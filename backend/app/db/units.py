"""The units of X4 done (plan M1 7b, migration extraction_unit): a unit of the document's work
packages is marked in the transaction that writes its statements, so it is done whole or not at
all, and once per document. A unit marked already - by an earlier run, or by a writer beside this
one, whose commit this one waits for - is taken: the caller's transaction gives way, with what it
wrote, and the unit counts as done by the other.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg

_MARK = """
INSERT INTO extraction_unit (document_id, unit_key, run_id, node_id, statements, checked_absent)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (document_id, unit_key) DO NOTHING
RETURNING unit_key
"""
_DONE = """
SELECT unit_key, run_id, node_id, statements, checked_absent, finished_at
FROM extraction_unit WHERE document_id = %s
"""


class UnitTaken(Exception):
    """The unit is marked done already: the transaction that would mark it again gives way."""

    def __init__(self, key: str) -> None:
        super().__init__(f"unit {key} is done already")
        self.key = key


@dataclass(frozen=True)
class UnitDone:
    key: str
    run_id: UUID
    node_id: UUID | None  # the node its statements went to
    statements: int
    checked_absent: tuple[str, ...]  # concepts of cv:DockingPoints the unit lacks
    finished_at: datetime


async def mark_unit(
    connection: psycopg.AsyncConnection,
    document_id: UUID,
    key: str,
    *,
    run_id: UUID,
    node_id: UUID | None,
    statements: int,
    checked_absent: Sequence[str],
) -> None:
    """Mark the unit done, in the caller's transaction - the one that writes its statements. Raises
    UnitTaken where it is marked already; raised in a transaction block, that takes back all of it."""
    cursor = await connection.execute(
        _MARK, (document_id, key, run_id, node_id, statements, list(checked_absent))
    )
    if await cursor.fetchone() is None:
        raise UnitTaken(key)


async def done_units(connection: psycopg.AsyncConnection, document_id: UUID) -> dict[str, UnitDone]:
    """The document's units done, by their keys, whichever run did them."""
    cursor = await connection.execute(_DONE, (document_id,))
    return {
        key: UnitDone(key, run_id, node_id, statements, tuple(absent), finished)
        for key, run_id, node_id, statements, absent, finished in await cursor.fetchall()
    }
