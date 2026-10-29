"""A document's structure read back as a tree (plan M1 4.6, 9.2), by those who see its document
(app/db/documents.py): its nodes from its top, each with its statements and children in their
order, all in one snapshot - as the editor shows it, each node and statement with the fields of its
form and its anchors, each node with the findings on it and its statements counted. Written by
app/db/nodes.py."""

from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.db.documents import DOCUMENT_VISIBLE
from app.db.findings import SEVERITIES
from app.db.source_queries import Reader
from app.domain.l1 import REVIEW_STATUSES, WORDING_FIELDS, Severity

# each query of a tree asks who sees its document, all within one snapshot (read_tree)
_VISIBLE = f"SELECT 1 FROM document d WHERE d.id = %(id)s AND {DOCUMENT_VISIBLE}"  # noqa: S608 - fixed parts
_NODES = f"""
SELECT n.id, n.parent_id, n.position, n.function_iri, n.node_type_iri, n.code, n.code_assigned,
    n.original_title, n.obligation_iri, n.origin_iri, n.review_status_iri, n.revision, n.iri
FROM node n JOIN document d ON d.id = n.document_id
WHERE n.document_id = %(id)s AND {DOCUMENT_VISIBLE} ORDER BY n.position
"""  # noqa: S608 - fixed parts
_STATEMENTS = f"""
SELECT s.id, s.node_id, s.position, s.verbatim, s.lead_in, s.statement_kind_iri, s.subkind_iri,
    s.obligation_iri, s.details, s.origin_iri, s.review_status_iri, s.text_hash, s.revision, s.iri,
    array(
        SELECT a.addressee_iri FROM statement_addressee a WHERE a.statement_id = s.id ORDER BY 1
    ) AS addressees
FROM statement s JOIN document d ON d.id = s.document_id
WHERE s.document_id = %(id)s AND {DOCUMENT_VISIBLE} ORDER BY s.position
"""  # noqa: S608 - fixed parts
# a node's and a statement's anchors, each with its blocks as the document orders them
_ANCHORS = f"""
SELECT a.id, a.node_id, a.statement_id, a.page_start, a.page_end, a.printed_page, a.quote, a.match_kind_iri,
    a.match_score::float8 AS match_score,
    array(
        SELECT ab.block_id FROM anchor_block ab
        JOIN document_block b ON b.conversion_id = ab.conversion_id AND b.block_id = ab.block_id
        WHERE ab.anchor_id = a.id ORDER BY b.seq
    ) AS blocks
FROM anchor a JOIN document d ON d.id = a.document_id
WHERE a.document_id = %(id)s AND (a.node_id IS NOT NULL OR a.statement_id IS NOT NULL) AND {DOCUMENT_VISIBLE}
ORDER BY a.id
"""  # noqa: S608 - fixed parts
# the findings on a node, its statements and the anchors of both, by node and severity
_FINDINGS = f"""
WITH owner (focus_id, node_id) AS (
    SELECT id, id FROM node WHERE document_id = %(id)s
    UNION ALL SELECT id, node_id FROM statement WHERE document_id = %(id)s
    UNION ALL SELECT a.id, coalesce(a.node_id, s.node_id) FROM anchor a
        LEFT JOIN statement s ON s.id = a.statement_id
        WHERE a.document_id = %(id)s AND (a.node_id IS NOT NULL OR a.statement_id IS NOT NULL)
)
SELECT o.node_id, f.severity, count(*)
FROM validation_finding f JOIN owner o ON o.focus_id = f.focus_id JOIN document d ON d.id = f.document_id
WHERE f.document_id = %(id)s AND {DOCUMENT_VISIBLE}
GROUP BY o.node_id, f.severity
"""  # noqa: S608 - fixed parts


@dataclass(frozen=True)
class TreeAnchor:
    """Where in the source a node's title or a statement stands: its pages, the page the document
    prints, the passage found, how it was matched, and its blocks in the document's order."""

    id: UUID
    page_start: int | None
    page_end: int | None
    printed_page: str | None
    quote: str | None
    match_kind_iri: str | None
    match_score: float | None
    blocks: tuple[str, ...]


