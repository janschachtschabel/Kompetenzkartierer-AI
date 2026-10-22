"""The lands' own research, table T1 of each report, seeds the register beside the dataset (plan M1, 2.4).

Five assignments, each with its reports and its title column: Schule, Elementar and Beruf one
report per land, Hochschule and Erwachsenenbildung one for all lands. A row becomes a candidate
of no account, unchecked, with the title the research read off the document and its evidence:
E from the primary document, S from a secondary source. The comparison says which addresses
only the dataset knows, only the research, or both.
"""

import asyncio
import re
from collections import Counter
from pathlib import Path
from typing import Any, get_args

import psycopg
import pytest

from app.core.settings import REPOSITORY_ONTOLOGY
from app.db.migrate import migrate
from app.sources.register import EDUCATION_SECTORS, Evidence
from app.sources.research_t1 import ASSIGNMENTS, DATASET, RESEARCH, compare_addresses, read_research
from app.sources.seed import SeedError, read_documents, seed_register
from tests.sources.test_seed import DOCUMENTS, document, entries, run_command, write_documents

PUBLISHED = REPOSITORY_ONTOLOGY / RESEARCH
SECTORS = ("elementary", "school", "vocational", "higher", "adult")


def sector(notation: str) -> str:
    return f"https://w3id.org/wlo/curriculum/vocab#sec_{notation}"


# One report per assignment, as the research names them, with its title column
REPORTS = {
    "schule": ("01-schule-DE-BY.md", "dokumenttitel_woertlich"),
    "elementar": ("02-elementar-DE-BY.md", "dokumenttitel_woertlich"),
    "beruf": ("03B-beruf-DE-BY.md", "dokumenttitel_woertlich"),
    "hochschule": ("04A-hochschule-laender.md", "norm_titel_woertlich"),
    "eb": ("05A-eb-laender.md", "titel_woertlich"),
}


def row(title: str, url: str, **fields: str) -> dict[str, str]:
    return {"land": "DE-BY", "title": title, "url": url, "beleg": "E"} | fields


def table(title_column: str, *rows: dict[str, str]) -> list[str]:
    header = ["land", title_column, "kurzbezeichnung", "url", "beleg"]
    lines = ["```csv", ";".join(header)]
    for fields in rows:
        values = {"kurzbezeichnung": "", **fields, title_column: fields.get("title", "")}
        lines.append(";".join(values.get(column, "") for column in header))
    return [*lines, "```"]


def write_research(directory: Path, **rows: list[dict[str, str]]) -> Path:
    """A research folder with one report per assignment; T0 before T1, as the reports have it."""
    directory.mkdir(exist_ok=True)
    for assignment, (name, title_column) in REPORTS.items():
        lines = [
            f"# Bericht {name}",
            "",
            "## T0 Überblick",
            "",
            "```csv",
            "land;anzahl;url;beleg",
            "DE-BY;3;https://t0.example/;E",
            "```",
            "",
            "## T1 Dokumente",
            "",
            *table(title_column, *rows.get(assignment, [])),
            "",
        ]
        (directory / name).write_text("\n".join(lines), encoding="utf-8")
    return directory


# --- reading the published research


def test_the_published_research_gives_its_t1_rows_but_the_broken_ones() -> None:
    read = read_research(PUBLISHED)

    # 684 rows in the five assignments' T1 tables; a semicolon in a field moved six of them. Their
    # url fields name 34 addresses beyond the first
    assert len(read.rows) == 668
    assert read.left_out == {"shifted": 6, "no_url": 9, "no_title": 1, "further_address": 34}
    # 595 first addresses of the url fields: one the untitled row's alone, one another's with a bracket
    assert len({row.url for row in read.rows}) == 593


def test_each_assignment_seeds_its_own_sector() -> None:
    read = read_research(PUBLISHED)

    assert Counter(row.sector for row in read.rows) == {
        "school": 364,
        "elementary": 130,
        "vocational": 110,
        "higher": 16,
        "adult": 48,
    }


def test_the_assignments_are_the_five_of_the_research() -> None:
    assert {assignment.sector for assignment in ASSIGNMENTS.values()} == set(SECTORS)


# --- reading a report


def test_t1_is_the_table_under_its_heading_not_the_first(tmp_path: Path) -> None:
    directory = write_research(tmp_path / "r", schule=[row("Lehrplan Physik", "https://a.example/ph.pdf")])

    read = read_research(directory)

    assert [(row.title, row.url) for row in read.rows] == [("Lehrplan Physik", "https://a.example/ph.pdf")]


