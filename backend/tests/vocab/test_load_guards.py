"""The store's guards: one release at a time, nothing half-written, active notations unique."""

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import migrate
from app.vocab.loader import Concept, Vocabulary, read_vocabulary
from app.vocab.store import LoadResult, load_vocabulary
from tests.support import without_settings_variables
from tests.vocab.model import write_model

pytestmark = pytest.mark.pg

BACKEND = Path(__file__).resolve().parents[2]
EX = "https://example.org/vocab/"
COLOURS = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <https://example.org/vocab/> .

ex:colours a skos:ConceptScheme ; skos:prefLabel "Farben"@de .
"""
SHAPES = 'ex:shapes a skos:ConceptScheme ; skos:prefLabel "Formen"@de .\n'
RED_R = 'ex:red a skos:Concept ; skos:inScheme ex:colours ; skos:notation "R" .\n'
BLUE_R = 'ex:blue a skos:Concept ; skos:inScheme ex:colours ; skos:notation "R" .\n'


def fetch(url: str, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


def model(root: Path, *parts: str) -> Vocabulary:
    return read_vocabulary(write_model(root, COLOURS + "".join(parts)))


def run_load_command(database_url: str, ontology_dir: str) -> subprocess.CompletedProcess[str]:
    with without_settings_variables():
        environment = {**os.environ, "DATABASE_URL": database_url, "ONTOLOGY_DIR": ontology_dir}
    return subprocess.run(
        [sys.executable, "-m", "app.vocab.load"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


def test_loads_at_once_write_one_release(migrated: str, tmp_path: Path) -> None:
    vocabulary = model(tmp_path, RED_R)
    start = threading.Barrier(4)
    results: list[LoadResult] = []

    def run() -> None:
        start.wait()
        results.append(load_vocabulary(migrated, vocabulary))

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert sorted(result.changed for result in results) == [False, False, False, True]
    assert fetch(migrated, "SELECT count(*) FROM vocab_release") == [(1,)]


def test_a_failed_load_leaves_the_previous_release_whole(migrated: str, tmp_path: Path) -> None:
    good = model(tmp_path / "good", RED_R)
    load_vocabulary(migrated, good)
    rows_before = fetch(migrated, "SELECT * FROM vocab_concept ORDER BY iri")
    orphan = Concept(EX + "orphan", EX + "nowhere", [], None, {}, {}, {}, [])
    broken = Vocabulary("f" * 64, {}, good.schemes, {**good.concepts, orphan.iri: orphan})

    with pytest.raises(errors.ForeignKeyViolation):
        load_vocabulary(migrated, broken)

    assert fetch(migrated, "SELECT count(*) FROM vocab_release") == [(1,)]
    assert fetch(migrated, "SELECT * FROM vocab_concept ORDER BY iri") == rows_before


def test_a_scheme_the_files_no_longer_hold_is_retired(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, model(tmp_path / "a", SHAPES, RED_R))

    without = load_vocabulary(migrated, model(tmp_path / "b", RED_R))

    assert fetch(migrated, "SELECT retired_in FROM vocab_scheme WHERE iri = %s", EX + "shapes") == [
        (without.release_id,)
    ]


def test_a_notation_can_pass_from_a_retired_concept_to_a_new_one(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, model(tmp_path / "a", RED_R))

    load_vocabulary(migrated, model(tmp_path / "b", BLUE_R))

    active = fetch(migrated, "SELECT iri FROM vocab_concept WHERE notation = 'R' AND retired_in IS NULL")
    assert active == [(EX + "blue",)]


def test_two_active_concepts_cannot_share_a_notation_in_one_scheme(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, model(tmp_path, RED_R))

    with pytest.raises(errors.UniqueViolation), psycopg.connect(migrated) as connection:
        connection.execute(
            "INSERT INTO vocab_concept (iri, scheme_iri, types, notation, pref_labels, alt_labels,"
            " definitions, broader, properties) VALUES (%s, %s, '{}', 'R', '{}', '{}', '{}', '{}', '{}')",
            (EX + "blue", EX + "colours"),
        )


def test_the_load_command_refuses_a_missing_ontology_folder_and_retires_nothing(
    migrated: str, tmp_path: Path
) -> None:
    load_vocabulary(migrated, model(tmp_path / "a", RED_R))

    refused = run_load_command(migrated, str(tmp_path / "nowhere"))

    assert refused.returncode == 1
    assert "vocabulary not loaded" in refused.stderr
    assert fetch(migrated, "SELECT count(*) FROM vocab_concept WHERE retired_in IS NULL") == [(1,)]


def test_the_load_command_on_an_unmigrated_database_ends_with_1(database_url: str, tmp_path: Path) -> None:
    root = write_model(tmp_path, COLOURS + RED_R)

    refused = run_load_command(database_url, str(root))

    assert refused.returncode == 1
    assert "vocabulary not loaded" in refused.stderr


GREEN_A = 'ex:a a skos:Concept ; skos:inScheme ex:colours ; skos:notation "{n}" .\n'
GREEN_B = 'ex:b a skos:Concept ; skos:inScheme ex:colours ; skos:notation "{n}" .\n'


def test_two_concepts_that_stay_can_swap_their_notations(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, model(tmp_path / "a", GREEN_A.format(n="R"), GREEN_B.format(n="G")))

    load_vocabulary(migrated, model(tmp_path / "b", GREEN_A.format(n="G"), GREEN_B.format(n="R")))

    assert fetch(migrated, "SELECT iri, notation FROM vocab_concept ORDER BY iri") == [
        (EX + "a", "G"),
        (EX + "b", "R"),
    ]


def test_a_notation_passes_to_a_concept_that_sorts_first(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, model(tmp_path / "a", GREEN_B.format(n="R")))

    load_vocabulary(migrated, model(tmp_path / "b", GREEN_A.format(n="R"), GREEN_B.format(n="S")))

    assert fetch(migrated, "SELECT iri, notation FROM vocab_concept ORDER BY iri") == [
        (EX + "a", "R"),
        (EX + "b", "S"),
    ]
