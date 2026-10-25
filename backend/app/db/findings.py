"""What a stage finds on a document (plan M1 6.2, 8; table validation_finding): a value outside the
profile, a block id nobody showed, a work the document may be an edition of. A finding is kept, never a
failure of its run: the run goes on without the value, and the editors see why. Written with the
stage's result, in its transaction, so that findings go with their run; read for the document's page,
gravest first, each with the row it is about. A stage that runs again (X5 after a repair, plan M1 8b)
drops the findings of its earlier runs: they describe a document that is no more."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.core.ids import new_id
from app.db.runs import Stage, stage_iri
from app.domain.l1 import Severity

MOST_MESSAGE_SIGNS = 4000  # as the table holds them
MOST_FINDINGS = 500  # what a page lists of a document's findings
LABEL_SIGNS = 160  # of the row a finding is about, what a list shows
SEVERITIES: tuple[Severity, ...] = ("violation", "warning", "info")  # gravest first
_ADD = """
    INSERT INTO validation_finding (id, document_id, run_id, rule, severity, focus_id, path, message, details)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
# The row a finding is about by its entity's kind, named by its wording or title; the stage of its run
_ROWS = """
SELECT f.rule, f.severity, replace(r.stage_iri, %(stages)s, ''), e.kind, f.focus_id,
    left(coalesce(s.verbatim, n.original_title, n.code, sp.title, d.title), %(label)s), f.path, f.message,
    f.details ->> 'unit'
FROM validation_finding f
JOIN entity e ON e.id = f.focus_id
LEFT JOIN extraction_run r ON r.id = f.run_id
LEFT JOIN statement s ON s.id = f.focus_id
LEFT JOIN node n ON n.id = f.focus_id
LEFT JOIN specification sp ON sp.id = f.focus_id
LEFT JOIN document d ON d.id = f.focus_id
WHERE f.document_id = %(document)s
ORDER BY array_position(%(severities)s::text[], f.severity), r.stage_iri, f.rule, f.created_at, f.id
LIMIT %(most)s
"""
_COUNTS = "SELECT severity, count(*) FROM validation_finding WHERE document_id = %s GROUP BY severity"
_DROP = """
DELETE FROM validation_finding f USING extraction_run r
WHERE f.document_id = %s AND r.id = f.run_id AND r.stage_iri = %s AND f.run_id <> %s
"""


@dataclass(frozen=True)
class Finding:
    """``rule`` names what was found ("x1.not_in_profile"); ``focus_id`` the row it is about - the
    document itself where it is about the whole; ``path`` the property, where it is one."""

    rule: str
    severity: Severity
    focus_id: UUID
    message: str
    path: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FindingRow:
    """A finding as the document's page lists it: ``stage`` its run's ("X5"), ``focus_kind`` the kind of
    the row it is about ("statement", "node", "document" …) and ``focus_label`` that row's wording or
    title, where it has one; ``unit`` the work package it names."""

    rule: str
    severity: Severity
    stage: str | None
    focus_kind: str
    focus_id: UUID
    focus_label: str | None
    path: str | None
    message: str
    unit: str | None


@dataclass(frozen=True)
class FindingsPage:
    counts: dict[Severity, int]  # of all the document's findings
    rows: list[FindingRow]  # at most the most asked for
    truncated: bool


async def findings_of(
    connection: psycopg.AsyncConnection, document_id: UUID, *, most: int = MOST_FINDINGS
) -> FindingsPage:
    """The document's findings, gravest first, then by stage and rule - at most ``most`` of them."""
    cursor = await connection.execute(
        _ROWS,
        {
            "document": document_id,
            "stages": stage_iri("X0").removesuffix("X0"),
            "label": LABEL_SIGNS,
            "severities": list(SEVERITIES),
            "most": most + 1,
        },
    )
    rows = [FindingRow(*row) for row in await cursor.fetchall()]
    cursor = await connection.execute(_COUNTS, (document_id,))
    counted: dict[str, int] = dict(await cursor.fetchall())
    return FindingsPage(
        {severity: counted.get(severity, 0) for severity in SEVERITIES}, rows[:most], len(rows) > most
    )


async def drop_stage_findings(
    connection: psycopg.AsyncConnection, document_id: UUID, stage: Stage, *, keep_run: UUID
) -> int:
    """Drop the findings of the stage's runs on the document but ``keep_run``; how many went."""
    cursor = await connection.execute(_DROP, (document_id, stage_iri(stage), keep_run))
    return cursor.rowcount


async def add_findings(
    connection: psycopg.AsyncConnection, document_id: UUID, run_id: UUID | None, findings: Sequence[Finding]
) -> None:
    """Keep the findings of the run, a message past MOST_MESSAGE_SIGNS cut to them."""
    if not findings:
        return
    async with connection.cursor() as cursor:
        await cursor.executemany(
            _ADD,
            [
                (
                    new_id(),
                    document_id,
                    run_id,
                    finding.rule,
                    finding.severity,
                    finding.focus_id,
                    finding.path,
                    finding.message[:MOST_MESSAGE_SIGNS],
                    Jsonb(dict(finding.details)),
                )
                for finding in findings
            ],
        )