def test_without_a_t1_heading_the_first_table_is_t1(tmp_path: Path) -> None:
    directory = write_research(tmp_path / "r")
    lines = [
        "# Bericht",
        "",
        "## Dokumente",
        "",
        *table("dokumenttitel_woertlich", row("Plan", "https://b.example/")),
    ]
    (directory / "01-schule-DE-BY.md").write_text("\n".join(lines), encoding="utf-8")

    (found,) = read_research(directory).rows

    assert found.url == "https://b.example/"


@pytest.mark.parametrize("assignment", list(REPORTS))
def test_each_assignment_reads_its_own_title_column(tmp_path: Path, assignment: str) -> None:
    directory = write_research(
        tmp_path / "r", **{assignment: [row("Wörtlicher Titel", "https://c.example/")]}
    )

    (found,) = read_research(directory).rows

    assert found.title == "Wörtlicher Titel"
    assert found.sector == ASSIGNMENTS[assignment].sector


def test_the_overview_and_the_other_reports_are_no_t1_of_the_lands(tmp_path: Path) -> None:
    directory = write_research(tmp_path / "r")
    for name in ("03A-beruf-ueberblick.md", "04B-hochschule-modulhandbuecher.md", "07A-bewertungsskalen.md"):
        lines = ["## T1", *table("dokumenttitel_woertlich", row("Anderes", "https://d.example/"))]
        (directory / name).write_text("\n".join(lines), encoding="utf-8")

    assert read_research(directory).rows == []


@pytest.mark.parametrize(
    ("field", "url"),
    [
        ("https://a.example/x.pdf", "https://a.example/x.pdf"),
        ("https://a.example/x.pdf (Spiegel RPTU)", "https://a.example/x.pdf"),
        ("https://a.example/x.pdf S. 8 und 18", "https://a.example/x.pdf"),
        ("https://a.example/1 | https://a.example/2", "https://a.example/1"),
        ("https://a.example/1 | Kopie https://b.example/2", "https://a.example/1"),
        ("nur Verweis im Plan (https://c.example/lp.pdf)", "https://c.example/lp.pdf"),
        (
            "https://d.example/lp.pdf?__blob=publicationFile&v=3",
            "https://d.example/lp.pdf?__blob=publicationFile&v=3",
        ),
        ("https://e.example/wiki/Plan_(2024)", "https://e.example/wiki/Plan_(2024)"),
        ("HTTPS://f.example/a.", "https://f.example/a"),
    ],
)
def test_the_first_address_of_the_field_is_the_entry_s(tmp_path: Path, field: str, url: str) -> None:
    directory = write_research(tmp_path / "r", schule=[row("Plan", field)])

    (found,) = read_research(directory).rows

    assert found.url == url


