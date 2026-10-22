"""The comparison dataset v62.493 seeds the source register (plan M1, 2.2; Gesamtplan §7.5).

Its rows become candidates of no account, unchecked: what was published of a curriculum (its
address, land, school form, subject, grades, binding, kind of source), never the dataset's own
titles, themes or node counts. ESA derivations and "kanonisch" rows are no curricula of their own.
"""

import asyncio
import csv
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args
from urllib.parse import urlsplit

import psycopg
import pytest
from psycopg.rows import dict_row

from app.db.migrate import migrate
from app.sources.register import EDUCATION_SECTORS, SEED_DIR, Provenance, SeedDataset
from app.sources.seed import DATASET, SeedError, read_documents, seed_register
from tests.support import without_settings_variables

BACKEND = Path(__file__).resolve().parents[2]

SCHOOL = "https://w3id.org/wlo/curriculum/vocab#sec_school"
DOCUMENTS = SEED_DIR / "lehrplan_dokumente_de.csv"
# The documents file's columns, in its order
COLUMNS = [
    "Titel",
    "Beschreibung",
    "Themen (Auszug)",
    "Land_Kuerzel",
    "Land",
    "Sektor",
    "Schulform",
    "Fach_Schluessel",
    "Fach",
    "Bildungsstufe",
    "Jahrgang_von",
    "Jahrgang_bis",
    "G8/G9",
    "Stand (Quelle)",
    "Jahr",
    "Verbindlichkeit",
    "URL",
    "URL_Original",
    "URL_Typ",
    "URL_Kandidat",
    "Kandidat_Herkunft",
    "URL_Archiv",
    "Wayback_Zeitstempel",
    "Quelltyp",
    "Verifikation",
    "ESA-Ableitung",
    "md5",
    "Anzahl_Knoten",
    "davon_Themeneinheiten_E3",
    "davon_Unterthemen_E4",
    "davon_Belege_E5",
    "davon_quellennah",
    "davon_Altgeruest",
    "Beispiel_ID",
    "Modellversion",
]


def write_documents(path: Path, *rows: dict[str, str]) -> Path:
    """A documents file as the dataset writes it (BOM, semicolons, CRLF), with these rows."""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})
    return path


def document(key: str, **fields: str) -> dict[str, str]:
    base = {
        "Titel": f"Ein Titel des Datensatzes {key}",
        "Themen (Auszug)": "Thema A | Thema B",
        "Land_Kuerzel": "BY",
        "Land": "Bayern",
        "Schulform": "Gymnasium",
        "Fach_Schluessel": "physik",
        "Fach": "Physik",
        "Bildungsstufe": "Sekundarstufe I",
        "Jahrgang_von": "7",
        "Jahrgang_bis": "10",
        "Verbindlichkeit": "verbindlich",
        "URL": f"https://www.lehrplanplus.bayern.de/{key}",
        "Quelltyp": "Landesportal",
        "Verifikation": "volltext",
        "Anzahl_Knoten": "120",
        "Beispiel_ID": key,
    }
    return base | fields


# --- reading the file


def test_the_published_file_gives_the_plan_s_counts() -> None:
    read = read_documents(DOCUMENTS)

    urls = {row.url for row in read.rows}
    assert len(read.rows) == 1498
    # the plan counted 1,279 strings: one is an address with a note after it, the same as another
    assert len(urls) == 1278
    assert len({urlsplit(url).hostname for url in urls}) == 34
    assert read.left_out == {"esa": 90, "kanonisch": 243}


def test_an_esa_derivation_and_a_kanonisch_row_are_left_out(tmp_path: Path) -> None:
    path = write_documents(
        tmp_path / "d.csv",
        document("BY.GYM.PH"),
        document("BB.ESA.GEO", **{"ESA-Ableitung": "ja"}),
        document("HB.GYM.PH", Verifikation="kanonisch"),
    )

    read = read_documents(path)

    assert [row.key for row in read.rows] == ["BY.GYM.PH"]


def test_a_local_url_takes_the_original_address(tmp_path: Path) -> None:
    path = write_documents(
        tmp_path / "d.csv",
        document("BB.GYM.GEO", URL="lokal", URL_Original="https://bildungsserver.example/a.pdf"),
    )

    (row,) = read_documents(path).rows

    assert row.url == "https://bildungsserver.example/a.pdf"


