"""The check job's tables (migration 0010, plan M1, 2.5): what it found at each address, keyed by
the address's SHA-256, and when each host may next be asked."""

import hashlib
import re
from collections.abc import Iterator
from typing import Any, get_args

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import migrate
from app.sources.register import CheckOutcome, DetectedKind

pytestmark = pytest.mark.pg

URL = "https://lehrplaene.example/medien/Physik.pdf"


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        yield opened


def add_check(connection: psycopg.Connection, url: str = URL, **columns: Any) -> None:
    values = {
        "url_sha256": hashlib.sha256(url.encode()).digest(),
        "url": url,
        "outcome": "reachable",
        "status_code": 200,
        "size_bytes": 4,
        "sha256": b"\x01" * 32,
        **columns,
    }
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO url_check ({names}) VALUES ({marks})",  # noqa: S608 - the test's own names
        tuple(values.values()),
    )


def listed_values(connection: psycopg.Connection, column: str) -> set[str]:
    found = connection.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'url_check'::regclass"
        " AND conname = %s",
        (f"url_check_{column}_check",),
    ).fetchone()
    assert found is not None, f"no CHECK on url_check.{column}"
    return set(re.findall(r"'([^']*)'::text", found[0]))


LISTS: list[tuple[str, Any]] = [("outcome", CheckOutcome), ("detected_type", DetectedKind)]


@pytest.mark.parametrize(("column", "known"), LISTS, ids=[column for column, _ in LISTS])
def test_the_database_lists_exactly_the_values_the_code_knows(
    connection: psycopg.Connection, column: str, known: Any
) -> None:
    assert listed_values(connection, column) == set(get_args(known))


def test_an_address_is_kept_under_its_sha_256_in_any_script(connection: psycopg.Connection) -> None:
    add_check(connection, "https://lehrpläne.example/Ökonomie_小学.pdf")

    with pytest.raises(errors.CheckViolation):
        add_check(connection, "https://b.example/", url_sha256=hashlib.sha256(b"https://c.example/").digest())


def test_an_address_is_checked_once(connection: psycopg.Connection) -> None:
    add_check(connection)

    with pytest.raises(errors.UniqueViolation):
        add_check(connection)


def test_only_a_body_read_to_its_end_has_a_hash_and_a_size(connection: psycopg.Connection) -> None:
    add_check(connection, "https://a.example/1", outcome="too_large", size_bytes=None, sha256=None)
    add_check(
        connection, "https://a.example/2", outcome="refused", status_code=403, size_bytes=None, sha256=None
    )

    for broken in (
        {"outcome": "reachable", "size_bytes": None, "sha256": None},
        {"outcome": "refused", "status_code": 403},
        {"outcome": "reachable", "size_bytes": None},
    ):
        with pytest.raises(errors.CheckViolation):
            add_check(connection, "https://a.example/3", **broken)


@pytest.mark.parametrize("status", [99, 600])
def test_a_status_is_an_http_one(connection: psycopg.Connection, status: int) -> None:
    with pytest.raises(errors.CheckViolation):
        add_check(connection, status_code=status)


def test_a_host_is_a_name_as_dns_holds_one(connection: psycopg.Connection) -> None:
    connection.execute("INSERT INTO host_throttle (host, next_at) VALUES (%s, now())", ("a" * 253,))

    for host in ("", "a" * 254):
        with pytest.raises(errors.CheckViolation):
            connection.execute("INSERT INTO host_throttle (host, next_at) VALUES (%s, now())", (host,))