# The url fields as the published research has them, by report
@pytest.mark.parametrize(
    ("field", "source_type"),
    [
        pytest.param(
            "https://www.lsvd.de/media/doc/3972/2015_thueringen_bildungsplan_18.pdf (Spiegelkopie)"
            " | https://bildung.thueringen.de/bildung/bildungsplan/ (Original-Portal wegen Captcha"
            " nicht lesbar)",
            "spiegel",
            id="02-elementar-DE-TH-spiegelkopie",
        ),
        pytest.param(
            "https://dms.nuw.rptu.de/geogebrainstitut/images/f/f4/Mathematik_RahmenLP_SekI.pdf"
            " (Spiegel RPTU, Landesserver-URL nicht gefunden)",
            "spiegel",
            id="01-schule-DE-RP-spiegel",
        ),
        pytest.param(
            "https://www.kita-saar.de/export/sites/kitas/katholische-kita-ggmbh-saarland/.galleries/"
            "dokumente/Bildungsprogramm_mit_Handreichungen_2018_August.pdf"
            " (Spiegel - Ministeriumsseite saarland.de HTTP 403)",
            "spiegel",
            id="02-elementar-DE-SL-spiegel",
        ),
        pytest.param(
            "https://hcg-berlin.de/wp-content/uploads/rahmenlehrplan-teil-c_mathe-1-10.pdf"
            " (Schulkopie, Original-Pfad des Bildungsservers nicht ermittelt)",
            "spiegel",
            id="01-schule-DE-BE-schulkopie",
        ),
        pytest.param(
            "https://reposit.haw-hamburg.de/bitstream/20.500.12738/9601/1/sp_d.08.1543.pdf (Sekundärquelle)",
            "sekundaer",
            id="02-elementar-DE-HH-sekundaerquelle",
        ),
        pytest.param(
            "https://edumedia-depot.gei.de/server/api/core/bitstreams/6208b92d-6433-4dc8-a541-948e39cac45a"
            "/content (Archivkopie)",
            "archiv",
            id="01-schule-DE-SL-gei-archivkopie",
        ),
        # the GEI's depot of curricula is an archive, whatever the note calls it
        pytest.param(
            "https://edumedia-depot.gei.de/bitstreams/1fccfa22-b21a-4d8e-a074-3f55476f8f1b/download"
            " (Spiegel GEI, Scan ohne Textlayer)",
            "archiv",
            id="01-schule-DE-RP-gei-spiegel",
        ),
        pytest.param(
            "https://edumedia-depot.gei.de/bitstreams/b92c434c-bf9f-4674-ae16-4e9f908b945d/download",
            "archiv",
            id="gei-without-a-note",
        ),
        pytest.param(
            "https://web.archive.org/web/2023id_/https://www.schulportal-thueringen.de/lp.pdf",
            "archiv",
            id="wayback",
        ),
        pytest.param("https://a.example/lp.pdf (Archivkopie)", "archiv", id="archivkopie-elsewhere"),
        # the copy the research read is another address, not the land's own
        pytest.param(
            "https://www.schleswig-holstein.de/mm/downloads/SOZMI/bildungsleitlinien.pdf (gelesen als Kopie"
            " https://www.partizipation-und-bildung.de/wp-content/uploads/2026/02/bildungsleitlinien.pdf)",
            None,
            id="02-elementar-DE-SH-gelesen-als-kopie",
        ),
        # a note after "|" is the further address's
        pytest.param(
            "https://www.saarland.de/SharedDocs/Downloads/DE/mbk/Lehrpl%C3%A4ne/Lehrplaene_Grundschule/"
            "GS_Kernlehrplan_Sachunterricht.pdf?__blob=publicationFile&v=3 | gelesen als Archivkopie"
            " https://edumedia-depot.gei.de/bitstreams/b92c434c-bf9f-4674-ae16-4e9f908b945d/download",
            None,
            id="01-schule-DE-SL-archivkopie-of-the-further",
        ),
        pytest.param(
            "https://www.schulportal-thueringen.de/media/detail?tspi=2279 | Kopie"
            " https://www.schule-am-kiliansberg.de/app/download/5818961109/Physik_RS_Nov_2012_7_10.pdf",
            None,
            id="01-schule-DE-TH-kopie-of-the-further",
        ),
        pytest.param(
            "https://epub.sub.uni-hamburg.de/epub/volltexte/2014/34356/pdf/bildungsempfehlungen.pdf"
            " (nicht abrufbar \N{EN DASH} HTTP 403)",
            None,
            id="02-elementar-DE-HH-other-note",
        ),
        pytest.param(
            "https://www.lsvd.de/media/doc/3972/2015_thueringen_bildungsplan_18.pdf S. 8 und 18",
            None,
            id="02-elementar-DE-TH-pages",
        ),
        pytest.param("https://a.example/lp.pdf", None, id="no-note"),
        # umwelt-online collects the lands' laws; the research calls it a secondary source
        pytest.param(
            "https://umwelt-online.de/recht/arbeitss/arbeitsrecht/laender/hb/wbg.htm",
            "sekundaer",
            id="05A-eb-DE-HB-umwelt-online",
        ),
        pytest.param(
            "https://www.umwelt-online.de/recht/arbeitss/arbeitsrecht/laender/th/kitag.htm",
            "sekundaer",
            id="02-elementar-DE-TH-www-umwelt-online",
        ),
        # a note marks the copy where it begins with what the copy is, not where it names a copy
        pytest.param("https://a.example/lp.pdf (keine Kopie verfügbar)", None, id="no-copy"),
        pytest.param("https://a.example/lp.pdf (Original, nicht die Schulkopie)", None, id="not-school-s"),
        pytest.param("https://a.example/lp.pdf (Spiegelstrich-Liste)", None, id="dashes"),
        pytest.param("https://a.example/lp.pdf (Sekundärquelle, Kopie)", "sekundaer", id="secondary-copy"),
    ],
)
def test_who_publishes_the_copy_is_as_the_field_notes_it_at_the_first_address(
    tmp_path: Path, field: str, source_type: str | None
) -> None:
    # Gesamtplan §7.5: an archive is a source of its own kind, a mirror is marked
    directory = write_research(tmp_path / "r", schule=[row("Plan", field)])

    (found,) = read_research(directory).rows

    assert found.source_type == source_type