def test_a_note_in_brackets_after_the_address_is_no_part_of_it(tmp_path: Path) -> None:
    # as the dataset has it once (BW.MA.PK): the address, a space, a note for its readers
    path = write_documents(
        tmp_path / "d.csv",
        document(
            "BW.MA.PK", URL="https://www.bildungsplaene-bw.de/BP2016BW_M_IK_5-6_04 (Sidebar, PK-Katalog)"
        ),
    )

    (row,) = read_documents(path).rows

    assert row.url == "https://www.bildungsplaene-bw.de/BP2016BW_M_IK_5-6_04"


def test_a_row_keeps_what_was_published_of_the_curriculum_and_no_more(tmp_path: Path) -> None:
    path = write_documents(
        tmp_path / "d.csv",
        document(
            "SH.GYM.GE",
            Land_Kuerzel="SH",
            Land="Schleswig-Holstein",
            Fach="Geschichte",
            Fach_Schluessel="geschichte",
            Jahrgang_von="5",
            Jahrgang_bis="9",
            Verbindlichkeit="bedingt",
            Quelltyp="Wayback-Archiv",
            URL_Archiv="https://web.archive.org/web/20201205224206/https://fachportal.example/ge.pdf",
            Wayback_Zeitstempel="20201205224206",
        ),
    )

    (row,) = read_documents(path).rows

    assert (row.country, row.school_form, row.subject_key, row.subject) == (
        "DE-SH",
        "Gymnasium",
        "geschichte",
        "Geschichte",
    )
    assert (row.grade_from, row.grade_to, row.binding, row.source_type) == (5, 9, "bedingt", "archiv")
    assert row.archive_url == "https://web.archive.org/web/20201205224206/https://fachportal.example/ge.pdf"
    assert row.archived_at == "20201205224206"
    # the register's own title, not the dataset's
    assert row.title == "Schleswig-Holstein · Geschichte · Gymnasium"


@pytest.mark.parametrize(
    ("kind", "source_type"),
    [
        ("Landesportal", "amtlich"),
        ("KMK", "amtlich"),
        ("Wayback-Archiv", "archiv"),
        ("GEI-Depot", "archiv"),
        ("Drittquelle/Spiegel", "spiegel"),
        ("unbekannt", None),
    ],
)
def test_the_kind_of_source_is_the_register_s(tmp_path: Path, kind: str, source_type: str | None) -> None:
    (row,) = read_documents(write_documents(tmp_path / "d.csv", document("BY.GYM.PH", Quelltyp=kind))).rows

    assert row.source_type == source_type


def test_a_row_whose_address_cannot_be_fetched_is_left_out_and_counted(tmp_path: Path) -> None:
    path = write_documents(
        tmp_path / "d.csv",
        document("BY.GYM.PH"),
        document("BY.GYM.CH", URL="ftp://lehrplan.example/ch.pdf"),
        document("BY.GYM.BIO", URL="https://user:pw@lehrplan.example/bio.pdf"),
    )

    read = read_documents(path)

    assert [row.key for row in read.rows] == ["BY.GYM.PH"]
    assert read.left_out == {"url_invalid": 2}


def test_grades_that_are_no_numbers_stay_unknown(tmp_path: Path) -> None:
    path = write_documents(tmp_path / "d.csv", document("BY.GYM.PH", Jahrgang_von="", Jahrgang_bis="Q2"))

    (row,) = read_documents(path).rows

    assert (row.grade_from, row.grade_to) == (None, None)


# --- into the register


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


def with_sectors(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO vocab_scheme (iri, types, pref_labels, properties) VALUES (%s, '{}', '{}', '{}')",
            (EDUCATION_SECTORS,),
        )
        connection.execute(
            "INSERT INTO vocab_concept (iri, scheme_iri, types, notation, pref_labels, alt_labels,"
            " definitions, broader, properties)"
            " VALUES (%s, %s, '{}', 'school', '{}', '{}', '{}', '{}', '{}')",
            (SCHOOL, EDUCATION_SECTORS),
        )


