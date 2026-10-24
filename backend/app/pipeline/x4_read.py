"""X4's answer for a unit read (plan M1 7b, F9; schema x4-aussagen). An answer for another unit than
the one asked about is none: the unit stays open. Its statements are read as X3's are
(app/pipeline/statement_read.py), from the unit's own blocks alone; what it checked absent is kept
as the docking points' IRIs (cv:DockingPoints), each once, for the unit's row (extraction_unit).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.db.findings import Finding
from app.pipeline.statement_read import Reading, ReadStatement, StatementContext
from app.pipeline.x2_segments import WorkPackage


class WrongUnit(Exception):
    """The answer names another unit than the one asked about."""


@dataclass(frozen=True)
class UnitReading:
    statements: list[ReadStatement]  # in the document's order
    checked_absent: tuple[str, ...]  # IRIs of cv:DockingPoints
    findings: list[Finding]


def read_unit(answer: Mapping[str, Any], context: StatementContext, unit: WorkPackage) -> UnitReading:
    """The unit's statements and what it checked absent; WrongUnit for an answer about another."""
    if answer["unitKey"].strip() != unit.key:
        raise WrongUnit(f"an answer for {answer['unitKey']!r}, not for {unit.key}")
    reading = Reading(context)
    statements = reading.statements(answer["statements"], range(unit.first, unit.last + 1))
    absent = [
        reading.code("DockingPoints", point, f"$.checkedAbsent[{at}]")
        for at, point in enumerate(answer["checkedAbsent"])
    ]
    return UnitReading(statements, tuple(dict.fromkeys(iri for iri in absent if iri)), reading.findings)
