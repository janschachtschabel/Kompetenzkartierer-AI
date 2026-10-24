"""What a stage finds on a document (plan M1 6.2, 8; table validation_finding): a value outside the
profile, a block id nobody showed, a work the document may be an edition of. A finding is kept, never a
failure of its run: the run goes on without the value, and the editors see why. Written with the
stage's result, in its transaction, so that findings go with their run."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.core.ids import new_id
from app.domain.l1 import Severity

MOST_MESSAGE_SIGNS = 4000  # as the table holds them
_ADD = """
    INSERT INTO validation_finding (id, document_id, run_id, rule, severity, focus_id, path, message, details)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
