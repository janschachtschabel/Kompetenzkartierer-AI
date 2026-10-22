"""The dataset's notes on blocked portals and detours become access notes (plan M1, 2.3).

A note belongs to a land, school form and subject; a register entry seeded with the same three
shows it. The rule stays ours (Gesamtplan §7.5): official sources first, an archive as one,
a mirror marked; a technical barrier is never got round.
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


@pytest.mark.pg
def test_an_entry_of_no_seed_has_neither(client: TestClient, migrated: str) -> None:
    _, header = seed_account(migrated, "Lehrkraft", ["nutzer"])
    created = client.post(
        "/api/v1/sources/import", headers=header, json={"url": "https://lehrplan.example/a.pdf"}
    ).json()

    detail = client.get(f"/api/v1/sources/{created['source']['id']}", headers=header).json()

    assert (detail["seed"], detail["access_notes"]) == (None, [])
