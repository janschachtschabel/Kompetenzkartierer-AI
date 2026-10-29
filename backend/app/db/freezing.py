"""A document frozen (plan M1 9.6; Paket 9b H5, H6): it gets its IRIs and changes no more - the database's
triggers keep its rows as they are (migration freeze).

Under the tree's lock, in this order, each refused with its own reason and nothing changed: frozen
already (DocumentFrozen), beside its open job (JobOpen), its tree not all there (NotExtracted: X4 has
not read every package, and it is no draft copy), short of its work, the work's country or short title,
its issuer or edition (``incomplete``), no base to name it under (``no_iri_base``), X5 owing it a check
or an anchor X5 has not checked (``check_owed``), violations among its findings the editors have not
accepted (``has_violations``). Then the work gets its IRI where it has none, the document its own -
issuer, the work's short title, edition (app/domain/iris.py) - where it has none, its nodes and
statements theirs (app/domain/naming.py); an IRI another work or document holds refuses
(``iri_taken``). The document is frozen last: after that, the triggers refuse every change.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg import sql

from app.db.anchors import unchecked_anchors
from app.db.documents import DocumentError
from app.db.editing import CV, DocumentFrozen, JobOpen, NotExtracted, extracted, frozen
from app.db.nodes import lock_tree
from app.db.runs import x5_owed
from app.domain.iris import document_iri, work_iri
from app.domain.naming import NodeRow, StatementRow, name_rows
from app.jobs.queue import open_job
from app.pipeline.extraction import unique_key
from app.pipeline.x4_unit import UNIT_WITHOUT_NODE

_DOCUMENT = """
SELECT d.iri, d.revision, d.issuer, d.edition, d.work_id, w.iri, w.region, w.short_title
FROM document d LEFT JOIN work w ON w.id = d.work_id WHERE d.id = %s
"""
_NODES = """
SELECT id, parent_id, position, code, code_assigned, iri, statement_serial FROM node WHERE document_id = %s
"""
_STATEMENTS = """
SELECT id, node_id, position, iri, review_status_iri = %s FROM statement WHERE document_id = %s
"""
_VIOLATIONS = "SELECT count(*) FROM validation_finding WHERE document_id = %s AND severity = 'violation'"
_TAKEN = sql.SQL("SELECT 1 FROM {} WHERE iri = %s AND id <> %s LIMIT 1")


FreezeCode = Literal["incomplete", "no_iri_base", "check_owed", "has_violations", "iri_taken"]


class FreezeRefused(Exception):
    """The document is not frozen: ``code`` says why, ``details`` what of it."""

    def __init__(self, code: FreezeCode, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code: FreezeCode = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class Frozen:
    iri: str  # the document's
    revision: int
    nodes: int  # named now
    statements: int
    violations: int  # the editors accepted


async def freeze(
    connection: psycopg.AsyncConnection, document_id: UUID, base: str | None, *, accept_violations: bool
) -> Frozen:
    """Freeze the document under ``base`` (IRI_BASE) as above; DocumentError for none."""
    async with connection.transaction():
        await lock_tree(connection, document_id)
        if await frozen(connection, document_id):
            raise DocumentFrozen(f"the document {document_id} is frozen")
        if (job := await open_job(connection, unique_key(document_id))) is not None:
            raise JobOpen(job)
        if not await extracted(connection, document_id):
            raise NotExtracted(f"X4 has not read every package of the document {document_id}")
        cursor = await connection.execute(_DOCUMENT, (document_id,))
        row = await cursor.fetchone()
        if row is None:
            raise DocumentError(f"no document {document_id}")
        iri, revision, issuer, edition, work_id, work, region, short_title = row
        missing = [name for name, lacking in (
            ("work", work_id is None), ("region", work_id is not None and region is None),
            ("short_title", work_id is not None and short_title is None),
            ("issuer", issuer is None), ("edition", edition is None),
        ) if lacking]  # fmt: skip
        if missing:
            raise FreezeRefused("incomplete", f"the document lacks {missing}", {"missing": missing})
        if base is None:
            raise FreezeRefused("no_iri_base", "the service names no IRI base (IRI_BASE)")
        unchecked = len(await unchecked_anchors(connection, document_id, rule_titles=(UNIT_WITHOUT_NODE,)))
        if unchecked or await x5_owed(connection, document_id):
            raise FreezeRefused("check_owed", "X5 owes the document a check", {"unchecked": unchecked})
        cursor = await connection.execute(_VIOLATIONS, (document_id,))
        violations = int((await cursor.fetchone() or (0,))[0])
        if violations and not accept_violations:
            raise FreezeRefused("has_violations", "violations not accepted", {"violations": violations})
        if work is None:
            work = work_iri(base, region, short_title)
            await _untaken(connection, "work", work, work_id)
            await connection.execute("UPDATE work SET iri = %s WHERE id = %s", (work, work_id))
        if iri is None:
            iri = document_iri(base, issuer, short_title, edition)
            await _untaken(connection, "document", iri, document_id)
        named = await _name(connection, document_id, iri)
        await connection.execute(
            "UPDATE document SET iri = %s, frozen_at = now(), updated_at = now() WHERE id = %s",
            (iri, document_id),
        )
        return Frozen(iri, revision, named[0], named[1], violations)


async def _untaken(
    connection: psycopg.AsyncConnection, table: Literal["work", "document"], iri: str, own: UUID
) -> None:
    cursor = await connection.execute(_TAKEN.format(sql.Identifier(table)), (iri, own))
    if await cursor.fetchone() is not None:
        raise FreezeRefused("iri_taken", f"the IRI {iri} is another {table}'s", {"iri": iri})


async def _name(connection: psycopg.AsyncConnection, document_id: UUID, iri: str) -> tuple[int, int]:
    """Give the document's nodes and statements the IRIs they lack; how many of each got one."""
    cursor = await connection.execute(_NODES, (document_id,))
    nodes = [NodeRow(*found) for found in await cursor.fetchall()]
    cursor = await connection.execute(_STATEMENTS, (CV + "rev_rejected", document_id))
    statements = [StatementRow(*found) for found in await cursor.fetchall()]
    named = name_rows(iri, nodes, statements)
    async with connection.cursor() as writing:
        await writing.executemany(
            "UPDATE node SET iri = %s WHERE id = %s", [(v, k) for k, v in named.nodes.items()]
        )
        await writing.executemany(
            "UPDATE node SET statement_serial = %s WHERE id = %s", [(v, k) for k, v in named.serials.items()]
        )
        await writing.executemany(
            "UPDATE statement SET iri = %s WHERE id = %s", [(v, k) for k, v in named.statements.items()]
        )
    return len(named.nodes), len(named.statements)
