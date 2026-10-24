"""One open job of a key (plan M1 7a, F1): a job may carry a unique key; two jobs waiting or
running never share one, and a key is free again once its job has ended - an extraction runs at
most once at a time for its document."""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import migrate

pytestmark = pytest.mark.pg


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        opened.execute("INSERT INTO job_lane (lane) VALUES ('system') ON CONFLICT DO NOTHING")
        yield opened


def add_job(connection: psycopg.Connection, key: str | None, status: str = "queued") -> uuid.UUID:
    job_id = uuid.uuid4()
    running = status == "running"
    connection.execute(
        "INSERT INTO job (id, kind, lane, status, unique_key, lease_owner, lease_token, lease_expires_at)"
        " VALUES (%s, 'extract.run', 'system', %s, %s, %s, %s,"
        " CASE WHEN %s THEN now() + interval '1 minute' END)",
        (job_id, status, key, "w1" if running else None, uuid.uuid4() if running else None, running),
    )
    return job_id


@pytest.mark.parametrize("second", ["queued", "running"])
@pytest.mark.parametrize("first", ["queued", "running"])
def test_two_open_jobs_never_share_a_key(connection: psycopg.Connection, first: str, second: str) -> None:
    add_job(connection, "extract.run:d1", first)

    with pytest.raises(errors.UniqueViolation):
        add_job(connection, "extract.run:d1", second)


@pytest.mark.parametrize("ended", ["done", "failed", "cancelled"])
def test_a_key_is_free_again_once_its_job_has_ended(connection: psycopg.Connection, ended: str) -> None:
    job_id = add_job(connection, "extract.run:d1")
    connection.execute("UPDATE job SET status = %s, finished_at = now() WHERE id = %s", (ended, job_id))

    add_job(connection, "extract.run:d1")
    add_job(connection, "extract.run:d2")  # another key: no matter

    counted = connection.execute("SELECT count(*) FROM job WHERE unique_key = 'extract.run:d1'").fetchone()
    assert counted == (2,)


def test_jobs_without_a_key_are_any_number(connection: psycopg.Connection) -> None:
    for _ in range(3):
        add_job(connection, None)

    assert connection.execute("SELECT count(*) FROM job WHERE unique_key IS NULL").fetchone() == (3,)


@pytest.mark.parametrize("key", ["", "k" * 201], ids=["empty", "too-long"])
def test_a_key_is_one_to_two_hundred_signs(connection: psycopg.Connection, key: str) -> None:
    add_job(connection, "k" * 200)

    with pytest.raises(errors.CheckViolation):
        add_job(connection, key)
