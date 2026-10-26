"""A document's structure in the store (plan M1 4.6): written one subtree at a time, whole or not
at all; read back as a tree by those who see its document in app/db/tree.py.

A subtree goes under a node of its document, or at its top, after the siblings there; the
positions of its nodes and statements are where they stand in their drafts, from 1. Statements are
also added to a node that stands, from a position the caller gives (X4's units). A node type
and a subkind are checked before anything is written: each is one of the document's sector's
profile and refines the core value beside it (the database checks the latter as well), and no
core value it names is retired. Anchors name blocks of the document's own conversion, by the
database's keys. Writes to one document's tree wait for each other, as moves of its nodes do
(``lock_tree``, migration l1_nodes).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.db.anchors import new_entity, write_anchor
from app.db.documents import DocumentError, ProfileValueError
from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft, check_profile_value
from app.domain.wording import text_hash
from app.vocab.lookup import ProfileConcepts, profile_concepts

CV = "https://w3id.org/wlo/curriculum/vocab#"
_DOCUMENT = """
SELECT d.conversion_id, s.notation FROM document d JOIN vocab_concept s ON s.iri = d.sector_iri
WHERE d.id = %s
"""
_LOCK = "SELECT lock_node_tree(%s)"  # the lock the database's guards take (migration l1_nodes)
_OF_DOCUMENT = "SELECT 1 FROM node WHERE id = %s AND document_id = %s"
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
        conversion_id, sector = await _document(connection, document_id)
        _check(root, await profile_concepts(connection, sector))
        await _none_retired(connection, _core_values(root))
        await lock_tree(connection, document_id)
        cursor = await connection.execute(_NEXT, (document_id, parent_id))
        position = await cursor.fetchone()
        assert position is not None  # noqa: S101 - an aggregate yields its row
        writer = _Writer(connection, document_id, conversion_id, run_id)
        return await writer.node(root, parent_id, int(position[0]))


async def append_statements(
    connection: psycopg.AsyncConnection,
    document_id: UUID,
    node_id: UUID,
    statements: Sequence[StatementDraft],
    *,
    first_position: int,
    run_id: UUID | None = None,
) -> list[UUID]:
    """Write ``statements`` at the node ``node_id`` of the document, from ``first_position`` on, as
    the run ``run_id`` made them; their ids. Checked as a subtree's are - ProfileValueError for a
    subkind the profile does not hold for its kind or a core value retired, DocumentError for a node
    the document does not hold - and then nothing of them is written. They wait for, and then hold,
    the tree's lock as every write to it does (``lock_tree``): an editor renumbering the node's
    statements and a unit adding to it take turns."""
    async with connection.transaction():
        conversion_id, sector = await _document(connection, document_id)
        profile = await profile_concepts(connection, sector)
        _check_statements(statements, {} if profile is None else profile.subkinds)
        values: set[str] = set()
        for statement in statements:
            values |= _statement_values(statement)
        await _none_retired(connection, values)
        await lock_tree(connection, document_id)
        cursor = await connection.execute(_OF_DOCUMENT, (node_id, document_id))
        if await cursor.fetchone() is None:
            raise DocumentError(f"no node {node_id} in document {document_id}")
        writer = _Writer(connection, document_id, conversion_id, run_id)
        return [
            await writer.statement(statement, node_id, first_position + place)
            for place, statement in enumerate(statements)
        ]


async def drop_statements(
    connection: psycopg.AsyncConnection, document_id: UUID, statement_ids: Sequence[UUID]
) -> int:
    """Take the document's statements ``statement_ids`` away - their addressees, anchors and the anchors'
    blocks go with them - under the tree's lock, which whoever changes a tree takes first (plan M1,
    Paket 4: X6 and the editors); how many went. Ids of no statement of the document take none. In a
    transaction of its own, or the caller's (as a savepoint), so that the lock holds over the delete."""
    async with connection.transaction():
        await lock_tree(connection, document_id)
        cursor = await connection.execute(
            "DELETE FROM statement WHERE document_id = %s AND id = ANY(%s)",
            (document_id, list(statement_ids)),
        )
    return cursor.rowcount


async def lock_tree(connection: psycopg.AsyncConnection, document_id: UUID) -> None:
    """Wait for, then hold until the transaction ends, the lock all writes to the document's tree
    share - subtrees written, nodes moved (migration l1_nodes); within a transaction alone."""
    await connection.execute(_LOCK, (document_id,))


async def _document(connection: psycopg.AsyncConnection, document_id: UUID) -> tuple[UUID, str]:
    """The document's conversion and the notation of its sector; DocumentError for none."""
    cursor = await connection.execute(_DOCUMENT, (document_id,))
    found = await cursor.fetchone()
    if found is None:
        raise DocumentError(f"no document {document_id}")
    return found[0], found[1]


async def _none_retired(connection: psycopg.AsyncConnection, values: set[str]) -> None:
    cursor = await connection.execute(_RETIRED, (sorted(values),))
    if (retired := await cursor.fetchone()) is not None:
        raise ProfileValueError("retired", retired[0])


def _check(draft: NodeDraft, profile: ProfileConcepts | None) -> None:
    node_types = {} if profile is None else profile.node_types
    if draft.node_type is not None and (
        problem := check_profile_value(draft.node_type, draft.function, node_types)
    ):
        raise ProfileValueError(problem, draft.node_type)
    _check_statements(draft.statements, {} if profile is None else profile.subkinds)
    for child in draft.children:
        _check(child, profile)


def _check_statements(statements: Sequence[StatementDraft], subkinds: Mapping[str, tuple[str, ...]]) -> None:
    for statement in statements:
        if statement.subkind is not None and (
            problem := check_profile_value(statement.subkind, statement.kind, subkinds)
        ):
            raise ProfileValueError(problem, statement.subkind)


def _core_values(draft: NodeDraft) -> set[str]:
    """The values of the core's fixed schemes the subtree names - functions, kinds, addressees,
    origins and the like - which may be retired since its draft was made."""
    values = {draft.function, draft.origin, draft.review_status}
    values.update(value for value in (draft.obligation, draft.scope_share, draft.extraction_depth) if value)
    values.update(anchor.match_kind for anchor in draft.anchors if anchor.match_kind)
    for statement in draft.statements:
        values |= _statement_values(statement)
    for child in draft.children:
        values |= _core_values(child)
    return values


def _statement_values(statement: StatementDraft) -> set[str]:
    """The core values a statement names, its anchors' too."""
    values = {statement.kind, statement.origin, statement.review_status}
    values.update((*statement.addressees, *statement.layout_markers))
    if statement.obligation is not None:
        values.add(statement.obligation)
    values.update(anchor.match_kind for anchor in statement.anchors if anchor.match_kind)
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

    async def statement(self, draft: StatementDraft, node_id: UUID, position: int) -> UUID:
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
        return statement_id

    async def anchor(
        self, draft: AnchorDraft, *, node_id: UUID | None = None, statement_id: UUID | None = None
    ) -> None:
        await write_anchor(
            self.connection,
            self.document_id,
            self.conversion_id,
            draft,
            node_id=node_id,
            statement_id=statement_id,
        )

    async def _entity(self, kind: str) -> UUID:
        return await new_entity(self.connection, kind)
