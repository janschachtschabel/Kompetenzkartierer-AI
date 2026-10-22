"""The dataset's notes on blocked portals and detours become access notes (plan M1, 2.3).

A note belongs to a land, school form and subject; a register entry seeded with the same three
shows it, and a note naming no school form or no subject holds for all of them. The rule stays
ours (Gesamtplan §7.5): official sources first, an archive as one, a mirror marked; a technical
barrier is never got round.
"""

import asyncio
import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.db.migrate import migrate
from app.sources.access_notes import NOTES, read_notes, record_notes
from app.sources.register import EDUCATION_SECTORS
from app.sources.seed import read_documents, seed_register
from tests.sources.test_seed import SCHOOL, document, write_documents
from tests.support import make_settings, seed_account, selector_client

PUBLIC = "http://testserver:8000"


def published_notes() -> list[dict[str, str]]:
    with NOTES.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def test_the_published_notes_are_read_but_the_empty_ones() -> None:
    read = read_notes(NOTES)

    assert len(read.notes) == 353
    assert read.left_out == {"empty": 2}


def test_a_note_keeps_its_scope_categories_and_address() -> None:
    raw = next(
        row
        for row in published_notes()
        if "; " in row["Kategorien"] and row["URL_im_Text"].startswith("http")
    )

    note = next(note for note in read_notes(NOTES).notes if note.text == " ".join(raw["Hinweis"].split()))

    assert note.country == f"DE-{raw['Land_Kuerzel']}"
    assert (note.school_form, note.subject) == (raw["Schulform"], raw["Fach"])
    assert note.categories == [part.strip() for part in raw["Kategorien"].split(";")]
    assert note.url == raw["URL_im_Text"]


def test_a_local_address_is_none() -> None:
    assert any(row["URL_im_Text"] == "lokal" for row in published_notes())

    assert all(note.url is None or note.url.startswith("http") for note in read_notes(NOTES).notes)


# --- into the register and onto an entry


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as connection:
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
    return database_url


def run(coroutine_of: Any, url: str) -> Any:
    async def go() -> Any:
        async with await psycopg.AsyncConnection.connect(url) as connection:
            return await coroutine_of(connection)

    return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)


@pytest.mark.pg
def test_the_notes_are_recorded_once(migrated: str) -> None:
    notes = read_notes(NOTES).notes

    first = run(lambda connection: record_notes(connection, notes), migrated)
    second = run(lambda connection: record_notes(connection, notes), migrated)

    assert (first.added, second.added, second.present) == (353, 0, 353)


@pytest.fixture
def client(migrated: str, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(database_url=migrated, storage_dir=tmp_path))
    with selector_client(app, base_url=PUBLIC) as test_client:
        yield test_client


@pytest.mark.pg
def test_an_entry_shows_the_notes_of_its_land_school_form_and_subject(
    client: TestClient, migrated: str, tmp_path: Path
) -> None:
    raw = next(row for row in published_notes() if row["Land_Kuerzel"] == "RP" and row["Hinweis"].strip())
    scope = {
        "Land_Kuerzel": "RP",
        "Land": "Rheinland-Pfalz",
        "Schulform": raw["Schulform"],
        "Fach": raw["Fach"],
    }
    path = write_documents(
        tmp_path / "d.csv",
        document("RP.X.1", **scope),
        document("BY.X.2", URL="https://lehrplan.example/2", Fach="Kein Fach"),
    )
    run(lambda connection: seed_register(connection, read_documents(path).rows), migrated)
    run(lambda connection: record_notes(connection, read_notes(NOTES).notes), migrated)
    _, header = seed_account(migrated, "Lehrkraft", ["nutzer"])
    entries = {
        entry["url"]: entry for entry in client.get("/api/v1/sources", headers=header).json()["entries"]
    }
    with_notes = entries["https://www.lehrplanplus.bayern.de/RP.X.1"]
    without = entries["https://lehrplan.example/2"]

    detail = client.get(f"/api/v1/sources/{with_notes['id']}", headers=header).json()
    other = client.get(f"/api/v1/sources/{without['id']}", headers=header).json()

    expected = {
        " ".join(row["Hinweis"].split())
        for row in published_notes()
        if (row["Land_Kuerzel"], row["Schulform"], row["Fach"]) == ("RP", raw["Schulform"], raw["Fach"])
        and row["Hinweis"].strip()
    }
    assert {note["text"] for note in detail["access_notes"]} == expected
    assert detail["seed"]["school_form"] == raw["Schulform"]
    assert detail["seed"]["subject"] == raw["Fach"]
    assert (detail["seed"]["grade_from"], detail["seed"]["grade_to"]) == (7, 10)
    # no note names its subject: it shows none, though notes on its land and school form exist
    assert other["access_notes"] == []


