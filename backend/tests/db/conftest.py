"""A fresh PostgreSQL database per test, in the server KKA_TEST_DATABASE_URL names.

The URL is an account that may create databases, on a server for tests only (locally the
container kka-test-pg, in CI a service). Without it the database tests are skipped.
"""

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

ADMIN_URL_VARIABLE = "KKA_TEST_DATABASE_URL"


@pytest.fixture
def database_url() -> Iterator[str]:
    admin = os.environ.get(ADMIN_URL_VARIABLE)
    if not admin:
        pytest.skip(f"{ADMIN_URL_VARIABLE} is not set")
    name = f"kka_t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
    try:
        yield make_conninfo(admin, dbname=name)
    finally:
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
