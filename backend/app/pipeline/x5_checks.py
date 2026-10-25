"""X5's plausibility checks (plan M1 8.2): what SHACL cannot see of the first layer, each a finding on
the row it is about.

- ``x5.heading_as_statement``: a statement that is its node's heading - the same text hash, numbering
  aside (the X4 rules say a heading is no statement).
- ``x5.unit_without_statements``: a unit read whole that holds no statement and checked nothing absent;
  at its node, else at the document.
- ``x5.rule_bounds``: a rule of the frame whose lower bound lies above its upper one, or whose share is
  no share.
- ``x5.retired_value``: a function, node type, statement kind or subkind or obligation the vocabularies
  have retired since it was written.

What SHACL checks is not checked again here: required fields, a subkind under its kind, a node type
under its function (cur-shapes.ttl). No vocabulary says which statement kinds a node type takes, and the
first layer holds no hours or shares to sum (plan M1, Nachtrag 8a).
"""

from typing import Any
from uuid import UUID

import psycopg

from app.db.findings import Finding
from app.domain.wording import text_hash

_HEADED = """
SELECT s.id, s.text_hash, n.original_title FROM statement s JOIN node n ON n.id = s.node_id
WHERE s.document_id = %s AND n.original_title IS NOT NULL
"""
_EMPTY_UNITS = """
SELECT unit_key, node_id FROM extraction_unit
WHERE document_id = %s AND statements = 0 AND cardinality(checked_absent) = 0 ORDER BY unit_key
"""
_RULES = "SELECT id, content FROM frame_part WHERE document_id = %s AND part_kind = 'rules' ORDER BY position"
_RETIRED = """
SELECT n.id, value.field, value.iri FROM node n
CROSS JOIN LATERAL (VALUES ('nodeFunction', n.function_iri), ('nodeType', n.node_type_iri),
    ('obligation', n.obligation_iri)) AS value (field, iri)
JOIN vocab_concept c ON c.iri = value.iri
WHERE n.document_id = %(document)s AND c.retired_in IS NOT NULL
UNION ALL
SELECT s.id, value.field, value.iri FROM statement s
CROSS JOIN LATERAL (VALUES ('statementKind', s.statement_kind_iri), ('statementSubkind', s.subkind_iri),
    ('obligation', s.obligation_iri)) AS value (field, iri)
JOIN vocab_concept c ON c.iri = value.iri
WHERE s.document_id = %(document)s AND c.retired_in IS NOT NULL
"""
_BOUNDS = (("minCount", "maxCount"), ("minAmount", "maxAmount"))


async def plausibility(connection: psycopg.AsyncConnection, document_id: UUID) -> list[Finding]:
    """The document's findings of the four checks."""
    return [
        *await _headings_as_statements(connection, document_id),
        *await _units_without_statements(connection, document_id),
        *await _rules_out_of_bounds(connection, document_id),
        *await _retired_values(connection, document_id),
    ]


async def _headings_as_statements(connection: psycopg.AsyncConnection, document_id: UUID) -> list[Finding]:
    cursor = await connection.execute(_HEADED, (document_id,))
    return [
        Finding("x5.heading_as_statement", "warning", found, "a statement that is its node's heading")
        for found, hashed, title in await cursor.fetchall()
        if hashed == text_hash(title)
    ]


async def _units_without_statements(connection: psycopg.AsyncConnection, document_id: UUID) -> list[Finding]:
    cursor = await connection.execute(_EMPTY_UNITS, (document_id,))
    return [
        Finding(
            "x5.unit_without_statements",
            "info",
            node_id or document_id,
            "a unit read whole holds no statement",
            details={"unit": key},
        )
        for key, node_id in await cursor.fetchall()
    ]


async def _rules_out_of_bounds(connection: psycopg.AsyncConnection, document_id: UUID) -> list[Finding]:
    cursor = await connection.execute(_RULES, (document_id,))
    found = []
    for part, content in await cursor.fetchall():
        for wrong in _contradictions(content):
            found.append(
                Finding("x5.rule_bounds", "warning", part, "a rule's bounds contradict", details=wrong)
            )
    return found


def _contradictions(content: dict[str, Any]) -> list[dict[str, Any]]:
    wrong = [
        {low: content[low], high: content[high]}
        for low, high in _BOUNDS
        if content.get(low) is not None and content.get(high) is not None and content[low] > content[high]
    ]
    share = content.get("maxShare")
    if share is not None and not 0 <= share <= 1:
        wrong.append({"maxShare": share})
    return wrong


async def _retired_values(connection: psycopg.AsyncConnection, document_id: UUID) -> list[Finding]:
    cursor = await connection.execute(_RETIRED, {"document": document_id})
    return [
        Finding(
            "x5.retired_value",
            "warning",
            found,
            "a value the vocabularies have retired",
            path=f"cur:{field}",
            details={"value": iri},
        )
        for found, field, iri in await cursor.fetchall()
    ]
