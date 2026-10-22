"""Keeping the register: editors set the terms of use, an owner the description of its entry; the
file goes out as a download, to whom THIRD_PARTY_MARKDOWN allows.
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
from app.core.storage import FileSystemStorage
from app.db.migrate import migrate
from app.db.sources import StoredFile, record_upload
from app.sources.register import EDUCATION_SECTORS
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
PDF = b"%PDF-1.7 Lehrplan"
SECTOR = "https://w3id.org/wlo/curriculum/vocab#sec_school"


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as connection:
        # the sector scheme as app.vocab.load leaves it, cut to one concept
        connection.execute(
            "INSERT INTO vocab_scheme (iri, types, pref_labels, properties) VALUES (%s, '{}', '{}', '{}')",
            (EDUCATION_SECTORS,),
        )
        connection.execute(
            "INSERT INTO vocab_concept (iri, scheme_iri, types, notation, pref_labels, alt_labels,"
            " definitions, broader, properties)"
            " VALUES (%s, %s, '{}', 'school', '{}', '{}', '{}', '{}', '{}')",
            (SECTOR, EDUCATION_SECTORS),
        )
    return database_url


def client_for(url: str, store: Path, **settings: Any) -> TestClient:
    return selector_client(
        create_app(make_settings(database_url=url, storage_dir=store, **settings)), base_url=PUBLIC
    )


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "store"


@pytest.fixture
def client(migrated: str, store: Path) -> Iterator[TestClient]:
    with client_for(migrated, store) as test_client:
        yield test_client


@pytest.fixture
def world(migrated: str, store: Path) -> dict[str, Any]:
    """An owner's upload and a seed entry with a file, both holding PDF; another account; an editor."""
    owner_id, owner = seed_account(migrated, "Lehrkraft", ["nutzer"])
    _, other = seed_account(migrated, "Andere", ["nutzer"])
    _, editor = seed_account(migrated, "Redaktion", ["redaktion"])
    stored = StoredFile(
        sha256=b"\x07" * 32, size=len(PDF), mime="application/pdf", storage_key="sources/" + "07" * 32
    )
    FileSystemStorage(store).put(stored.storage_key, PDF)

    async def fill() -> dict[str, UUID]:
        async with await psycopg.AsyncConnection.connect(migrated, autocommit=True) as connection:
            own = await record_upload(
                connection,
                owner=owner_id,
                stored=stored,
                file_name="Lehrplan Ä.pdf",
                received_name="x",
                title="Mein",
            )
            seed = new_id()
            await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (seed,))
            await connection.execute(
                "INSERT INTO source (id, provenance, title, register_status, file_id, file_name, mime)"
                " SELECT %s, 'vergleichsdatensatz-v62.493', 'Saat', 'acquired', id, 'saat.pdf',"
                " 'application/pdf' FROM source_file",
                (seed,),
            )
            return {"own": own, "seed": seed}

    ids = asyncio.run(fill(), loop_factory=asyncio.SelectorEventLoop)
    return {**ids, "owner": owner, "other": other, "editor": editor}


def row(url: str, source_id: UUID) -> dict[str, Any]:
    with psycopg.connect(url, row_factory=psycopg.rows.dict_row) as connection:
        found = connection.execute("SELECT * FROM source WHERE id = %s", (source_id,)).fetchone()
    assert found is not None
    return found


# --- editing


def test_an_editor_sets_the_terms_of_use_with_their_evidence(
    client: TestClient, migrated: str, world: dict[str, Any]
) -> None:
    change = {
        "rights_status": "amtlich",
        "rights_evidence": "Amtsblatt des StMUK 2023, S. 12",
        "source_type": "amtlich",
        "license": "amtliches Werk, § 5 UrhG",
    }

    answer = client.patch(f"/api/v1/sources/{world['seed']}", headers=world["editor"], json=change)

    assert answer.status_code == 200
    assert {key: answer.json()[key] for key in change} == change
    stored = row(migrated, world["seed"])
    assert (stored["rights_status"], stored["source_type"]) == ("amtlich", "amtlich")


def test_a_rights_status_needs_its_evidence(client: TestClient, world: dict[str, Any]) -> None:
    answer = client.patch(
        f"/api/v1/sources/{world['seed']}", headers=world["editor"], json={"rights_status": "amtlich"}
    )

    assert answer.status_code == 422
    assert answer.json()["code"] == "evidence_missing"


def terms_of(url: str, source_id: UUID) -> tuple[str, str | None]:
    stored = row(url, source_id)
    return stored["rights_status"], stored["rights_evidence"]


def test_a_rights_status_is_never_cleared(client: TestClient, migrated: str, world: dict[str, Any]) -> None:
    answer = client.patch(
        f"/api/v1/sources/{world['seed']}", headers=world["editor"], json={"rights_status": None}
    )

    assert answer.status_code == 422
    assert terms_of(migrated, world["seed"]) == ("unklar", None)


@pytest.mark.parametrize(
    "change",
    [{"rights_evidence": None}, {"rights_status": "geschuetzt", "rights_evidence": None}],
    ids=["evidence-removed", "status-changed-evidence-removed"],
)
def test_a_rights_status_keeps_its_evidence(
    client: TestClient, migrated: str, world: dict[str, Any], change: dict[str, Any]
) -> None:
    # the rule holds for what the entry would be, not for the fields sent
    terms = {"rights_status": "amtlich", "rights_evidence": "Amtsblatt 2023"}
    client.patch(f"/api/v1/sources/{world['seed']}", headers=world["editor"], json=terms)

    answer = client.patch(f"/api/v1/sources/{world['seed']}", headers=world["editor"], json=change)

    assert answer.status_code == 422
    assert answer.json()["code"] == "evidence_missing"
    assert terms_of(migrated, world["seed"]) == ("amtlich", "Amtsblatt 2023")


