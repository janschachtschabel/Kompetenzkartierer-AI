"""The core schema: the extensions the plan relies on and the one id space, ``entity``."""

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
    with psycopg.connect(database_url, autocommit=True) as conn:
        yield conn


@pytest.mark.parametrize("extension", ["vector", "pg_trgm", "unaccent"])
def test_the_extensions_are_installed(connection: psycopg.Connection, extension: str) -> None:
    row = connection.execute("SELECT count(*) FROM pg_extension WHERE extname = %s", (extension,)).fetchone()

    assert row == (1,)


def test_half_precision_vectors_and_unaccent_work(connection: psycopg.Connection) -> None:
    row = connection.execute("SELECT '[1,2,3]'::halfvec(3)::text, unaccent('Übergänge')").fetchone()

    assert row == ("[1,2,3]", "Ubergange")


def test_an_entity_has_an_id_a_kind_and_a_creation_time(connection: psycopg.Connection) -> None:
    entity_id = uuid.uuid4()
    connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'node')", (entity_id,))

    query = "SELECT kind, created_at IS NOT NULL FROM entity WHERE id = %s"
    row = connection.execute(query, (entity_id,)).fetchone()

    assert row == ("node", True)


@pytest.mark.parametrize(
    ("statement", "fault"),
    [
        ("INSERT INTO entity (id) VALUES (%s)", errors.NotNullViolation),
        ("INSERT INTO entity (kind) VALUES ('node') RETURNING %s", errors.NotNullViolation),
        ("INSERT INTO entity (id, kind) VALUES (%s, '')", errors.CheckViolation),
        ("INSERT INTO entity (id, kind) VALUES (%s, 'Node Kind')", errors.CheckViolation),
    ],
    ids=["no-kind", "no-id", "empty-kind", "kind-not-an-identifier"],
)
def test_an_entity_without_id_or_proper_kind_is_refused(
    connection: psycopg.Connection, statement: str, fault: type[Exception]
) -> None:
    with pytest.raises(fault):
        connection.execute(statement, (uuid.uuid4(),))


def test_an_id_is_given_once(connection: psycopg.Connection) -> None:
    entity_id = uuid.uuid4()
    connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'node')", (entity_id,))

    with pytest.raises(errors.UniqueViolation):
        connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'statement')", (entity_id,))


def test_a_typed_table_can_require_the_kind_of_its_entity(connection: psycopg.Connection) -> None:
    # the pattern later tables follow: (id, kind) points at entity, kind fixed per table
    connection.execute(
        """
        CREATE TABLE probe_node (
            id uuid PRIMARY KEY,
            kind text NOT NULL DEFAULT 'node' CHECK (kind = 'node'),
            FOREIGN KEY (id, kind) REFERENCES entity (id, kind)
        )
        """
    )
    node, statement = uuid.uuid4(), uuid.uuid4()
    both = "INSERT INTO entity (id, kind) VALUES (%s, 'node'), (%s, 'statement')"
    connection.execute(both, (node, statement))

    connection.execute("INSERT INTO probe_node (id) VALUES (%s)", (node,))
    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute("INSERT INTO probe_node (id) VALUES (%s)", (statement,))
