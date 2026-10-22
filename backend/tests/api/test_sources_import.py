"""An account imports a curriculum document by its URL: a register entry now, the fetch as a job.

The answer is 202 with the job's id; the entry and the job are made in one transaction, so there
is never one without the other. The job carries the trace of the request.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.db.migrate import migrate
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
URL = "https://lehrplaene.example/medien/14629?dateiname=Physik.pdf"


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


def client_for(url: str, store: Path, **settings: Any) -> TestClient:
    return selector_client(
        create_app(make_settings(database_url=url, storage_dir=store, **settings)), base_url=PUBLIC
    )


@pytest.fixture
def client(migrated: str, tmp_path: Path) -> Iterator[TestClient]:
    with client_for(migrated, tmp_path) as test_client:
        yield test_client


@pytest.fixture
def owner(migrated: str) -> tuple[UUID, dict[str, str]]:
    return seed_account(migrated, "Lehrkraft", ["nutzer"])


def rows(url: str, query: str, *values: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, values).fetchall()


def test_an_import_makes_an_unchecked_entry_and_its_fetch_job(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner

    answer = client.post("/api/v1/sources/import", headers=header, json={"url": URL, "title": "Physik"})

    assert answer.status_code == 202
    body = answer.json()
    source_id, job_id = UUID(body["source"]["id"]), UUID(body["job_id"])
    assert body["source"]["provenance"] == "url"
    assert body["source"]["register_status"] == "unchecked"
    assert body["source"]["file"] is None
    assert rows(migrated, "SELECT owner_id, url, title FROM source WHERE id = %s", source_id) == [
        (account, URL, "Physik")
    ]
    assert rows(migrated, "SELECT kind, lane, payload FROM job WHERE id = %s", job_id) == [
        ("source.fetch", str(account), {"source_id": str(source_id)})
    ]


def test_the_owner_follows_the_fetch_by_its_job(
    client: TestClient, owner: tuple[UUID, dict[str, str]]
) -> None:
    job_id = client.post("/api/v1/sources/import", headers=owner[1], json={"url": URL}).json()["job_id"]

    assert client.get(f"/api/v1/jobs/{job_id}", headers=owner[1]).json()["kind"] == "source.fetch"


def test_the_job_carries_the_trace_of_the_request(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    headers = {**owner[1], "x-client-trace-id": "trace-of-the-import"}

    job_id = client.post("/api/v1/sources/import", headers=headers, json={"url": URL}).json()["job_id"]

    assert rows(migrated, "SELECT trace_id FROM job WHERE id = %s", UUID(job_id)) == [
        ("trace-of-the-import",)
    ]


def test_the_import_is_audited(client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]) -> None:
    body = client.post("/api/v1/sources/import", headers=owner[1], json={"url": URL}).json()

    # the host and the job only: a download link's query may carry a token
    assert rows(migrated, "SELECT subject, details FROM audit_log WHERE action = 'source.import'") == [
        (f"source:{body['source']['id']}", {"host": "lehrplaene.example", "job": body["job_id"]})
    ]


@pytest.mark.parametrize(
    "url",
    [
        "ftp://lehrplaene.example/a.pdf",
        "javascript:alert(1)",
        "https://kka:geheim@lehrplaene.example/a.pdf",
        "https://lehrplaene.example/lehr plan.pdf",
        "https://lehrplaene.example/" + "a" * 2000,
    ],
)
def test_an_address_that_cannot_be_fetched_is_refused_and_nothing_is_made(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]], url: str
) -> None:
    answer = client.post("/api/v1/sources/import", headers=owner[1], json={"url": url})

    assert answer.status_code == 422
    assert rows(migrated, "SELECT (SELECT count(*) FROM source), (SELECT count(*) FROM job)") == [(0, 0)]


def test_a_title_with_hidden_signs_is_refused(client: TestClient, owner: tuple[UUID, dict[str, str]]) -> None:
    answer = client.post("/api/v1/sources/import", headers=owner[1], json={"url": URL, "title": "Physik‮"})

    assert answer.status_code == 422


def test_a_visitor_cannot_import(client: TestClient) -> None:
    assert client.post("/api/v1/sources/import", json={"url": URL}).status_code == 401


def test_imports_past_the_account_s_limit_wait(
    migrated: str, tmp_path: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    with client_for(migrated, tmp_path, url_imports_per_minute=1) as client:
        answers = [
            client.post("/api/v1/sources/import", headers=owner[1], json={"url": URL}) for _ in range(2)
        ]

    assert [answer.status_code for answer in answers] == [202, 429]
    assert answers[1].json()["code"] == "too_many_imports"
    assert 1 <= int(answers[1].headers["Retry-After"]) <= 60