def test_an_owner_describes_its_entry(client: TestClient, migrated: str, world: dict[str, Any]) -> None:
    change = {"title": "Lehrplan Physik", "country": "DE-BY", "sector": "school"}

    answer = client.patch(f"/api/v1/sources/{world['own']}", headers=world["owner"], json=change)

    assert answer.status_code == 200
    assert answer.json()["sector"] == SECTOR
    stored = row(migrated, world["own"])
    assert (stored["title"], stored["country"], stored["sector_iri"]) == ("Lehrplan Physik", "DE-BY", SECTOR)


@pytest.mark.parametrize(
    "field", [{"rights_status": "amtlich", "rights_evidence": "x"}, {"license": "CC BY"}]
)
def test_an_owner_does_not_set_the_terms_of_use(
    client: TestClient, world: dict[str, Any], field: dict[str, str]
) -> None:
    assert (
        client.patch(f"/api/v1/sources/{world['own']}", headers=world["owner"], json=field).status_code == 403
    )


def test_an_account_does_not_edit_an_entry_it_only_reads(client: TestClient, world: dict[str, Any]) -> None:
    seed = client.patch(f"/api/v1/sources/{world['seed']}", headers=world["owner"], json={"title": "Andere"})
    foreign = client.patch(
        f"/api/v1/sources/{world['own']}", headers=world["other"], json={"title": "Andere"}
    )

    assert seed.status_code == 403
    assert foreign.status_code == 404


@pytest.mark.parametrize(
    "change",
    [{}, {"sector": "invented"}, {"country": "Bayern"}, {"title": "Physik‮"}, {"provenance": "upload"}],
    ids=["nothing", "unknown-sector", "no-iso-country", "hidden-signs", "not-editable"],
)
def test_a_change_the_register_cannot_hold_is_refused(
    client: TestClient, world: dict[str, Any], change: dict[str, str]
) -> None:
    assert (
        client.patch(f"/api/v1/sources/{world['own']}", headers=world["owner"], json=change).status_code
        == 422
    )


def test_an_edit_is_audited(client: TestClient, migrated: str, world: dict[str, Any]) -> None:
    client.patch(f"/api/v1/sources/{world['own']}", headers=world["owner"], json={"title": "Neu"})

    with psycopg.connect(migrated) as connection:
        audited = connection.execute(
            "SELECT subject, details FROM audit_log WHERE action = 'source.edit'"
        ).fetchall()
    assert audited == [(f"source:{world['own']}", {"fields": ["title"]})]


# --- the file


def test_the_owner_gets_its_file_as_a_download(client: TestClient, world: dict[str, Any]) -> None:
    answer = client.get(f"/api/v1/sources/{world['own']}/file", headers=world["owner"])

    assert answer.status_code == 200
    assert answer.content == PDF
    assert answer.headers["content-type"] == "application/pdf"
    assert answer.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''Lehrplan%20%C3%84.pdf" in answer.headers["content-disposition"]
    assert answer.headers["x-content-type-options"] == "nosniff"


def test_a_file_of_no_account_is_hidden_from_accounts_by_default(
    client: TestClient, world: dict[str, Any]
) -> None:
    assert client.get(f"/api/v1/sources/{world['seed']}/file", headers=world["other"]).status_code == 403
    assert client.get(f"/api/v1/sources/{world['seed']}/file", headers=world["editor"]).status_code == 200


def test_third_party_files_may_be_opened_to_accounts(
    migrated: str, store: Path, world: dict[str, Any]
) -> None:
    with client_for(migrated, store, third_party_markdown="accounts") as client:
        assert client.get(f"/api/v1/sources/{world['seed']}/file", headers=world["other"]).status_code == 200
        assert client.get(f"/api/v1/sources/{world['seed']}/file").status_code == 401


def test_third_party_files_may_be_opened_to_visitors(
    migrated: str, store: Path, world: dict[str, Any]
) -> None:
    with client_for(migrated, store, third_party_markdown="public") as client:
        assert client.get(f"/api/v1/sources/{world['seed']}/file").status_code == 200
        # an account's own upload stays its own
        assert client.get(f"/api/v1/sources/{world['own']}/file").status_code == 401


def test_another_account_s_file_is_not_there(client: TestClient, world: dict[str, Any]) -> None:
    assert client.get(f"/api/v1/sources/{world['own']}/file", headers=world["other"]).status_code == 404


def test_an_entry_without_a_file_has_none_to_give(
    client: TestClient, migrated: str, world: dict[str, Any]
) -> None:
    with psycopg.connect(migrated, autocommit=True) as connection:
        empty = new_id()
        connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (empty,))
        connection.execute(
            "INSERT INTO source (id, provenance, title) VALUES (%s, 'recherche', 'ohne Datei')", (empty,)
        )

    answer = client.get(f"/api/v1/sources/{empty}/file", headers=world["editor"])

    assert answer.status_code == 404
    assert answer.json()["code"] == "no_file"
