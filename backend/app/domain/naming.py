"""The IRIs a document's nodes and statements get when it is frozen (plan M1 9.6, Paket 9b H6).

Nodes are named from the top, by the path of their codes under the document (app/domain/iris.py), each
group of siblings in its order. A statement is numbered under its node - ``<node>/s-<n>`` - from the
highest number the node has given (``statement_serial``), so that no number is given twice, though a
draft copy took one away. What a draft copy brought along keeps its IRI, whatever its code says now: an
IRI once given stays. What is new is named past it: a segment a sibling holds counts on ("lf-1-2"). A
rejected statement is none of the curriculum's and gets no IRI; one it had stays.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from app.domain.iris import node_iri, node_segments, statement_iri


@dataclass(frozen=True)
class NodeRow:
    id: UUID
    parent_id: UUID | None
    position: int
    code: str | None
    code_assigned: bool
    iri: str | None
    statement_serial: int


@dataclass(frozen=True)
class StatementRow:
    id: UUID
    node_id: UUID
    position: int
    iri: str | None
    rejected: bool


@dataclass(frozen=True)
class Named:
    """The IRIs given now, by row; the nodes' statement numbers where they grew."""

    nodes: dict[UUID, str] = field(default_factory=dict)
    statements: dict[UUID, str] = field(default_factory=dict)
    serials: dict[UUID, int] = field(default_factory=dict)


def name_rows(document: str, nodes: Iterable[NodeRow], statements: Iterable[StatementRow]) -> Named:
    """The IRIs the rows of the document ``document`` (its frozen IRI) lack, given as above."""
    children: dict[UUID | None, list[NodeRow]] = defaultdict(list)
    for row in nodes:
        children[row.parent_id].append(row)
    said: dict[UUID, list[StatementRow]] = defaultdict(list)
    for statement in statements:
        said[statement.node_id].append(statement)
    named = Named()
    pending: list[tuple[str, Sequence[NodeRow]]] = [(document, children[None])]
    while pending:
        parent, siblings = pending.pop()
        for row, iri in _siblings(parent, sorted(siblings, key=lambda sibling: sibling.position), named):
            _statements(row, iri, said[row.id], named)
            pending.append((iri, children[row.id]))
    return named


def _siblings(parent: str, siblings: Sequence[NodeRow], named: Named) -> list[tuple[NodeRow, str]]:
    taken = {row.iri for row in siblings if row.iri is not None}
    segments = node_segments([(row.code or "", row.code_assigned) for row in siblings])
    placed = []
    for row, segment in zip(siblings, segments, strict=True):
        iri = row.iri
        if iri is None:
            made, count = node_iri(parent, [segment]), 1
            while made in taken:
                count += 1
                made = node_iri(parent, [f"{segment}-{count}"])
            taken.add(made)
            named.nodes[row.id] = iri = made
        placed.append((row, iri))
    return placed


def _statements(row: NodeRow, iri: str, statements: Sequence[StatementRow], named: Named) -> None:
    serial = row.statement_serial
    for statement in sorted(statements, key=lambda said: said.position):
        if statement.iri is None and not statement.rejected:
            serial += 1
            named.statements[statement.id] = statement_iri(iri, serial)
    if serial != row.statement_serial:
        named.serials[row.id] = serial
