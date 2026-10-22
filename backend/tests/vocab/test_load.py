"""Loading the vocabularies into PostgreSQL: one release per content, nothing lost on change."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.db.migrate import migrate
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.support import without_settings_variables
from tests.vocab.model import write_model

pytestmark = pytest.mark.pg

BACKEND = Path(__file__).resolve().parents[2]
ONTOLOGY = BACKEND.parent / "ontology"
LEVEL = "https://w3id.org/wlo/curriculum/level/"
EX = "https://example.org/vocab/"
SCHEME = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix ex: <https://example.org/vocab/> .

ex:colours a skos:ConceptScheme ; skos:prefLabel "Farben"@de .
"""
RED = 'ex:red a skos:Concept ; skos:inScheme ex:colours ; skos:prefLabel "{label}"@de .\n'
BLUE = 'ex:blue a skos:Concept ; skos:inScheme ex:colours ; skos:prefLabel "Blau"@de .\n'


def colours(root: Path, *concepts: str) -> Path:
    return write_model(root, SCHEME + "".join(concepts))


def fetch(url: str, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


def test_the_ontology_loads_with_the_counts_of_its_files(migrated: str) -> None:
    vocabulary = read_vocabulary(ONTOLOGY)

    load_vocabulary(migrated, vocabulary)

    [(schemes, concepts)] = fetch(
        migrated, "SELECT (SELECT count(*) FROM vocab_scheme), (SELECT count(*) FROM vocab_concept)"
    )
    [(level_schemes, levels)] = fetch(
        migrated,
        "SELECT (SELECT count(*) FROM vocab_scheme WHERE iri LIKE %s),"
        " (SELECT count(*) FROM vocab_concept WHERE scheme_iri LIKE %s)",
        LEVEL + "%",
        LEVEL + "%",
    )
    assert (schemes, concepts) == (len(vocabulary.schemes), len(vocabulary.concepts))
    assert (level_schemes, levels) == (24, 135)


def test_a_concept_row_keeps_what_the_files_say(migrated: str) -> None:
    vocabulary = read_vocabulary(ONTOLOGY)
    load_vocabulary(migrated, vocabulary)
    level = next(concept for concept in vocabulary.concepts.values() if concept.scheme.startswith(LEVEL))

    [row] = fetch(
        migrated,
        "SELECT scheme_iri, types, notation, pref_labels, alt_labels, definitions, broader, properties,"
        " retired_in FROM vocab_concept WHERE iri = %s",
        level.iri,
    )

    assert row == (
        level.scheme,
        level.types,
        level.notation,
        level.pref_labels,
        level.alt_labels,
        level.definitions,
        level.broader,
        level.properties,
        None,
    )


def test_a_second_load_of_the_same_files_changes_nothing(migrated: str) -> None:
    vocabulary = read_vocabulary(ONTOLOGY)
    first = load_vocabulary(migrated, vocabulary)
    rows_before = fetch(migrated, "SELECT * FROM vocab_concept ORDER BY iri")

    second = load_vocabulary(migrated, read_vocabulary(ONTOLOGY))

    assert first.changed and not second.changed
    assert second.release_id == first.release_id
    assert fetch(migrated, "SELECT count(*) FROM vocab_release") == [(1,)]
    assert fetch(migrated, "SELECT * FROM vocab_concept ORDER BY iri") == rows_before


def test_changed_files_give_a_new_release_and_new_values(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, read_vocabulary(colours(tmp_path / "a", RED.format(label="Rot"))))

    result = load_vocabulary(migrated, read_vocabulary(colours(tmp_path / "b", RED.format(label="Rotton"))))

    assert result.changed
    assert fetch(migrated, "SELECT count(*) FROM vocab_release") == [(2,)]
    assert fetch(migrated, "SELECT pref_labels FROM vocab_concept WHERE iri = %s", EX + "red") == [
        ({"de": "Rotton"},)
    ]


def test_a_removed_concept_is_retired_not_deleted_and_returns(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, read_vocabulary(colours(tmp_path / "a", RED.format(label="Rot"), BLUE)))

    without = load_vocabulary(migrated, read_vocabulary(colours(tmp_path / "b", RED.format(label="Rot"))))
    retired = fetch(migrated, "SELECT retired_in FROM vocab_concept WHERE iri = %s", EX + "blue")
    load_vocabulary(migrated, read_vocabulary(colours(tmp_path / "c", RED.format(label="Rot"), BLUE)))
    back = fetch(migrated, "SELECT retired_in FROM vocab_concept WHERE iri = %s", EX + "blue")

    assert retired == [(without.release_id,)]
    assert back == [(None,)]


def test_the_load_command_reads_the_folder_the_settings_name(migrated: str, tmp_path: Path) -> None:
    root = colours(tmp_path, RED.format(label="Rot"))
    with without_settings_variables():
        environment = {
            **os.environ,
            "DATABASE_URL": migrated,
            "ONTOLOGY_DIR": str(root),
            "LOG_FORMAT": "json",
        }

    runs = [
        subprocess.run(
            [sys.executable, "-m", "app.vocab.load"],
            cwd=BACKEND,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        for _ in range(2)
    ]

    assert [run.returncode for run in runs] == [0, 0], runs[0].stderr
    assert "loaded release" in runs[0].stderr
    assert "unchanged" in runs[1].stderr
    assert fetch(migrated, "SELECT iri FROM vocab_concept") == [(EX + "red",)]
