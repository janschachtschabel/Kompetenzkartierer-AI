"""X3's answer read (plan M1 7b, F2; schema x3-rahmenteile).

Each competency or level model, operator, legend entry and rule is a frame part: its schema object
as the model gave it - its codes the schema's notations -, the blocks it names taken out into its
anchor. Blocks the conversion does not hold are left out with a finding, and an entry of none of
its blocks is. The parts come in the document's order, by their first block (X4's choice lists
take them in the order written, app/pipeline/unit_prefix.py). A statement of the frame stands at
the node of the frame range its first block lies in - the title pages are of no node -, one outside
every such range is left out: X4 reads the other sections. At each node they stand from position 1
on, in the document's order (X4 never writes at a node read typed); a statement points to content
at its own node, by its position.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from app.db.findings import Finding
from app.db.frame_parts import FramePartDraft
from app.domain.l1 import FramePartKind, StatementDraft
from app.pipeline.statement_read import Reading, StatementContext
from app.pipeline.x1_outline import MODEL, PROPOSED
from app.pipeline.x2_segments import WorkPackage

# each kind of part by the field that names its blocks, in the schema's order
_EVIDENCE: dict[FramePartKind, str] = {
    "competencyModels": "evidenceBlockIds",
    "levelModels": "evidenceBlockIds",
    "operators": "evidenceBlockId",
    "crossCuttingLegend": "evidenceBlockId",
    "rules": "blockIds",
}


@dataclass(frozen=True)
class FrameContext:
    statements: StatementContext  # its stage x3
    ranges: Sequence[WorkPackage]  # X2's packages read typed (job frame)


@dataclass(frozen=True)
class FrameReading:
    parts: list[FramePartDraft]
    statements: dict[UUID, list[StatementDraft]]  # by node, each at its position from 1
    checked_absent: tuple[str, ...]  # notations of cv:DockingPoints
    counts: dict[str, int]  # the parts of each kind
    findings: list[Finding]


def read_frame(answer: Mapping[str, Any], context: FrameContext) -> FrameReading:
    """The frame parts and statements of X3's answer, as the module says."""
    reading = Reading(context.statements)
    parts: list[tuple[int, FramePartDraft]] = []
    for kind, field in _EVIDENCE.items():
        for at, entry in enumerate(answer[kind]):
            named = entry[field]
            path = f"$.{kind}[{at}].{field}"
            blocks = reading.blocks(named if isinstance(named, list) else [named], path, None)
            if not blocks:
                reading.note(
                    "part_without_block", "warning", f"$.{kind}[{at}]", "no block of it holds the part"
                )
                continue
            content = {name: value for name, value in entry.items() if name != field}
            draft = FramePartDraft(kind, content, reading.anchor(blocks), MODEL, PROPOSED)
            parts.append((min(reading.position(block) for block in blocks), draft))
    parts.sort(key=lambda item: item[0])  # stable: the schema's and the answer's order among equals
    statements = _placed(reading, answer["statements"], context.ranges)
    counts: dict[str, int] = {}
    for _, part in parts:
        counts[part.kind] = counts.get(part.kind, 0) + 1
    return FrameReading(
        parts=[part for _, part in parts],
        statements=statements,
        checked_absent=tuple(dict.fromkeys(answer["checkedAbsent"])),
        counts=counts,
        findings=reading.findings,
    )


def _placed(
    reading: Reading, given: Sequence[Mapping[str, Any]], ranges: Sequence[WorkPackage]
) -> dict[UUID, list[StatementDraft]]:
    read = reading.statements(given, None)
    # the paths name no index: the statements are in the document's order, not the answer's
    placed: dict[UUID, list[StatementDraft]] = {}
    at_node: list[tuple[UUID, int] | None] = []  # each statement's node and position there
    for statement in read:
        holding = next((item for item in ranges if item.first <= statement.first <= item.last), None)
        node = None if holding is None else holding.node_id
        if node is None:
            block = statement.draft.anchors[0].block_ids[0]
            if holding is None:
                message = "a statement outside the frame's ranges: X4 reads it"
                reading.note("statement_outside_frame", "warning", "$.statements", message, block=block)
            else:  # the title pages: read for their models and lists alone
                message = "a statement of the title pages, which no node holds"
                reading.note("statement_without_node", "warning", "$.statements", message, block=block)
            at_node.append(None)
            continue
        placed.setdefault(node, []).append(statement.draft)
        at_node.append((node, len(placed[node])))
    for statement, place in zip(read, at_node, strict=True):
        if place is None or not statement.targets:
            continue
        node, position = place
        targets = []
        for target in statement.targets:
            if (found := at_node[target]) is not None and found[0] == node:
                targets.append(found[1])
            else:
                message = "content at another node, or at none"
                reading.note("target_elsewhere", "info", "$.statements", message, target=target)
        if targets:
            draft = placed[node][position - 1]
            placed[node][position - 1] = replace(draft, details={**draft.details, "targetsContent": targets})
    return placed
