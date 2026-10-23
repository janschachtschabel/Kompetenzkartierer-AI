"""A register entry's conversion: asked for, followed, and read page by page (plan M1, 3.6).

Who may ask and read is who may read the entry's file (app/api/source_content.py). The conversion
belongs to the file, shared by its SHA-256: an entry of another account holding the same file
finds the same one.
"""

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool

from app.api import conversions
from app.api.app import create_app
from app.conversion.job import KIND, convert_source
from app.core.ids import new_id
from app.core.storage import FileSystemStorage
from app.core.storage_async import AsyncStorage
from app.db.conversions import conversion_for
from app.db.migrate import migrate
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import claim
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
FIXTURES = Path(__file__).resolve().parents[1] / "conversion" / "fixtures"
PROSE = (FIXTURES / "prose.pdf").read_bytes()


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


def client_for(url: str, store: Path, **settings: Any) -> Iterator[TestClient]:
    app = create_app(make_settings(database_url=url, storage_dir=store, **settings))
    with selector_client(app, base_url=PUBLIC) as test_client:
        yield test_client


@pytest.fixture
def client(migrated: str, tmp_path: Path) -> Iterator[TestClient]:
    yield from client_for(migrated, tmp_path)


@pytest.fixture
def owner(migrated: str) -> tuple[UUID, dict[str, str]]:
    return seed_account(migrated, "Lehrkraft", ["nutzer"])


def upload(
    client: TestClient, header: dict[str, str], data: bytes = PROSE, name: str = "lehrplan.pdf"
) -> str:
    answer = client.post("/api/v1/sources", headers=header, files={"file": (name, data)})
    assert answer.status_code == 201, answer.text
    return str(answer.json()["id"])


def run_the_job(url: str, store: Path) -> dict[str, Any] | PermanentError:
    """What a worker does with the waiting conversion now."""

    async def run() -> dict[str, Any] | PermanentError:
        async with AsyncConnectionPool(url, min_size=1, max_size=2, open=False) as pool:
            context = JobContext(
                pool, AsyncStorage(FileSystemStorage(store)), make_settings(database_url=url)
            )
            async with pool.connection() as connection:
                job = await claim(connection, "w1", [KIND], 60)
            assert job is not None
            try:
                return await convert_source(context, job)
            except PermanentError as error:
                return error

    return asyncio.run(run(), loop_factory=asyncio.SelectorEventLoop)


def jobs(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(
            "SELECT id, kind, lane, payload FROM job WHERE kind = %s", (KIND,)
        ).fetchall()


def ownerless(url: str, store: Path, data: bytes = PROSE) -> str:
    """An entry of no account holding a file, as an acquired candidate of the research would."""
    source_id, file_id = new_id(), new_id()
    key = f"sources/{file_id.hex}"
    FileSystemStorage(store).put(key, data)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, %s, %s)",
            (file_id, new_id().bytes * 2, len(data), key),
        )
        connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (source_id,))
        connection.execute(
            "INSERT INTO source (id, provenance, title, file_id, file_name, mime, register_status)"
            " VALUES (%s, 'laenderrecherche', 'Bildungsplan', %s, 'plan.pdf', 'application/pdf', 'acquired')",
            (source_id, file_id),
        )
    return str(source_id)


def test_an_owner_asks_for_the_conversion_of_a_pdf_as_a_job(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner
    source_id = upload(client, header)

    answer = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)

    assert answer.status_code == 202
    body = answer.json()
    assert (body["status"], body["engine"], body["pages"]) == ("pending", "pdfplumber", None)
    assert jobs(migrated) == [(UUID(body["job_id"]), KIND, str(account), {"conversion_id": body["id"]})]
    with psycopg.connect(migrated) as connection:
        audited = connection.execute(
            "SELECT actor_id, action, subject FROM audit_log WHERE action = 'source.convert'"
        ).fetchall()
    assert audited == [(account, "source.convert", f"source:{source_id}")]


def test_asked_again_while_it_waits_the_same_conversion_comes_back(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    source_id = upload(client, header)
    first = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header).json()

    again = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)

    assert again.status_code == 200
    assert (again.json()["id"], again.json()["job_id"]) == (first["id"], first["job_id"])
    assert len(jobs(migrated)) == 1


