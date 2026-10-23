"""A document's structure in the store (plan M1 4.6): written one subtree at a time, whole or not
at all, and read back as a tree by those who see its document (app/db/documents.py).

A subtree goes under a node of its document, or at its top, after the siblings there; the
positions of its nodes and statements are where they stand in their drafts, from 1. A node type
and a subkind are checked before anything is written: each is one of the document's sector's
profile and refines the core value beside it (the database checks the latter as well), and no
core value it names is retired. Anchors name blocks of the document's own conversion, by the
database's keys. Writes to one document's tree wait for each other, as moves of its nodes do
(``lock_tree``, migration l1_nodes).
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.ids import new_id
from app.db.documents import DOCUMENT_VISIBLE, DocumentError, ProfileValueError
from app.db.source_queries import Reader
from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft, check_profile_value
from app.domain.wording import text_hash
from app.vocab.lookup import ProfileConcepts, profile_concepts

CV = "https://w3id.org/wlo/curriculum/vocab#"
_DOCUMENT = """
SELECT d.conversion_id, s.notation FROM document d JOIN vocab_concept s ON s.iri = d.sector_iri
WHERE d.id = %s
"""
_LOCK = "SELECT lock_node_tree(%s)"  # the lock the database's guards take (migration l1_nodes)
_RETIRED = "SELECT iri FROM vocab_concept WHERE iri = ANY(%s) AND retired_in IS NOT NULL ORDER BY iri LIMIT 1"
_NEXT = """
SELECT coalesce(max(position), 0) + 1 FROM node WHERE document_id = %s AND parent_id IS NOT DISTINCT FROM %s
"""
_NODE = """
INSERT INTO node (id, document_id, parent_id, position, function_scheme, function_iri, node_type_iri, code,
    code_assigned, original_title, title_language, obligation_scheme, obligation_iri, scope_share_scheme,
    scope_share_iri, extraction_depth_scheme, extraction_depth_iri, applies_to, origin_scheme, origin_iri,
    review_status_scheme, review_status_iri, rule_id, run_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_STATEMENT = """
INSERT INTO statement (id, document_id, node_id, position, verbatim, language, lead_in, statement_kind_scheme,
    statement_kind_iri, subkind_iri, obligation_scheme, obligation_iri, origin_scheme, origin_iri,
    review_status_scheme, review_status_iri, rule_id, text_hash, details, layout_markers, run_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_ANCHOR = """
INSERT INTO anchor (id, document_id, conversion_id, node_id, statement_id, page_start, page_end, printed_page,
    quote, match_kind_scheme, match_kind_iri, match_score, char_start, char_end, table_cell)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
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


async def write_subtree(
    connection: psycopg.AsyncConnection,
    document_id: UUID,
    root: NodeDraft,
    *,
    parent_id: UUID | None = None,
    run_id: UUID | None = None,
) -> UUID:
    """Write ``root`` with all it holds under ``parent_id`` (the document's top where None), after
    the siblings there, as the run ``run_id`` made it (one of the document's); its id.
    ProfileValueError for a profile value the document's profile does not hold or a core value
    retired, DocumentError or the database's error, and then nothing of it is written."""
    async with connection.transaction():
        cursor = await connection.execute(_DOCUMENT, (document_id,))
        found = await cursor.fetchone()
        if found is None:
            raise DocumentError(f"no document {document_id}")
        conversion_id, sector = found
        _check(root, await profile_concepts(connection, sector))
        cursor = await connection.execute(_RETIRED, (sorted(_core_values(root)),))
        if (retired := await cursor.fetchone()) is not None:
            raise ProfileValueError("retired", retired[0])
        await lock_tree(connection, document_id)
        cursor = await connection.execute(_NEXT, (document_id, parent_id))
        position = await cursor.fetchone()
        assert position is not None  # noqa: S101 - an aggregate yields its row
        writer = _Writer(connection, document_id, conversion_id, run_id)
        return await writer.node(root, parent_id, int(position[0]))


async def lock_tree(connection: psycopg.AsyncConnection, document_id: UUID) -> None:
    """Wait for, then hold until the transaction ends, the lock all writes to the document's tree
    share - subtrees written, nodes moved (migration l1_nodes); within a transaction alone."""
    await connection.execute(_LOCK, (document_id,))


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


def _check(draft: NodeDraft, profile: ProfileConcepts | None) -> None:
    node_types = {} if profile is None else profile.node_types
    subkinds = {} if profile is None else profile.subkinds
    if draft.node_type is not None and (
        problem := check_profile_value(draft.node_type, draft.function, node_types)
    ):
        raise ProfileValueError(problem, draft.node_type)
    for statement in draft.statements:
        if statement.subkind is not None and (
            problem := check_profile_value(statement.subkind, statement.kind, subkinds)
        ):
            raise ProfileValueError(problem, statement.subkind)
    for child in draft.children:
        _check(child, profile)


def _core_values(draft: NodeDraft) -> set[str]:
    """The values of the core's fixed schemes the subtree names - functions, kinds, addressees,
    origins and the like - which may be retired since its draft was made."""
    values = {draft.function, draft.origin, draft.review_status}
    values.update(value for value in (draft.obligation, draft.scope_share, draft.extraction_depth) if value)
    anchors = list(draft.anchors)
    for statement in draft.statements:
        values.update((statement.kind, statement.origin, statement.review_status))
        values.update((*statement.addressees, *statement.layout_markers))
        if statement.obligation is not None:
            values.add(statement.obligation)
        anchors.extend(statement.anchors)
    values.update(anchor.match_kind for anchor in anchors if anchor.match_kind)
    for child in draft.children:
        values |= _core_values(child)
    return values


def _pair(scheme: str, iri: str | None) -> tuple[str | None, str | None]:
    """A value of a fixed scheme as its two columns, or none."""
    return (None, None) if iri is None else (CV + scheme, iri)


@dataclass(frozen=True)
class _Writer:
    connection: psycopg.AsyncConnection
    document_id: UUID
    conversion_id: UUID
    run_id: UUID | None

    async def node(self, draft: NodeDraft, parent_id: UUID | None, position: int) -> UUID:
        node_id = await self._entity("node")
        await self.connection.execute(
            _NODE,
            (
                node_id,
                self.document_id,
                parent_id,
                position,
                *_pair("NodeFunctions", draft.function),
                draft.node_type,
                draft.code,
                draft.code_assigned,
                draft.original_title,
                draft.title_language,
                *_pair("Obligations", draft.obligation),
                *_pair("ScopeShares", draft.scope_share),
                *_pair("ExtractionDepths", draft.extraction_depth),
                list(draft.applies_to),
                *_pair("Origins", draft.origin),
                *_pair("ReviewStatuses", draft.review_status),
                draft.rule_id,
                self.run_id,
            ),
        )
        for anchor in draft.anchors:
            await self.anchor(anchor, node_id=node_id)
        for place, statement in enumerate(draft.statements, start=1):
            await self.statement(statement, node_id, place)
        for place, child in enumerate(draft.children, start=1):
            await self.node(child, node_id, place)
        return node_id

    async def statement(self, draft: StatementDraft, node_id: UUID, position: int) -> None:
        statement_id = await self._entity("statement")
        await self.connection.execute(
            _STATEMENT,
            (
                statement_id,
                self.document_id,
                node_id,
                position,
                draft.verbatim,
                draft.language,
                draft.lead_in,
                *_pair("StatementKinds", draft.kind),
                draft.subkind,
                *_pair("Obligations", draft.obligation),
                *_pair("Origins", draft.origin),
                *_pair("ReviewStatuses", draft.review_status),
                draft.rule_id,
                text_hash(draft.verbatim),
                Jsonb(dict(draft.details)),
                list(draft.layout_markers),
                self.run_id,
            ),
        )
        async with self.connection.cursor() as cursor:
            await cursor.executemany(
                "INSERT INTO statement_addressee (statement_id, addressee_scheme, addressee_iri)"
                " VALUES (%s, %s, %s)",
                [(statement_id, CV + "Addressees", addressee) for addressee in draft.addressees],
            )
        for anchor in draft.anchors:
            await self.anchor(anchor, statement_id=statement_id)

    async def anchor(
        self, draft: AnchorDraft, *, node_id: UUID | None = None, statement_id: UUID | None = None
    ) -> None:
        anchor_id = await self._entity("anchor")
        await self.connection.execute(
            _ANCHOR,
            (
                anchor_id,
                self.document_id,
                self.conversion_id,
                node_id,
                statement_id,
                draft.page_start,
                draft.page_end,
                draft.printed_page,
                draft.quote,
                *_pair("MatchKinds", draft.match_kind),
                draft.match_score,
                draft.char_start,
                draft.char_end,
                draft.table_cell,
            ),
        )
        async with self.connection.cursor() as cursor:
            await cursor.executemany(
                "INSERT INTO anchor_block (anchor_id, conversion_id, block_id) VALUES (%s, %s, %s)",
                [(anchor_id, self.conversion_id, block) for block in draft.block_ids],
            )

    async def _entity(self, kind: str) -> UUID:
        made = new_id()
        await self.connection.execute("INSERT INTO entity (id, kind) VALUES (%s, %s)", (made, kind))
        return made