def test_an_address_is_the_copy_a_note_calls_it_on_each_of_its_rows(tmp_path: Path) -> None:
    # the same address read for another passage, in another assignment's report
    mirror = "https://www.lsvd.de/media/doc/3972/2015_thueringen_bildungsplan_18.pdf"
    directory = write_research(
        tmp_path / "r",
        schule=[row("Bildungsplan bis 18", f"{mirror} S. 47 (Literatur)")],
        elementar=[row("Bildungsplan bis 18", f"{mirror} (Spiegelkopie)"), row("Plan", f"{mirror} S. 8")],
    )

    kinds = [found.source_type for found in read_research(directory).rows]

    assert kinds == ["spiegel", "spiegel", "spiegel"]


def test_the_published_research_marks_its_archives_mirrors_and_secondary_sources() -> None:
    kinds = Counter(row.source_type for row in read_research(PUBLISHED).rows)

    # five rows on the GEI's depot; mirrors in Berlin, Rhineland-Palatinate (2), Saarland and
    # Thuringia (three rows of one address); a secondary source in Hamburg and eleven rows of
    # umwelt-online
    assert kinds == {None: 644, "archiv": 5, "spiegel": 7, "sekundaer": 12}


def test_no_address_of_the_published_research_is_of_two_kinds() -> None:
    kinds: dict[str, set[str | None]] = {}
    for found in read_research(PUBLISHED).rows:
        kinds.setdefault(found.url, set()).add(found.source_type)

    assert {url: found for url, found in kinds.items() if len(found) > 1} == {}


def test_the_further_addresses_of_an_entry_s_field_are_counted(tmp_path: Path) -> None:
    # an entry takes the first address alone; the others are left out, not lost unseen
    twice = row("Plan", "https://a.example/1 | https://a.example/2")
    directory = write_research(
        tmp_path / "r",
        schule=[
            row("Drei", "https://b.example/1 | https://b.example/2 | Kopie https://b.example/3"),
            row("Kopie", "https://c.example/1 (gelesen als Kopie https://c.example/2)"),
            twice,
            twice,
            row("", "https://d.example/1 | https://d.example/2"),
        ],
    )

    read = read_research(directory)

    assert len(read.rows) == 3
    # of the rows that are entries: not of the duplicate, nor of the row without a title
    assert read.left_out == {"further_address": 4, "duplicate": 1, "no_title": 1}


def test_a_row_without_an_address_or_a_title_is_left_out_and_counted(tmp_path: Path) -> None:
    directory = write_research(
        tmp_path / "r",
        schule=[row("Plan", "nicht veröffentlicht"), row("Plan", ""), row("", "https://a.example/")],
        eb=[row("Plan", "https://user:pw@a.example/"), row("Gültig", "https://a.example/ok")],
    )

    read = read_research(directory)

    assert [found.title for found in read.rows] == ["Gültig"]
    assert read.left_out == {"no_url": 2, "no_title": 1, "url_invalid": 1}


def test_a_row_a_semicolon_moved_is_left_out_and_counted(tmp_path: Path) -> None:
    # as the research has it six times: a semicolon in an earlier field moves url and beleg on
    directory = write_research(
        tmp_path / "r",
        elementar=[row("Gesetz; Verordnung", "https://a.example/"), row("Plan", "https://b.example/")],
    )

    read = read_research(directory)

    assert [found.url for found in read.rows] == ["https://b.example/"]
    assert read.left_out == {"shifted": 1}


@pytest.mark.parametrize(
    ("beleg", "evidence"),
    [
        ("E", "E"),
        ("S", "S"),
        ("S (Portalseite deutsch.html)", "S"),
        ("E (Titel S.1) | S (Gültigkeit laut Portal)", "E"),
        ("E (Auflistung) / A (Aufbau nicht geprüft)", "E"),
        ("A", None),
        ("", None),
        ("Expertise", None),
    ],
)
def test_the_evidence_is_as_the_field_begins(tmp_path: Path, beleg: str, evidence: str | None) -> None:
    directory = write_research(tmp_path / "r", schule=[row("Plan", "https://a.example/", beleg=beleg)])

    (found,) = read_research(directory).rows

    assert found.evidence == evidence