def test_a_conversion_done_is_read_page_by_page(
    client: TestClient, migrated: str, tmp_path: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    source_id = upload(client, header)
    client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)
    run_the_job(migrated, tmp_path)

    state = client.get(f"/api/v1/sources/{source_id}/conversion", headers=header).json()
    first = client.get(f"/api/v1/sources/{source_id}/conversion/blocks", params={"page": 1}, headers=header)
    second = client.get(f"/api/v1/sources/{source_id}/conversion/blocks", params={"page": 2}, headers=header)
    beyond = client.get(f"/api/v1/sources/{source_id}/conversion/blocks", params={"page": 3}, headers=header)
    asked_again = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)

    assert (state["status"], state["pages"], state["printed_pages"], state["findings"]) == (
        "done",
        2,
        [None, None],
        [],
    )
    assert first.status_code == 200
    page = first.json()
    assert (page["page"], page["printed_page"], len(page["blocks"])) == (1, None, 6)
    assert page["blocks"][0] | {"bbox": None} == {
        "id": "p1-b1",
        "page": 1,
        "kind": "text",
        "text": "1 Lernfeld Steuerungstechnik",
        "bbox": None,
        "font_size": 14.0,
        "bold": True,
        "italic": False,
        "cells": [],
    }
    assert [block["id"] for block in second.json()["blocks"]] == ["p2-b1"]
    assert (beyond.status_code, beyond.json()["code"]) == (404, "no_such_page")
    assert (asked_again.status_code, asked_again.json()["status"]) == (200, "done")


def test_before_any_conversion_and_before_it_is_done_the_entry_says_so(
    client: TestClient, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    source_id = upload(client, header)

    none = client.get(f"/api/v1/sources/{source_id}/conversion", headers=header)
    client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)
    waiting = client.get(f"/api/v1/sources/{source_id}/conversion/blocks", params={"page": 1}, headers=header)

    assert (none.status_code, none.json()["code"]) == (404, "no_conversion")
    assert (waiting.status_code, waiting.json()["code"]) == (409, "not_converted")


def test_a_conversion_that_failed_says_why_and_may_be_asked_again(
    client: TestClient, migrated: str, tmp_path: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    source_id = upload(client, header, (FIXTURES / "scan.pdf").read_bytes())
    first = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header).json()
    run_the_job(migrated, tmp_path)

    state = client.get(f"/api/v1/sources/{source_id}/conversion", headers=header).json()
    again = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)

    assert (state["status"], state["error_code"]) == ("failed", "needs_ocr")
    assert again.status_code == 202
    assert again.json()["id"] == first["id"] and again.json()["job_id"] != first["job_id"]


def test_an_account_starts_as_many_conversions_a_minute_as_the_service_takes(
    migrated: str, tmp_path: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    for client in client_for(migrated, tmp_path, conversions_per_minute=1):
        first = upload(client, header)
        second = upload(client, header, (FIXTURES / "tables.pdf").read_bytes())

        started = client.post(f"/api/v1/sources/{first}/conversions", headers=header)
        asked_again = client.post(f"/api/v1/sources/{first}/conversions", headers=header)  # starts nothing
        refused = client.post(f"/api/v1/sources/{second}/conversions", headers=header)

        assert (started.status_code, asked_again.status_code) == (202, 200)
        assert (refused.status_code, refused.json()["code"]) == (429, "too_many_conversions")
        assert int(refused.headers["retry-after"]) >= 1
        assert len(jobs(migrated)) == 1


def test_only_a_pdf_is_converted(client: TestClient, owner: tuple[UUID, dict[str, str]]) -> None:
    _, header = owner
    source_id = upload(client, header, b"# Lehrplan\n\nLernfeld 1", name="lehrplan.md")

    answer = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)

    assert (answer.status_code, answer.json()["code"]) == (422, "not_pdf")


