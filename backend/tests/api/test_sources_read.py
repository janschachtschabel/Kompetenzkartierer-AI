"""Reading the register: who sees which entry is decided in SQL.

An account sees its own entries and those of no account (seed, research) as metadata; editors and
admins see every entry. Another account's upload is the 404 of an entry that does not exist.
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.ids import new_id
from app.db.migrate import migrate
from app.db.sources import StoredFile, record_upload
from tests.support import make_settings, seed_account, seed_admin, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


@pytest.fixture
def client(migrated: str, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(database_url=migrated, storage_dir=tmp_path))
    with selector_client(app, base_url=PUBLIC) as test_client:
        yield test_client


@pytest.fixture
def world(migrated: str) -> dict[str, Any]:
    """Two accounts with an upload each, an editor, and a seed entry of no account."""
    lehrkraft, mine = seed_account(migrated, "Lehrkraft", ["nutzer"])
    andere, theirs = seed_account(migrated, "Andere", ["nutzer"])
    _, editor = seed_account(migrated, "Redaktion", ["redaktion"])

    async def fill() -> dict[str, UUID]:
        async with await psycopg.AsyncConnection.connect(migrated, autocommit=True) as connection:
            own = await upload(connection, lehrkraft, "Lehrplan Physik", b"\x01")
            foreign = await upload(connection, andere, "Lehrplan Chemie", b"\x02")
            seed = new_id()
            await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (seed,))
            await connection.execute(
                "INSERT INTO source (id, provenance, title, url, country, source_type)"
                " VALUES (%s, 'vergleichsdatensatz-v62.493', 'Kerncurriculum Physik Bayern',"
                " 'https://www.isb.bayern.de/lp.pdf', 'DE-BY', 'amtlich')",
                (seed,),
            )
            return {"own": own, "foreign": foreign, "seed": seed}

    ids = asyncio.run(fill(), loop_factory=asyncio.SelectorEventLoop)
    return {**ids, "mine": mine, "theirs": theirs, "editor": editor}


async def upload(connection: psycopg.AsyncConnection, owner: UUID, title: str, mark: bytes) -> UUID:
    stored = StoredFile(
        sha256=mark * 32, size=4, mime="application/pdf", storage_key=f"sources/{mark.hex() * 32}"
    )
    return await record_upload(
        connection, owner=owner, stored=stored, file_name="lp.pdf", received_name="lp.pdf", title=title
    )


def titles(answer: Any) -> list[str]:
    return sorted(entry["title"] for entry in answer.json()["entries"])


def test_an_account_sees_its_own_entries_and_those_of_no_account(
    client: TestClient, world: dict[str, Any]
) -> None:
    answer = client.get("/api/v1/sources", headers=world["mine"])

    assert answer.status_code == 200
    assert titles(answer) == ["Kerncurriculum Physik Bayern", "Lehrplan Physik"]
    assert answer.json()["total"] == 2


def test_an_editor_sees_every_entry(client: TestClient, world: dict[str, Any]) -> None:
    assert titles(client.get("/api/v1/sources", headers=world["editor"])) == [
        "Kerncurriculum Physik Bayern",
        "Lehrplan Chemie",
        "Lehrplan Physik",
    ]


def test_an_admin_sees_every_entry_as_the_editors_do(
    client: TestClient, migrated: str, world: dict[str, Any]
) -> None:
    admin = seed_admin(migrated)

    listed = client.get("/api/v1/sources", headers=admin).json()
    foreign = client.get(f"/api/v1/sources/{world['foreign']}", headers=admin).json()

    assert listed["total"] == 3
    assert foreign["title"] == "Lehrplan Chemie"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ({"status": "acquired"}, ["Lehrplan Physik"]),
        ({"provenance": "vergleichsdatensatz-v62.493"}, ["Kerncurriculum Physik Bayern"]),
        ({"country": "DE-BY"}, ["Kerncurriculum Physik Bayern"]),
        ({"q": "physik"}, ["Kerncurriculum Physik Bayern", "Lehrplan Physik"]),
        ({"q": "isb.bayern"}, ["Kerncurriculum Physik Bayern"]),  # the address counts too
        # a search term's wildcards are signs, not patterns: as patterns each matched entries
        ({"q": "100%_"}, []),
        ({"q": "%"}, []),
        ({"q": "_"}, []),
        ({"q": "Lehrplan_"}, []),
    ],
)
def test_the_register_is_filtered(
    client: TestClient, world: dict[str, Any], query: dict[str, str], expected: list[str]
) -> None:
    assert titles(client.get("/api/v1/sources", headers=world["mine"], params=query)) == expected


def test_the_total_counts_what_the_filter_lets_through(client: TestClient, world: dict[str, Any]) -> None:
    page = client.get("/api/v1/sources", headers=world["editor"], params={"q": "physik", "limit": 1}).json()

    assert page["total"] == 2
    assert len(page["entries"]) == 1


def test_the_newest_entry_comes_first(client: TestClient, world: dict[str, Any]) -> None:
    entries = client.get("/api/v1/sources", headers=world["editor"]).json()["entries"]

    assert [entry["title"] for entry in entries] == [
        "Kerncurriculum Physik Bayern",
        "Lehrplan Chemie",
        "Lehrplan Physik",
    ]


def test_an_entry_says_whether_it_is_the_caller_s(client: TestClient, world: dict[str, Any]) -> None:
    entries = client.get("/api/v1/sources", headers=world["mine"]).json()["entries"]
    own = client.get(f"/api/v1/sources/{world['own']}", headers=world["mine"]).json()

    assert {entry["title"]: entry["mine"] for entry in entries} == {
        "Kerncurriculum Physik Bayern": False,
        "Lehrplan Physik": True,
    }
    assert own["mine"] is True


def test_the_register_comes_in_pages(client: TestClient, world: dict[str, Any]) -> None:
    first = client.get("/api/v1/sources", headers=world["editor"], params={"limit": 2}).json()
    rest = client.get("/api/v1/sources", headers=world["editor"], params={"limit": 2, "offset": 2}).json()

    assert first["total"] == rest["total"] == 3
    assert len(first["entries"]) == 2 and len(rest["entries"]) == 1
    assert {entry["id"] for entry in first["entries"]}.isdisjoint(entry["id"] for entry in rest["entries"])


@pytest.mark.parametrize(
    "query",
    [
        {"status": "invented"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"offset": 1_000_001},  # 10**20 ended in NumericValueOutOfRange, a 500
        {"q": "Physik\x00"},  # a NUL ended in a DataError, a 500
        {"q": "Physik\N{RIGHT-TO-LEFT OVERRIDE}"},
        {"q": "x" * 201},
    ],
    ids=["status", "limit-0", "limit-201", "offset-negative", "offset-huge", "q-nul", "q-bidi", "q-long"],
)
def test_an_unknown_filter_value_is_refused(
    client: TestClient, world: dict[str, Any], query: dict[str, Any]
) -> None:
    assert client.get("/api/v1/sources", headers=world["mine"], params=query).status_code == 422


def test_a_search_term_is_matched_in_one_spelling(
    client: TestClient, migrated: str, world: dict[str, Any]
) -> None:
    with psycopg.connect(migrated, autocommit=True) as connection:
        entry = new_id()
        connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (entry,))
        connection.execute(
            "INSERT INTO source (id, provenance, title) VALUES (%s, 'recherche', %s)",
            (entry, "Lehrplan Caf\N{LATIN SMALL LETTER E WITH ACUTE}"),
        )

    query = {"q": "Cafe\N{COMBINING ACUTE ACCENT}"}

    assert titles(client.get("/api/v1/sources", headers=world["mine"], params=query)) == [
        "Lehrplan Caf\N{LATIN SMALL LETTER E WITH ACUTE}"
    ]


def test_an_entry_shows_its_terms_and_how_its_file_came(client: TestClient, world: dict[str, Any]) -> None:
    answer = client.get(f"/api/v1/sources/{world['own']}", headers=world["mine"])

    assert answer.status_code == 200
    body = answer.json()
    assert body["title"] == "Lehrplan Physik"
    assert body["rights_status"] == "unklar" and body["license"] is None
    assert [(a["method"], a["received_name"]) for a in body["acquisitions"]] == [("upload", "lp.pdf")]
    assert body["file"]["name"] == "lp.pdf"


def test_a_seed_entry_s_metadata_is_for_every_account(client: TestClient, world: dict[str, Any]) -> None:
    body = client.get(f"/api/v1/sources/{world['seed']}", headers=world["mine"]).json()

    assert body["source_type"] == "amtlich"
    assert body["url"] == "https://www.isb.bayern.de/lp.pdf"


def test_another_account_s_upload_is_not_there(client: TestClient, world: dict[str, Any]) -> None:
    foreign = client.get(f"/api/v1/sources/{world['foreign']}", headers=world["mine"])
    missing = client.get(f"/api/v1/sources/{new_id()}", headers=world["mine"])

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_a_visitor_reads_no_register(client: TestClient, world: dict[str, Any]) -> None:
    assert client.get("/api/v1/sources").status_code == 401
    assert client.get(f"/api/v1/sources/{world['seed']}").status_code == 401