@pytest.mark.parametrize(
    ("land", "country"), [("DE-BY", "DE-BY"), ("DE", "DE"), ("Bayern", None), ("DE-BAY", None)]
)
def test_the_land_is_the_country(tmp_path: Path, land: str, country: str | None) -> None:
    directory = write_research(tmp_path / "r", eb=[row("Plan", "https://a.example/", land=land)])

    (found,) = read_research(directory).rows

    assert found.country == country


def test_a_long_title_is_cut_to_what_the_register_holds(tmp_path: Path) -> None:
    directory = write_research(
        tmp_path / "r", beruf=[row("Bildungsplan  für " + "x" * 600, "https://a.example/")]
    )

    (found,) = read_research(directory).rows

    assert found.title.startswith("Bildungsplan für x")
    assert len(found.title) == 500


def test_a_row_twice_is_one_entry(tmp_path: Path) -> None:
    same = row("Plan", "https://a.example/")
    directory = write_research(tmp_path / "r", schule=[same, same])

    read = read_research(directory)

    assert len(read.rows) == 1
    assert read.left_out == {"duplicate": 1}


def test_a_row_keeps_its_key_when_rows_before_it_change(tmp_path: Path) -> None:
    first = read_research(write_research(tmp_path / "a", schule=[row("Plan", "https://a.example/")]))
    later = read_research(
        write_research(
            tmp_path / "b", schule=[row("Neu", "https://n.example/"), row("Plan", "https://a.example/")]
        )
    )

    assert first.rows[0].key in {found.key for found in later.rows}


def test_a_row_keeps_its_key_when_its_report_is_renamed(tmp_path: Path) -> None:
    same = row("Plan", "https://a.example/")
    first = read_research(write_research(tmp_path / "a", schule=[same]))
    renamed = write_research(tmp_path / "b", schule=[same])
    (renamed / "01-schule-DE-BY.md").rename(renamed / "01-schule-DE-BY-fassung-2.md")

    (later,) = read_research(renamed).rows

    assert later.key == first.rows[0].key


def test_a_corrected_title_is_a_new_candidate(tmp_path: Path) -> None:
    # the editors clear away the old one: the register keeps what it was seeded with
    first = read_research(
        write_research(tmp_path / "a", schule=[row("Lehrplan Phsyik", "https://a.example/")])
    )
    later = read_research(
        write_research(tmp_path / "b", schule=[row("Lehrplan Physik", "https://a.example/")])
    )

    assert first.rows[0].key != later.rows[0].key


def test_the_same_title_and_address_of_two_assignments_are_two_entries(tmp_path: Path) -> None:
    same = row("Gesetz", "https://a.example/")
    directory = write_research(tmp_path / "r", schule=[same], beruf=[same])

    assert len({found.key for found in read_research(directory).rows}) == 2


def test_a_table_without_the_title_column_is_refused(tmp_path: Path) -> None:
    directory = write_research(tmp_path / "r")
    lines = ["## T1", *table("titel", row("Plan", "https://a.example/"))]
    (directory / "01-schule-DE-BY.md").write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(SeedError, match=r"01-schule-DE-BY\.md.*dokumenttitel_woertlich"):
        read_research(directory)


def test_a_report_without_a_table_is_refused(tmp_path: Path) -> None:
    directory = write_research(tmp_path / "r")
    (directory / "05A-eb-laender.md").write_text("# Bericht\n\nkeine Tabelle\n", encoding="utf-8")

    with pytest.raises(SeedError, match=r"05A-eb-laender\.md"):
        read_research(directory)


def test_a_folder_without_the_reports_of_an_assignment_is_refused(tmp_path: Path) -> None:
    directory = write_research(tmp_path / "r")
    (directory / "04A-hochschule-laender.md").unlink()

    with pytest.raises(SeedError, match="ONTOLOGY_DIR"):
        read_research(directory)


# --- into the register


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


def with_sectors(url: str, *notations: str) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO vocab_scheme (iri, types, pref_labels, properties) VALUES (%s, '{}', '{}', '{}')",
            (EDUCATION_SECTORS,),
        )
        for notation in notations:
            connection.execute(
                "INSERT INTO vocab_concept (iri, scheme_iri, types, notation, pref_labels, alt_labels,"
                " definitions, broader, properties) VALUES (%s, %s, '{}', %s, '{}', '{}', '{}', '{}', '{}')",
                (sector(notation), EDUCATION_SECTORS, notation),
            )


@pytest.fixture
def sectored(migrated: str) -> str:
    with_sectors(migrated, *SECTORS)
    return migrated


def run(coroutine_of: Any, url: str) -> Any:
    async def go() -> Any:
        async with await psycopg.AsyncConnection.connect(url) as connection:
            return await coroutine_of(connection)

    return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)


