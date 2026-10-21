"""Versioned SQL migrations, each applied exactly once: ``python -m app.db.migrate``.

The files ``NNNN_name.sql`` in ``app/db/migrations`` are numbered from 0001 without gaps. A run
takes a session-level advisory lock, so pods or jobs starting together wait for each other
instead of applying a file twice; it applies every pending file in its own transaction and
records it with the SHA-256 of its bytes in ``schema_migration``. A database that knows a
version this code does not, or an applied file whose bytes changed, stops the run: the code
must not guess what such a database holds. API and worker never migrate; they only check the
state (/ready).
"""

import hashlib
import logging
import re
import sys
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

import psycopg

log = logging.getLogger("app.db.migrate")  # also when run as __main__

MIGRATIONS: Traversable = files("app.db") / "migrations"
# Any fixed number serves; all runs against one database must agree on it
LOCK_KEY = 0x6B6B_612D_6D69_6772  # "kka-migr"
_FILENAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")
_BOOKKEEPING = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version integer PRIMARY KEY CHECK (version > 0),
    name text NOT NULL,
    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(Exception):
    """The migrations cannot be applied as they are; nothing further was changed."""


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    sql: str
    checksum: str


def load_migrations(directory: Traversable = MIGRATIONS) -> list[Migration]:
    """The ``.sql`` files of ``directory`` in order; refused unless they run 1, 2, ... without gaps."""
    migrations: dict[int, Migration] = {}
    for entry in directory.iterdir():
        if not entry.name.endswith(".sql"):
            continue
        match = _FILENAME.fullmatch(entry.name)
        if match is None:
            raise MigrationError(f"{entry.name}: a migration is named NNNN_lower_case_name.sql")
        version = int(match.group(1))
        if version in migrations:
            raise MigrationError(f"version {version} twice: {migrations[version].filename}, {entry.name}")
        content = entry.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        migrations[version] = Migration(version, entry.name, content.decode("utf-8"), checksum)
    ordered = [migrations[version] for version in sorted(migrations)]
    for expected, migration in enumerate(ordered, start=1):
        if migration.version != expected:
            raise MigrationError(f"gap before {migration.filename}: version {expected} is missing")
    return ordered


def migrate(conninfo: str, directory: Traversable = MIGRATIONS) -> list[int]:
    """Apply the pending migrations; the versions applied by this run, in order."""
    migrations = load_migrations(directory)
    with psycopg.connect(conninfo, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            connection.execute(_BOOKKEEPING)
            rows = connection.execute("SELECT version, checksum FROM schema_migration").fetchall()
            applied = {int(version): str(checksum) for version, checksum in rows}
            _check(applied, migrations)
            done = []
            for migration in migrations:
                if migration.version not in applied:
                    _apply(connection, migration)
                    done.append(migration.version)
            return done
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def _check(applied: dict[int, str], migrations: list[Migration]) -> None:
    known = {migration.version: migration for migration in migrations}
    unknown = sorted(set(applied) - set(known))
    if unknown:
        raise MigrationError(
            f"the database is at migration {max(applied)}, newer than this code ({len(migrations)})"
        )
    for version, checksum in applied.items():
        if known[version].checksum != checksum:
            raise MigrationError(f"{known[version].filename} changed after it was applied")


def _apply(connection: psycopg.Connection, migration: Migration) -> None:
    try:
        with connection.transaction():
            connection.execute(migration.sql.encode("utf-8"))  # bytes: the file as it is, several statements
            connection.execute(
                "INSERT INTO schema_migration (version, name, checksum) VALUES (%s, %s, %s)",
                (migration.version, migration.filename, migration.checksum),
            )
    except psycopg.Error as error:
        raise MigrationError(f"{migration.filename} failed: {error}") from error
    log.info("applied %s", migration.filename)


async def applied_versions(connection: psycopg.AsyncConnection) -> frozenset[int]:
    """The versions recorded in ``schema_migration``; none before the first run made the table."""
    cursor = await connection.execute("SELECT to_regclass('schema_migration') IS NOT NULL")
    exists = await cursor.fetchone()
    if not (exists and exists[0]):
        return frozenset()
    cursor = await connection.execute("SELECT version FROM schema_migration")
    return frozenset(int(version) for (version,) in await cursor.fetchall())


def main() -> int:
    from app.core.logging import configure_logging
    from app.core.settings import Settings

    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    try:
        applied = migrate(settings.database_url.get_secret_value())
    except MigrationError as error:
        log.error("migration stopped: %s", error)
        return 1
    log.info("%d migration(s) applied", len(applied))
    return 0


if __name__ == "__main__":
    sys.exit(main())
