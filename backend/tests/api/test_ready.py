"""/ready: 200 when the database answers and has every migration of this code, 503 otherwise."""

import time

import psycopg
import pytest

from app.api.app import create_app
from app.api.internal import READY_TIMEOUT_S
from app.db.migrate import migrate
from tests.support import make_settings, selector_client

INTERNAL = "http://testserver:9000"


def ready(database_url: str) -> tuple[int, dict[str, object]]:
    app = create_app(make_settings(database_url=database_url))
    with selector_client(app, base_url=INTERNAL) as client:
        response = client.get("/ready")
    return response.status_code, response.json()


def test_without_a_reachable_database_ready_answers_503_in_time() -> None:
    app = create_app(make_settings(database_url="postgresql://kka:fake@127.0.0.1:1/kka"))
    with selector_client(app, base_url=INTERNAL) as client:
        started = time.monotonic()
        response = client.get("/ready")
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason": "database"}
    assert elapsed < READY_TIMEOUT_S + 2


def test_health_does_not_need_the_database() -> None:
    app = create_app(make_settings(database_url="postgresql://kka:fake@127.0.0.1:1/kka"))

    with selector_client(app, base_url=INTERNAL) as client:
        assert client.get("/health").status_code == 200


@pytest.mark.pg
def test_an_empty_database_is_not_ready(database_url: str) -> None:
    assert ready(database_url) == (503, {"status": "unavailable", "reason": "migration"})


@pytest.mark.pg
def test_a_migrated_database_is_ready(database_url: str) -> None:
    migrate(database_url)

    assert ready(database_url) == (200, {"status": "ready"})


@pytest.mark.pg
def test_a_database_ahead_of_the_code_is_ready(database_url: str) -> None:
    # a rolling update: the new release migrated, the old pods keep serving
    migrate(database_url)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum) VALUES (999, '0999_next.sql', %s)",
            ("0" * 64,),
        )

    assert ready(database_url) == (200, {"status": "ready"})


@pytest.mark.pg
def test_a_database_that_does_not_answer_in_time_is_not_ready(database_url: str) -> None:
    # another session holds the bookkeeping table: the query waits, the probe must not
    migrate(database_url)
    app = create_app(make_settings(database_url=database_url))
    with psycopg.connect(database_url) as holder, selector_client(app, base_url=INTERNAL) as client:
        holder.execute("LOCK TABLE schema_migration IN ACCESS EXCLUSIVE MODE")
        started = time.monotonic()
        response = client.get("/ready")
        elapsed = time.monotonic() - started
        holder.rollback()

    assert response.status_code == 503
    assert elapsed < READY_TIMEOUT_S + 2


@pytest.mark.pg
def test_ready_survives_connections_a_database_restart_cut(database_url: str) -> None:
    migrate(database_url)
    app = create_app(make_settings(database_url=database_url, db_pool_min_size=1))
    with selector_client(app, base_url=INTERNAL) as client:
        assert client.get("/ready").status_code == 200
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                " WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )

        statuses = [client.get("/ready").status_code for _ in range(3)]

    assert statuses == [200, 200, 200]