def seed_research(url: str, directory: Path = PUBLISHED) -> Any:
    rows = read_research(directory).rows
    return run(lambda connection: seed_register(connection, rows, DATASET), url)


@pytest.mark.pg
def test_the_research_seeds_candidates_of_no_account_with_their_evidence_and_sector(
    sectored: str, tmp_path: Path
) -> None:
    directory = write_research(
        tmp_path / "r",
        schule=[row("Lehrplan Physik", "https://a.example/ph.pdf", beleg="E (Titelseite)")],
        eb=[row("Weiterbildungsgesetz", "https://b.example/wbg", land="DE-NW", beleg="A")],
    )

    report = seed_research(sectored, directory)

    found = {entry["title"]: entry for entry in entries(sectored)}
    assert (report.added, report.present) == (2, 0)
    school, adult = found["Lehrplan Physik"], found["Weiterbildungsgesetz"]
    assert (school["provenance"], school["dataset"], school["register_status"]) == (
        DATASET,
        DATASET,
        "unchecked",
    )
    assert (school["owner_id"], school["rights_status"], school["source_type"]) == (None, "unklar", None)
    assert (school["sector_iri"], school["evidence"], school["country"]) == (sector("school"), "E", "DE-BY")
    assert (adult["sector_iri"], adult["evidence"], adult["country"]) == (sector("adult"), None, "DE-NW")


@pytest.mark.pg
def test_the_published_research_seeds_once(sectored: str) -> None:
    first = seed_research(sectored)
    before = entries(sectored)

    second = seed_research(sectored)

    assert (first.added, second.added, second.present) == (668, 0, 668)
    assert entries(sectored) == before
    assert {entry["provenance"] for entry in before} == {DATASET}


@pytest.mark.pg
def test_without_a_sector_of_the_research_nothing_is_seeded(migrated: str) -> None:
    with_sectors(migrated, "school", "vocational", "higher", "adult")

    with pytest.raises(SeedError, match=r"elementary.*app\.vocab\.load"):
        seed_research(migrated)

    with psycopg.connect(migrated) as connection:
        assert connection.execute("SELECT count(*) FROM source").fetchone() == (0,)


@pytest.mark.pg
def test_the_comparison_counts_the_addresses_by_who_knows_them(sectored: str, tmp_path: Path) -> None:
    documents = write_documents(
        tmp_path / "d.csv",
        document("BY.GYM.PH", URL="https://a.example/seed-only"),
        document("BY.GYM.CH", URL="https://a.example/both"),
        document("BY.GYM.BIO", URL="https://a.example/both"),
    )
    run(lambda connection: seed_register(connection, read_documents(documents).rows), sectored)
    directory = write_research(
        tmp_path / "r",
        schule=[
            row("Chemie", "https://a.example/both"),
            row("Informatik", "https://a.example/research-only"),
        ],
    )
    seed_research(sectored, directory)

    comparison = run(compare_addresses, sectored)

    assert (comparison.only_seed, comparison.only_research, comparison.both) == (1, 1, 1)


@pytest.mark.pg
def test_the_evidence_the_table_holds_is_the_code_s(migrated: str) -> None:
    with psycopg.connect(migrated) as connection:
        found = connection.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'source_seed'::regclass AND conname = 'source_seed_evidence_check'"
        ).fetchone()

    assert found is not None
    assert set(re.findall(r"'([^']*)'::text", found[0])) == set(get_args(Evidence))


@pytest.mark.pg
def test_the_command_seeds_the_research_and_compares_it_with_the_dataset(sectored: str) -> None:
    run(lambda connection: seed_register(connection, read_documents(DOCUMENTS).rows), sectored)

    done = run_command(sectored, module="app.sources.research_t1")

    assert done.returncode == 0, done.stderr
    assert (
        "668 entries added, 0 in the register already;"
        " left out: further_address 34, no_title 1, no_url 9, shifted 6" in done.stderr
    )
    # the dataset's 1,278 addresses and the research's 593
    assert (
        "addresses only in the comparison dataset 1210, only in the research 525, in both 68" in done.stderr
    )


@pytest.mark.pg
def test_the_command_ends_with_1_where_the_folder_holds_no_research(sectored: str, tmp_path: Path) -> None:
    done = run_command(sectored, str(tmp_path), module="app.sources.research_t1")

    assert done.returncode == 1
    assert "ONTOLOGY_DIR" in done.stderr
