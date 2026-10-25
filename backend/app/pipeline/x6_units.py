"""Which work packages X6 asks the model again (plan M1 8b, Festlegung F1; konzept §13.2: "nur
fehlerhafte Einheiten erneut"): a package X4 did whose statements the model left wrong, and that was
not repaired twice already (extraction_unit.repairs).

Wrong is a violation on a statement X4 or X6 wrote that nobody has touched since - origin model,
proposed, its first revision - such as a wording its blocks do not hold, or a warning of reading the
model's answer for the package (``details.unit``): the answer lost a statement or a value. A lexicon
pattern that ran out of time is no fault of the answer. Hints, SHACL's warnings (plausibility, the
profiles' rules - the editors' to weigh, and those of L2 certain in M1), findings on nodes, frame parts
or the document (X1 to X3), and packages X4 has not done (extract.run asks them) are no cause.

A statement is the package's whose part of the node holds its position (app/pipeline/x4_unit.py,
PART); under X4's own node of a package without a heading, that package's. The statements of the
package the editors hold - changed, confirmed, rejected or written by hand - are named, as the repair
keeps them and is not to bring them again.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.db.runs import stage_iri, stage_result
from app.db.units import UnitDone, done_units
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x4_unit import PART, first_position

MOST_REPAIRS = 2  # as migration unit_repairs holds them
_CV = "https://w3id.org/wlo/curriculum/vocab#"
_ASKED = {
    "written": [stage_iri("X4"), stage_iri("X6")],  # the stages whose statements a repair writes anew
    "model": _CV + "orig_model",
    "proposed": _CV + "rev_proposed",
}
# a statement as the pipeline wrote it, nobody's since: origin model, proposed, its first revision
_ON_STATEMENTS = """
SELECT f.rule, f.message, f.path, s.node_id, s.position, s.verbatim
FROM validation_finding f
JOIN statement s ON s.id = f.focus_id
JOIN extraction_run r ON r.id = s.run_id
WHERE f.document_id = %(document)s AND f.severity = 'violation' AND r.stage_iri = ANY(%(written)s)
    AND s.origin_iri = %(model)s AND s.review_status_iri = %(proposed)s AND s.revision = 1
ORDER BY s.node_id, s.position, f.rule, f.created_at
"""
_OF_READING = """
SELECT f.details ->> 'unit', f.rule, f.message, f.path
FROM validation_finding f
JOIN extraction_run r ON r.id = f.run_id
WHERE f.document_id = %(document)s AND f.severity IN ('violation', 'warning')
    AND r.stage_iri = ANY(%(written)s) AND f.details ? 'unit' AND f.rule NOT LIKE '%%.pattern_timeout'
ORDER BY f.rule, f.path, f.created_at
"""
_HELD = """
SELECT s.node_id, s.position, s.verbatim FROM statement s
WHERE s.document_id = %(document)s
    AND NOT (s.origin_iri = %(model)s AND s.review_status_iri = %(proposed)s AND s.revision = 1)
ORDER BY s.node_id, s.position
"""


@dataclass(frozen=True)
class Defect:
    """What a finding says is wrong: its rule and message, the statement's wording where it is on one,
    the place in the answer or the property where it names one."""

    rule: str
    message: str
    wording: str | None
    path: str | None


@dataclass(frozen=True)
class RepairUnit:
    package: WorkPackage
    node_id: UUID | None  # the node its statements stand at (X4's own for a package under no heading)
    first: int  # the first position of its part of the node
    defects: tuple[Defect, ...]
    kept: tuple[str, ...]  # the wordings of its statements the editors hold


async def repairable_units(connection: psycopg.AsyncConnection, document_id: UUID) -> list[RepairUnit]:
    """The document's packages X6 asks again, in the document's order, each with its defects."""
    result = await stage_result(connection, document_id, "X2")
    packages = [WorkPackage.from_result(kept) for kept in (result or {}).get("packages", [])]
    done = await done_units(connection, document_id)
    places = _Places(packages, done)
    defects: dict[str, list[Defect]] = {}
    asked = _ASKED | {"document": document_id}
    cursor = await connection.execute(_ON_STATEMENTS, asked)
    for rule, message, path, node_id, position, verbatim in await cursor.fetchall():
        if (key := places.unit_of(node_id, position)) is not None:
            defects.setdefault(key, []).append(Defect(rule, message, verbatim, path))
    cursor = await connection.execute(_OF_READING, asked)
    for key, rule, message, path in await cursor.fetchall():
        defects.setdefault(key, []).append(Defect(rule, message, None, path))
    kept: dict[str, list[str]] = {}
    cursor = await connection.execute(_HELD, asked)
    for node_id, position, verbatim in await cursor.fetchall():
        if (key := places.unit_of(node_id, position)) is not None:
            kept.setdefault(key, []).append(verbatim)
    return [
        RepairUnit(
            item,
            done[item.key].node_id,
            places.first(item),
            tuple(defects[item.key]),
            tuple(kept.get(item.key, ())),
        )
        for item in packages
        if item.key in defects and places.repairable(item)
    ]


class _Places:
    """Where a package's statements stand: its part of its node, or X4's node of its own."""

    def __init__(self, packages: Sequence[WorkPackage], done: dict[str, UnitDone]) -> None:
        self.packages = packages
        self.done = done
        by_key = {item.key: item for item in packages}
        self.own = {  # X4's node of a package under no heading, and that package
            unit.node_id: unit.key
            for unit in done.values()
            if unit.node_id is not None and unit.key in by_key and by_key[unit.key].node_id is None
        }

    def first(self, package: WorkPackage) -> int:
        return 1 if package.node_id is None else first_position(package, self.packages)

    def unit_of(self, node_id: UUID, position: int) -> str | None:
        if node_id in self.own:
            return self.own[node_id]
        parts = [item for item in self.packages if item.node_id == node_id]
        part = (position - 1) // PART
        return parts[part].key if 0 <= part < len(parts) else None

    def repairable(self, package: WorkPackage) -> bool:
        # done: X4 marked it - only X4 marks packages, never one X3 reads typed
        done = self.done.get(package.key)
        return done is not None and done.repairs < MOST_REPAIRS
