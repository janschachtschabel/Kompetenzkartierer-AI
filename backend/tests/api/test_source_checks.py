"""Starting the check of the register's candidates, and what it found per entry (plan M1, 2.5).

An admin starts it, one check at a time: it asks 34 hosts of other people, and two would ask
each address twice. An entry shows what the check found at its address.
"""

import asyncio
import hashlib
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
from app.jobs.queue import claim
from app.sources.check_job import KIND, enqueue_check
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
URL = "https://lehrplaene.example/medien/Physik.pdf"


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
def admin(migrated: str) -> tuple[UUID, dict[str, str]]:
    return seed_account(migrated, "Admin", ["admin"])


def jobs(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(
            "SELECT id, kind, lane, status, payload FROM job ORDER BY created_at"
        ).fetchall()


def test_an_admin_starts_the_check_as_a_job(
    client: TestClient, migrated: str, admin: tuple[UUID, dict[str, str]]
) -> None:
    account, header = admin

    answer = client.post("/api/v1/sources/checks", headers=header)

    assert answer.status_code == 202
    job_id = UUID(answer.json()["job_id"])
    assert jobs(migrated) == [(job_id, KIND, str(account), "queued", {})]
    with psycopg.connect(migrated) as connection:
        audited = connection.execute(
            "SELECT actor_id, action, subject FROM audit_log WHERE action = 'source.check'"
        ).fetchall()
    assert audited == [(account, "source.check", f"job:{job_id}")]
    # the admin follows it as any job
    assert client.get(f"/api/v1/jobs/{job_id}", headers=header).json()["kind"] == KIND


@pytest.mark.parametrize("roles", [["nutzer"], ["redaktion"]])
def test_no_one_but_an_admin_starts_it(client: TestClient, migrated: str, roles: list[str]) -> None:
    _, header = seed_account(migrated, "Konto", roles)

    answer = client.post("/api/v1/sources/checks", headers=header)

    assert answer.status_code == 403
    assert jobs(migrated) == []


def test_while_a_check_waits_or_runs_no_second_starts(
    client: TestClient, migrated: str, admin: tuple[UUID, dict[str, str]]
) -> None:
    _, header = admin
    first = client.post("/api/v1/sources/checks", headers=header).json()["job_id"]

    waiting = client.post("/api/v1/sources/checks", headers=header)
    asyncio.run(take_job(migrated), loop_factory=asyncio.SelectorEventLoop)  # a worker runs it now
    running = client.post("/api/v1/sources/checks", headers=header)
    with psycopg.connect(migrated) as connection:
        connection.execute(
            "UPDATE job SET status = 'done', lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,"
            " finished_at = now() WHERE id = %s",
            (first,),
        )
    after = client.post("/api/v1/sources/checks", headers=header)

    for refused in (waiting, running):
        assert (refused.status_code, refused.json()["code"]) == (409, "check_running")
        # the check that waits or runs, for the page to follow
        assert refused.json()["details"] == {"job_id": first}
    assert after.status_code == 202


async def take_job(url: str) -> None:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as connection:
        assert await claim(connection, "w1", [KIND], 60) is not None


def test_two_starts_at_once_make_one_check(migrated: str) -> None:
    async def start() -> UUID | None:
        async with (
            await psycopg.AsyncConnection.connect(migrated) as connection,
            connection.transaction(),
        ):
            started, _ = await enqueue_check(connection, "admin")
            await asyncio.sleep(0.2)  # a while before the commit: the other waits on the lock
            return started

    async def both() -> list[UUID | None]:
        return list(await asyncio.gather(start(), start()))

    found = asyncio.run(both(), loop_factory=asyncio.SelectorEventLoop)

    assert sorted(found, key=lambda started: started is None)[1] is None
    assert len(jobs(migrated)) == 1


def test_the_spec_names_the_start_and_its_refusal() -> None:
    spec = create_app(make_settings()).openapi()
    answers = spec["paths"]["/api/v1/sources/checks"]["post"]["responses"]

    assert "202" in answers
    assert answers["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorBody"
    }


# --- what the check found, per entry


def add_candidate(url: str, address: str = URL) -> UUID:
    source_id = new_id()
    with psycopg.connect(url) as connection:
        connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (source_id,))
        connection.execute(
            "INSERT INTO source (id, provenance, url) VALUES (%s, 'vergleichsdatensatz-v62.493', %s)",
            (source_id, address),
        )
    return source_id


def test_an_entry_shows_what_the_check_found_at_its_address(
    client: TestClient, migrated: str, admin: tuple[UUID, dict[str, str]]
) -> None:
    checked, unchecked = (
        add_candidate(migrated),
        add_candidate(migrated, "https://lehrplaene.example/neu.pdf"),
    )
    with psycopg.connect(migrated) as connection:
        connection.execute(
            "INSERT INTO url_check (url_sha256, url, outcome, status_code, detected_type, size_bytes, sha256)"
            " VALUES (%s, %s, 'reachable', 200, 'pdf', 4711, %s)",
            (hashlib.sha256(URL.encode()).digest(), URL, b"\x02" * 32),
        )
    _, header = seed_account(migrated, "Lehrkraft", ["nutzer"])

    found = client.get(f"/api/v1/sources/{checked}", headers=header).json()["check"]
    none = client.get(f"/api/v1/sources/{unchecked}", headers=header).json()["check"]

    assert {key: found[key] for key in ("outcome", "status_code", "detected_type", "size")} == {
        "outcome": "reachable",
        "status_code": 200,
        "detected_type": "pdf",
        "size": 4711,
    }
    assert found["checked_at"]
    assert none is None