def test_an_entry_without_a_file_has_nothing_to_convert(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    imported = client.post(
        "/api/v1/sources/import", headers=header, json={"url": "https://lehrplaene.example/lp.pdf"}
    ).json()

    answer = client.post(f"/api/v1/sources/{imported['source']['id']}/conversions", headers=header)

    assert (answer.status_code, answer.json()["code"]) == (404, "no_file")


def test_another_account_holding_the_same_file_finds_the_same_conversion_but_not_its_job(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    first = client.post(f"/api/v1/sources/{upload(client, header)}/conversions", headers=header).json()
    _, other = seed_account(migrated, "Kollegin", ["nutzer"])
    _, admin = seed_account(migrated, "Betrieb", ["admin"])
    twin = upload(client, other)  # the same bytes: the same file

    asked = client.post(f"/api/v1/sources/{twin}/conversions", headers=other)
    read = client.get(f"/api/v1/sources/{twin}/conversion", headers=other).json()
    by_admin = client.get(f"/api/v1/sources/{twin}/conversion", headers=admin).json()

    assert asked.status_code == 200 and asked.json()["id"] == first["id"]
    # the job is the first account's: another one could neither follow nor cancel it (app/api/jobs.py)
    assert (asked.json()["job_id"], read["job_id"]) == (None, None)
    assert by_admin["job_id"] == first["job_id"]
    assert len(jobs(migrated)) == 1


def test_another_account_s_upload_is_no_entry_of_its_conversion(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    _, header = owner
    source_id = upload(client, header)
    _, stranger = seed_account(migrated, "Fremd", ["nutzer"])

    for answer in (
        client.post(f"/api/v1/sources/{source_id}/conversions", headers=stranger),
        client.get(f"/api/v1/sources/{source_id}/conversion", headers=stranger),
        client.get(f"/api/v1/sources/{source_id}/conversion/blocks", params={"page": 1}, headers=stranger),
    ):
        assert answer.status_code == 404


@pytest.mark.parametrize(
    ("opened_to", "roles", "status"),
    [
        ("hidden", ["nutzer"], 403),
        ("hidden", ["redaktion"], 202),
        ("accounts", ["nutzer"], 202),
    ],
)
def test_an_entry_of_no_account_is_converted_for_whom_its_file_is_open(
    migrated: str, tmp_path: Path, opened_to: str, roles: list[str], status: int
) -> None:
    source_id = ownerless(migrated, tmp_path)
    _, header = seed_account(migrated, "Konto", roles)

    for client in client_for(migrated, tmp_path, third_party_markdown=opened_to):
        answer = client.post(f"/api/v1/sources/{source_id}/conversions", headers=header)

        assert answer.status_code == status
        if status == 403:
            assert answer.json()["code"] == "file_hidden"


def test_the_conversion_of_an_entry_of_no_account_is_read_by_whom_its_file_is_open(
    migrated: str, tmp_path: Path
) -> None:
    source_id = ownerless(migrated, tmp_path)
    _, editor = seed_account(migrated, "Redaktion", ["redaktion"])
    _, user = seed_account(migrated, "Konto", ["nutzer"])
    for client in client_for(migrated, tmp_path):
        client.post(f"/api/v1/sources/{source_id}/conversions", headers=editor)
    run_the_job(migrated, tmp_path)
    paths = [
        f"/api/v1/sources/{source_id}/conversion",
        f"/api/v1/sources/{source_id}/conversion/blocks?page=1",
    ]

    for client in client_for(migrated, tmp_path, third_party_markdown="hidden"):
        hidden = [client.get(path, headers=user) for path in paths]
    for client in client_for(migrated, tmp_path, third_party_markdown="public", public_access="lookup"):
        public = [client.get(path) for path in paths]  # a visitor, without a token

    assert [(answer.status_code, answer.json()["code"]) for answer in hidden] == [(403, "file_hidden")] * 2
    assert [answer.status_code for answer in public] == [200, 200]
    assert public[0].json()["job_id"] is None and public[1].json()["blocks"]


def test_two_asking_at_once_start_one_conversion(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, header = owner
    source_id = upload(client, header)

    async def slowly(*args: Any) -> Any:
        found = await conversion_for(*args)
        await asyncio.sleep(0.3)  # both would have read "none" before either started one
        return found

    monkeypatch.setattr(conversions, "conversion_for", slowly)
    with ThreadPoolExecutor(2) as pool:
        answers = list(
            pool.map(
                lambda _: client.post(f"/api/v1/sources/{source_id}/conversions", headers=header), range(2)
            )
        )

    assert sorted(answer.status_code for answer in answers) == [200, 202]
    assert answers[0].json()["id"] == answers[1].json()["id"]
    assert len(jobs(migrated)) == 1
    with psycopg.connect(migrated) as connection:
        found = connection.execute("SELECT count(*) FROM entity WHERE kind = 'conversion'").fetchone()
    assert found == (1,)


def test_a_visitor_asks_for_no_conversion(client: TestClient, migrated: str, tmp_path: Path) -> None:
    source_id = ownerless(migrated, tmp_path)

    assert client.post(f"/api/v1/sources/{source_id}/conversions").status_code == 401


@pytest.mark.parametrize(
    ("path", "options"),
    [
        ("conversions", {"json": {"engine": "docling"}}),
        ("conversion/blocks", {"params": {"page": 0}}),
    ],
    ids=["unknown-engine", "page-zero"],
)
def test_what_names_no_engine_or_page_is_refused(
    client: TestClient, owner: tuple[UUID, dict[str, str]], path: str, options: dict[str, Any]
) -> None:
    _, header = owner
    source_id = upload(client, header)
    call = client.post if path == "conversions" else client.get

    assert call(f"/api/v1/sources/{source_id}/{path}", headers=header, **options).status_code == 422
