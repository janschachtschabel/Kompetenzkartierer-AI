"""A work package written anew by X6 (plan M1 8b, Festlegung F4): in one transaction under the attempt's
lease, the tree's lock first (who changes a tree takes it first, plan M1 Paket 4) - then which of the
package's statements stand is read, and nothing changes them meanwhile.

The statements the model wrote and nobody has touched since (origin model, proposed, first revision) go
with their anchors; those the editors hold - changed, confirmed, rejected, written by hand - stay, and a
statement of the new answer with the wording of one of them is left out (konzept: a rejected statement
is kept so that it is not proposed again). The new statements come after every position the package
used, so none takes the place a held statement points to; a statement points to content by that
content's new position - by the held one's where its wording is held and not rejected -, and to none
the answer lost. The findings of reading the package's earlier answers make way for this reading's,
and the mark names the repair and counts it (app/db/units.py).

An answer that brings no statement to write for a package the model wrote statements to - none, none
read, or only the wordings that stay, which it was told not to bring - lost them rather than found none
(it was asked for all of them): nothing of it is written (``EmptyAnswer``).
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.db.documents import Document
from app.db.findings import add_findings, drop_unit_findings
from app.db.nodes import append_statements, drop_statements, lock_tree, node_stands
from app.db.units import remark_unit
from app.domain.wording import text_hash
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, hold_lease
from app.pipeline.x4_read import UnitReading
from app.pipeline.x4_unit import PART, pointing
from app.pipeline.x6_units import RepairUnit

_CV = "https://w3id.org/wlo/curriculum/vocab#"
_OF_PACKAGE = """
SELECT id, position, text_hash,
    origin_iri = %(model)s AND review_status_iri = %(proposed)s AND revision = 1,
    review_status_iri = %(rejected)s
FROM statement
WHERE document_id = %(document)s AND node_id = %(node)s AND position BETWEEN %(low)s AND %(high)s
ORDER BY position
"""
_LAST_POSITION = 2**31 - 1  # of a node X4 made for a package alone: all its positions are the package's


class EmptyAnswer(Exception):
    """The answer held no statement of a package that has statements nobody touched."""


@dataclass(frozen=True)
class Rewritten:
    statements: int  # the new ones written
    dropped: int  # the answer's left out: the editors hold their wording already


async def rewrite_unit(
    connection: psycopg.AsyncConnection,
    job: Job,
    document: Document,
    unit: RepairUnit,
    read: UnitReading,
    *,
    run_id: UUID,
) -> Rewritten:
    """Write the package anew as read; LeaseLost, EmptyAnswer, PermanentError ``node_gone`` where an editor
    took its node away while it waited for the tree (Paket 9 G6), or the database's error, and then
    nothing of it."""
    if unit.node_id is None:
        raise LookupError(f"package {unit.package.key} stands at no node")
    async with connection.transaction():
        await hold_lease(connection, job)
        await lock_tree(connection, document.id)
        if not await node_stands(connection, document.id, unit.node_id):  # an editor took it away
            raise PermanentError("node_gone", f"the node of the package {unit.package.key} is gone")
        high = unit.first + PART - 1 if unit.package.node_id is not None else _LAST_POSITION
        cursor = await connection.execute(
            _OF_PACKAGE,
            {
                "document": document.id, "node": unit.node_id, "low": unit.first, "high": high,
                "model": _CV + "orig_model", "proposed": _CV + "rev_proposed",
                "rejected": _CV + "rev_rejected",
            },
        )  # fmt: skip
        found = await cursor.fetchall()  # mine: the model's, nobody's since
        untouched = [row_id for row_id, _, _, mine, _ in found if mine]
        held = {hashed for _, _, hashed, mine, _ in found if not mine}
        hashes = [text_hash(item.draft.verbatim) for item in read.statements]
        kept = [index for index, hashed in enumerate(hashes) if hashed not in held]
        if untouched and not kept:
            raise EmptyAnswer(unit.package.key)
        standing: dict[str, int] = {}  # a held wording not rejected, at its first position
        for _, position, hashed, mine, rejected in found:
            if not (mine or rejected):
                standing.setdefault(hashed, position)
        await drop_statements(connection, document.id, untouched)
        start = max((position for _, position, _, _, _ in found), default=unit.first - 1) + 1
        place = {index: start + at for at, index in enumerate(kept)} | {
            index: standing[hashed] for index, hashed in enumerate(hashes) if hashed in standing
        }
        drafts = [
            pointing(
                read.statements[index].draft,
                [place[at] for at in read.statements[index].targets if at in place],
            )
            for index in kept
        ]
        await append_statements(
            connection, document.id, unit.node_id, drafts, first_position=start, run_id=run_id
        )
        await drop_unit_findings(connection, document.id, unit.package.key, ("X4", "X6"))
        await add_findings(connection, document.id, run_id, read.findings)
        await remark_unit(
            connection,
            document.id,
            unit.package.key,
            run_id=run_id,
            statements=len(found) - len(untouched) + len(drafts),
            checked_absent=read.checked_absent,
        )
    return Rewritten(len(drafts), len(read.statements) - len(kept))