def run_seed(url: str, path: Path = DOCUMENTS) -> Any:
    async def go() -> Any:
        async with await psycopg.AsyncConnection.connect(url) as connection:
            return await seed_register(connection, read_documents(path).rows)

    return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)


def entries(url: str) -> list[dict[str, Any]]:
    with psycopg.connect(url, row_factory=dict_row) as connection:
        return connection.execute(
            "SELECT s.*, x.* FROM source s JOIN source_seed x ON x.source_id = s.id ORDER BY x.seed_key"
        ).fetchall()


@pytest.fixture
def seeded(migrated: str) -> Iterator[str]:
    with_sectors(migrated)
    yield migrated


@pytest.mark.pg
def test_the_dataset_seeds_candidates_of_no_account_unchecked(seeded: str) -> None:
    report = run_seed(seeded)

    rows = entries(seeded)
    assert (report.added, report.present) == (1498, 0)
    assert len(rows) == 1498
    assert {row["provenance"] for row in rows} == {DATASET}
    assert {row["register_status"] for row in rows} == {"unchecked"}
    assert {row["rights_status"] for row in rows} == {"unklar"}
    assert {row["owner_id"] for row in rows} == {None}
    assert {row["sector_iri"] for row in rows} == {SCHOOL}
    assert len({row["url"] for row in rows}) == 1278


@pytest.mark.pg
def test_a_second_run_changes_nothing(seeded: str) -> None:
    run_seed(seeded)
    before = entries(seeded)

    report = run_seed(seeded)

    assert (report.added, report.present) == (0, 1498)
    assert entries(seeded) == before


@pytest.mark.pg
def test_no_title_of_the_dataset_reaches_the_register(seeded: str) -> None:
    run_seed(seeded)

    with DOCUMENTS.open(encoding="utf-8-sig", newline="") as handle:
        published = {row["Titel"] for row in csv.DictReader(handle, delimiter=";")}
    assert published.isdisjoint({row["title"] for row in entries(seeded)})


@pytest.mark.pg
def test_without_the_education_sectors_nothing_is_seeded(migrated: str) -> None:
    with pytest.raises(SeedError, match=r"app\.vocab\.load"):
        run_seed(migrated)

    with psycopg.connect(migrated) as connection:
        assert connection.execute("SELECT count(*) FROM source").fetchone() == (0,)


@pytest.mark.pg
def test_the_datasets_the_table_holds_are_the_code_s(migrated: str) -> None:
    with psycopg.connect(migrated) as connection:
        found = connection.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'source_seed'::regclass AND conname = 'source_seed_dataset_check'"
        ).fetchone()

    assert found is not None
    assert set(re.findall(r"'([^']*)'::text", found[0])) == set(get_args(SeedDataset))
    assert set(get_args(SeedDataset)) <= set(get_args(Provenance))
    assert DATASET in get_args(SeedDataset)


def run_command(
    url: str, *arguments: str, module: str = "app.sources.seed"
) -> subprocess.CompletedProcess[str]:
    with without_settings_variables():
        environment = {**os.environ, "DATABASE_URL": url, "LOG_FORMAT": "text"}
    return subprocess.run(  # noqa: S603 - this interpreter and a fixed module
        [sys.executable, "-m", module, *arguments],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.pg
def test_the_command_seeds_a_file_and_says_how_many(seeded: str, tmp_path: Path) -> None:
    path = write_documents(
        tmp_path / "d.csv", document("BY.GYM.PH"), document("BB.ESA.GEO", **{"ESA-Ableitung": "ja"})
    )

    done = run_command(seeded, str(path))

    assert done.returncode == 0, done.stderr
    assert "1 entries added, 0 in the register already; left out: esa 1" in done.stderr
    # the access notes come with the seed, from the published file beside it
    assert "353 access notes added, 0 in the register already; left out: empty 2" in done.stderr


@pytest.mark.pg
def test_the_command_ends_with_1_where_the_register_cannot_take_the_seed(
    migrated: str, tmp_path: Path
) -> None:
    done = run_command(migrated, str(write_documents(tmp_path / "d.csv", document("BY.GYM.PH"))))

    assert done.returncode == 1
    assert "app.vocab.load" in done.stderr
