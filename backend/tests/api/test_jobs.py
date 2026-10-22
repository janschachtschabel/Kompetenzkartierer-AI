"""A job's state for whoever started it: status, progress, error code - and a cancel.

A job's lane is the account that started it. Another account learns nothing of it, not even
that it exists (404 as for none); an admin sees and cancels every job.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.db.migrate import migrate
from app.jobs.queue import enqueue
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
UNKNOWN = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


@pytest.fixture
def client(migrated: str) -> Iterator[TestClient]:
    with selector_client(create_app(make_settings(database_url=migrated)), base_url=PUBLIC) as test_client:
        yield test_client


@pytest.fixture
def owner(migrated: str) -> tuple[UUID, dict[str, str]]:
    return seed_account(migrated, "Lehrkraft", ["nutzer"])


@pytest.fixture
def stranger(migrated: str) -> dict[str, str]:
    return seed_account(migrated, "Andere", ["nutzer"])[1]


@pytest.fixture
def admin(migrated: str) -> dict[str, str]:
    return seed_account(migrated, "Admin", ["admin"])[1]


def add_job(url: str, lane: str, **columns: Any) -> UUID:
    async def add() -> UUID:
        async with await psycopg.AsyncConnection.connect(url, autocommit=True) as connection:
            job_id = await enqueue(connection, "source.fetch", lane, {"url": "https://example.org/a.pdf"})
            if columns:  # in one statement: a running job needs its lease in the same row
                assignments = ", ".join(f"{name} = %s" for name in columns)
                await connection.execute(
                    f"UPDATE job SET {assignments} WHERE id = %s",  # noqa: S608 - the test's own names
                    (*columns.values(), job_id),
                )
            return job_id

    return asyncio.run(add(), loop_factory=asyncio.SelectorEventLoop)


def test_the_owner_sees_the_state_of_the_job(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner
    job_id = add_job(migrated, str(account))

    answer = client.get(f"/api/v1/jobs/{job_id}", headers=header)

    assert answer.status_code == 200
    body = answer.json()
    assert body["id"] == str(job_id)
    assert body["kind"] == "source.fetch"
    assert body["status"] == "queued"
    assert body["progress"] is None
    assert body["error_code"] is None
    assert body["cancel_requested"] is False
    assert "payload" not in body and "lane" not in body


def test_progress_and_the_error_code_come_through_not_the_message(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner
    job_id = add_job(
        migrated,
        str(account),
        status="failed",
        progress=psycopg.types.json.Jsonb({"code": "fetching", "params": {"bytes": 1024}}),
        error=psycopg.types.json.Jsonb({"code": "not_a_pdf", "message": "words a handler chose"}),
    )

    body = client.get(f"/api/v1/jobs/{job_id}", headers=header).json()

    assert body["status"] == "failed"
    assert body["progress"] == {"code": "fetching", "params": {"bytes": 1024}}
    assert body["error_code"] == "not_a_pdf"
    assert "words a handler chose" not in str(body)


def test_another_account_learns_nothing_of_the_job(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]], stranger: dict[str, str]
) -> None:
    job_id = add_job(migrated, str(owner[0]))

    foreign = client.get(f"/api/v1/jobs/{job_id}", headers=stranger)
    missing = client.get(f"/api/v1/jobs/{UNKNOWN}", headers=stranger)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["message"] == missing.json()["message"]


def test_an_admin_sees_every_job(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]], admin: dict[str, str]
) -> None:
    job_id = add_job(migrated, str(owner[0]))

    assert client.get(f"/api/v1/jobs/{job_id}", headers=admin).status_code == 200


def test_a_visitor_needs_a_token(client: TestClient, migrated: str) -> None:
    job_id = add_job(migrated, "system")

    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 401


def test_the_owner_cancels_a_waiting_job(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner
    job_id = add_job(migrated, str(account))

    answer = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=header)

    assert answer.status_code == 200
    assert answer.json()["status"] == "cancelled"
    assert answer.json()["cancel_requested"] is True


def test_a_running_job_is_asked_to_stop(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    # the worker learns of it at its next heartbeat and cancels the handler
    account, header = owner
    job_id = add_job(
        migrated,
        str(account),
        status="running",
        lease_owner="w1",
        lease_token=UUID("11111111-1111-4111-8111-111111111111"),
        lease_expires_at="2999-01-01",
    )

    body = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=header).json()

    assert body["status"] == "running"
    assert body["cancel_requested"] is True


def test_only_its_owner_or_an_admin_cancels_a_job(
    client: TestClient,
    migrated: str,
    owner: tuple[UUID, dict[str, str]],
    stranger: dict[str, str],
    admin: dict[str, str],
) -> None:
    job_id = add_job(migrated, str(owner[0]))

    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=stranger).status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}", headers=owner[1]).json()["status"] == "queued"
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=admin).status_code == 200


def cancels_audited(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(
            "SELECT actor_id, action, subject, details FROM audit_log WHERE action = 'job.cancel'"
        ).fetchall()


def test_a_cancel_is_audited_and_a_refused_one_is_not(
    client: TestClient,
    migrated: str,
    owner: tuple[UUID, dict[str, str]],
    stranger: dict[str, str],
) -> None:
    account, header = owner
    job_id = add_job(migrated, str(account))
    ended = add_job(migrated, str(account), status="done")

    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=stranger).status_code == 404
    assert client.post(f"/api/v1/jobs/{ended}/cancel", headers=header).status_code == 409
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=header).status_code == 200

    assert cancels_audited(migrated) == [(account, "job.cancel", f"job:{job_id}", {"kind": "source.fetch"})]


def test_an_ended_job_cannot_be_cancelled(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner
    job_id = add_job(migrated, str(account), status="done")

    answer = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=header)

    assert answer.status_code == 409
    assert answer.json()["code"] == "conflict"
