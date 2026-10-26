"""A unit of X4 written (plan M1 7b, F4, F10): in one transaction under the attempt's lease, its
statements, its findings and its mark (app/db/units.py) - whole or not at all, once per document.

A unit's statements stand at its node, from where its part of the node begins: a node parted at
pages (app/pipeline/x2_segments.py) has a range of PART positions for each of its parts, so the
document's order holds however and whenever the parts are written. A unit of no node - a document
without headings is one unit - gets a node of its own, the rule's, named by the document's title.
A statement points to the content it names by that content's position. A unit marked already
(another writer's) gives way with all it wrote (UnitTaken); one whose node an editor took away while it
waited for the tree ends the job (``node_gone``, Paket 9 G6). At a node that stands the tree's lock
comes first, as for every writer of a tree (migration l1_nodes) - none holds a row of it while it
waits -, then the mark: a writer beside this one waits at the lock and meets the mark, where its
statements would otherwise meet this one's at their positions.
"""

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID

import psycopg

from app.db.documents import Document
from app.db.findings import add_findings
from app.db.nodes import append_statements, lock_tree, node_stands, write_subtree
from app.db.units import mark_unit
from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, hold_lease
from app.pipeline.x1_outline import PROPOSED, RULE
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x4_read import UnitReading

PART = 10_000  # positions for each part of a node: far more than a unit's statements (MOST_STATEMENTS)
UNIT_WITHOUT_NODE = "x4.unit_without_node"
_UNIT = "https://w3id.org/wlo/curriculum/vocab#fn_unit"


def first_position(unit: WorkPackage, packages: Sequence[WorkPackage]) -> int:
    """The position the unit's statements begin at, at its node: by its part among the node's
    packages (X2's, in the document's order)."""
    parts = [item.key for item in packages if item.node_id == unit.node_id]
    return parts.index(unit.key) * PART + 1


async def write_unit(
    connection: psycopg.AsyncConnection,
    job: Job,
    document: Document,
    unit: WorkPackage,
    read: UnitReading,
    *,
    first: int,
    run_id: UUID,
) -> int:
    """Write the unit as read, its statements from ``first`` on at its node; how many. LeaseLost,
    UnitTaken or the database's error, and then nothing of it is written."""
    async with connection.transaction():
        await hold_lease(connection, job)
        start = first if unit.node_id is not None else 1  # a node of its own holds it alone
        drafts = [
            pointing(item.draft, [start + target for target in item.targets]) for item in read.statements
        ]
        if unit.node_id is None:
            node = NodeDraft(
                function=_UNIT,
                origin=RULE,
                review_status=PROPOSED,
                original_title=document.title or "Dokument",
                rule_id=UNIT_WITHOUT_NODE,
                anchors=(AnchorDraft((unit.first_block,), page_start=unit.pages[0]),),
                statements=tuple(drafts),
            )
            # a node of its own: its statements meet no other writer's, the mark names it
            node_id = await write_subtree(connection, document.id, node, run_id=run_id)
            await _mark(connection, document, unit, read, node_id, len(drafts), run_id)
        else:
            # the tree's lock before any row of it (migration l1_nodes), then the mark: a writer beside
            # this one meets it there, not the statements' positions
            await lock_tree(connection, document.id)
            if not await node_stands(connection, document.id, unit.node_id):  # an editor took it away
                raise PermanentError("node_gone", f"the node of the package {unit.key} is gone")
            await _mark(connection, document, unit, read, unit.node_id, len(drafts), run_id)
            await append_statements(
                connection, document.id, unit.node_id, drafts, first_position=first, run_id=run_id
            )
        await add_findings(connection, document.id, run_id, read.findings)
    return len(drafts)


async def _mark(
    connection: psycopg.AsyncConnection,
    document: Document,
    unit: WorkPackage,
    read: UnitReading,
    node_id: UUID,
    statements: int,
    run_id: UUID,
) -> None:
    await mark_unit(
        connection,
        document.id,
        unit.key,
        run_id=run_id,
        node_id=node_id,
        statements=statements,
        checked_absent=read.checked_absent,
    )


def pointing(draft: StatementDraft, targets: list[int]) -> StatementDraft:
    """The statement pointing to the content statements at ``targets`` (their positions), where any."""
    return replace(draft, details={**draft.details, "targetsContent": targets}) if targets else draft