# The notes file's columns, in its order
NOTE_COLUMNS = [
    "Land_Kuerzel",
    "Land",
    "Schulform",
    "Fach",
    "Kategorien",
    "Feld",
    "Hinweis",
    "URL_im_Text",
    "Herkunft",
]


def write_notes(path: Path, *rows: dict[str, str]) -> Path:
    """A notes file as the dataset writes it (BOM, semicolons, CRLF), with these rows."""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, NOTE_COLUMNS, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in NOTE_COLUMNS})
    return path


def note(land: str, school_form: str, subject: str, text: str) -> dict[str, str]:
    return {"Land_Kuerzel": land, "Schulform": school_form, "Fach": subject, "Hinweis": text}


def notes_shown(client: TestClient, migrated: str, documents: Path, notes: Path) -> set[str]:
    """The texts of the notes the one entry of ``documents`` shows."""
    run(lambda connection: seed_register(connection, read_documents(documents).rows), migrated)
    run(lambda connection: record_notes(connection, read_notes(notes).notes), migrated)
    _, header = seed_account(migrated, "Lehrkraft", ["nutzer"])
    (entry,) = client.get("/api/v1/sources", headers=header).json()["entries"]
    detail = client.get(f"/api/v1/sources/{entry['id']}", headers=header).json()
    return {found["text"] for found in detail["access_notes"]}


@pytest.mark.pg
def test_a_note_without_a_school_form_or_subject_holds_for_all_of_them_in_its_land(
    client: TestClient, migrated: str, tmp_path: Path
) -> None:
    notes = write_notes(
        tmp_path / "n.csv",
        note("BY", "", "", "ganz Bayern"),
        note("BY", "Gymnasium", "", "jedes Gymnasium"),
        note("BY", "Gymnasium", "Physik", "Physik am Gymnasium"),
        note("BY", "Gymnasium", "Chemie", "Chemie am Gymnasium"),
        note("BY", "Realschule", "", "jede Realschule"),
        note("HE", "", "", "ganz Hessen"),
    )
    documents = write_documents(tmp_path / "d.csv", document("BY.GYM.PH"))

    shown = notes_shown(client, migrated, documents, notes)

    assert shown == {"ganz Bayern", "jedes Gymnasium", "Physik am Gymnasium"}


@pytest.mark.pg
def test_thuringia_s_blocked_portal_shows_on_its_esa_entries(
    client: TestClient, migrated: str, tmp_path: Path
) -> None:
    # the published notes on Thuringia's ESA name no subject: they hold for every subject of it
    scope = {"Land_Kuerzel": "TH", "Land": "Thüringen", "Schulform": "Erster Schulabschluss (ESA)"}
    documents = write_documents(tmp_path / "d.csv", document("TH.ESA.MA", **scope, Fach="Mathematik"))

    shown = notes_shown(client, migrated, documents, NOTES)

    assert any(text.startswith("schulportal-thueringen.de sperrt automatisierte Abrufe") for text in shown)
    expected = {
        " ".join(row["Hinweis"].split())
        for row in published_notes()
        if (row["Land_Kuerzel"], row["Schulform"]) == ("TH", scope["Schulform"])
        and row["Fach"] in ("", "Mathematik")
        and row["Hinweis"].strip()
    }
    assert shown == expected


@pytest.mark.pg
def test_an_entry_of_no_seed_has_neither(client: TestClient, migrated: str) -> None:
    _, header = seed_account(migrated, "Lehrkraft", ["nutzer"])
    created = client.post(
        "/api/v1/sources/import", headers=header, json={"url": "https://lehrplan.example/a.pdf"}
    ).json()

    detail = client.get(f"/api/v1/sources/{created['source']['id']}", headers=header).json()

    assert (detail["seed"], detail["access_notes"]) == (None, [])