@dataclass(frozen=True)
class TreeStatement:
    id: UUID
    position: int
    verbatim: str
    lead_in: str | None
    statement_kind_iri: str
    subkind_iri: str | None
    obligation_iri: str | None
    wording: Mapping[str, str]  # its wording parts (WORDING_FIELDS) it has, from its details
    origin_iri: str
    review_status_iri: str
    text_hash: str
    revision: int
    iri: str | None  # once its document was frozen
    addressees: tuple[str, ...]
    anchors: tuple[TreeAnchor, ...]


@dataclass(frozen=True)
class TreeNode:
    id: UUID
    position: int
    function_iri: str
    node_type_iri: str | None
    code: str | None
    code_assigned: bool
    original_title: str | None
    obligation_iri: str | None
    origin_iri: str
    review_status_iri: str
    revision: int
    iri: str | None  # once its document was frozen
    anchors: tuple[TreeAnchor, ...]
    # on the node, its anchors, its statements and their anchors - not its children's
    findings: dict[Severity, int]
    statements: tuple[TreeStatement, ...]
    children: tuple["TreeNode", ...]


async def read_tree(
    connection: psycopg.AsyncConnection, reader: Reader, document_id: UUID
) -> tuple[TreeNode, ...] | None:
    """The document's nodes from its top, each with its statements and children in their order;
    None where ``reader`` does not see the document. Read in one snapshot, in a read-only
    transaction of its own; within the caller's, as that one reads (each query anew under read
    committed)."""
    if connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        return await _read_tree(connection, reader, document_id)
    async with connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return await _read_tree(connection, reader, document_id)


def walk(tree: Sequence[TreeNode]) -> Iterator[TreeNode]:
    """Each node of the tree, level by level."""
    level = list(tree)
    while level:
        yield from level
        level = [child for node in level for child in node.children]


def review_counts(tree: Sequence[TreeNode]) -> tuple[dict[str, int], dict[str, int]]:
    """The tree's nodes and its statements counted by review status - each status, none left out."""
    nodes, statements = dict.fromkeys(REVIEW_STATUSES, 0), dict.fromkeys(REVIEW_STATUSES, 0)
    for node in walk(tree):
        nodes[node.review_status_iri] += 1
        for said in node.statements:
            statements[said.review_status_iri] += 1
    return nodes, statements


async def _read_tree(
    connection: psycopg.AsyncConnection, reader: Reader, document_id: UUID
) -> tuple[TreeNode, ...] | None:
    params = {"id": document_id, "me": reader.account_id, "all": reader.sees_all}
    cursor = await connection.execute(_VISIBLE, params)
    if await cursor.fetchone() is None:
        return None
    async with connection.cursor(row_factory=dict_row) as rows:
        read = []
        for query in (_NODES, _STATEMENTS, _ANCHORS):
            await rows.execute(query, params)
            read.append(await rows.fetchall())
    nodes, statements, anchors = read
    cursor = await connection.execute(_FINDINGS, params)
    found: defaultdict[UUID, dict[Severity, int]] = defaultdict(lambda: dict.fromkeys(SEVERITIES, 0))
    for node_id, severity, count in await cursor.fetchall():
        found[node_id][severity] = count
    anchored: defaultdict[UUID, list[TreeAnchor]] = defaultdict(list)  # by the node or statement
    for row in anchors:
        node_id, statement_id = row.pop("node_id"), row.pop("statement_id")
        anchored[node_id or statement_id].append(TreeAnchor(**{**row, "blocks": tuple(row["blocks"])}))
    said: defaultdict[UUID, list[TreeStatement]] = defaultdict(list)
    for row in statements:
        node_id, details, addressees = row.pop("node_id"), row.pop("details"), row.pop("addressees")
        said[node_id].append(
            TreeStatement(
                **row,
                wording={name: details[name] for name in WORDING_FIELDS if name in details},
                addressees=tuple(addressees),
                anchors=tuple(anchored[row["id"]]),
            )
        )
    under: defaultdict[UUID | None, list[dict[str, Any]]] = defaultdict(list)
    for row in nodes:
        under[row["parent_id"]].append(row)

    def built(row: dict[str, Any]) -> TreeNode:
        fields = {name: value for name, value in row.items() if name != "parent_id"}
        return TreeNode(
            **fields,
            anchors=tuple(anchored[row["id"]]),
            findings=found[row["id"]],
            statements=tuple(said[row["id"]]),
            children=tuple(built(child) for child in under[row["id"]]),
        )

    return tuple(built(row) for row in under[None])
