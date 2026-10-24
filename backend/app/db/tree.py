"""A document's structure read back as a tree (plan M1 4.6), by those who see its document
(app/db/documents.py): its nodes from its top, each with its statements and children in their
order, all in one snapshot. Written by app/db/nodes.py."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.db.documents import DOCUMENT_VISIBLE
from app.db.source_queries import Reader

# each query of a tree asks who sees its document, all within one snapshot (read_tree)
_VISIBLE = f"SELECT 1 FROM document d WHERE d.id = %(id)s AND {DOCUMENT_VISIBLE}"  # noqa: S608 - fixed parts
_NODES = f"""
SELECT n.id, n.parent_id, n.position, n.function_iri, n.node_type_iri, n.code, n.code_assigned,
    n.original_title, n.origin_iri, n.review_status_iri, n.revision
FROM node n JOIN document d ON d.id = n.document_id
WHERE n.document_id = %(id)s AND {DOCUMENT_VISIBLE} ORDER BY n.position
"""  # noqa: S608 - fixed parts
_STATEMENTS = f"""
SELECT s.id, s.node_id, s.position, s.verbatim, s.statement_kind_iri, s.subkind_iri, s.origin_iri,
    s.review_status_iri, s.text_hash, s.revision,
    array(
        SELECT a.addressee_iri FROM statement_addressee a WHERE a.statement_id = s.id ORDER BY 1
    ) AS addressees
FROM statement s JOIN document d ON d.id = s.document_id
WHERE s.document_id = %(id)s AND {DOCUMENT_VISIBLE} ORDER BY s.position
"""  # noqa: S608 - fixed parts


@dataclass(frozen=True)
class TreeStatement:
    id: UUID
    position: int
    verbatim: str
    statement_kind_iri: str
    subkind_iri: str | None
    origin_iri: str
    review_status_iri: str
    text_hash: str
    revision: int
    addressees: tuple[str, ...]


@dataclass(frozen=True)
class TreeNode:
    id: UUID
    position: int
    function_iri: str
    node_type_iri: str | None
    code: str | None
    code_assigned: bool
    original_title: str | None
    origin_iri: str
    review_status_iri: str
    revision: int
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


async def _read_tree(
    connection: psycopg.AsyncConnection, reader: Reader, document_id: UUID
) -> tuple[TreeNode, ...] | None:
    params = {"id": document_id, "me": reader.account_id, "all": reader.sees_all}
    cursor = await connection.execute(_VISIBLE, params)
    if await cursor.fetchone() is None:
        return None
    async with connection.cursor(row_factory=dict_row) as rows:
        await rows.execute(_NODES, params)
        nodes = await rows.fetchall()
        await rows.execute(_STATEMENTS, params)
        statements = await rows.fetchall()
    said: defaultdict[UUID, list[TreeStatement]] = defaultdict(list)
    for row in statements:
        node_id = row.pop("node_id")
        said[node_id].append(TreeStatement(**{**row, "addressees": tuple(row["addressees"])}))
    under: defaultdict[UUID | None, list[dict[str, Any]]] = defaultdict(list)
    for row in nodes:
        under[row["parent_id"]].append(row)

    def built(row: dict[str, Any]) -> TreeNode:
        fields = {name: value for name, value in row.items() if name != "parent_id"}
        children = tuple(built(child) for child in under[row["id"]])
        return TreeNode(**fields, statements=tuple(said[row["id"]]), children=children)

    return tuple(built(row) for row in under[None])
