"""A document's units as its page shows them (plan M1 7b, F13): X2's work packages, in the document's
order, each with how far X4 has come - done (with the statements it wrote), open, or none of X4's:
read typed by X3 (frame) or not read at all (none). A document before X2 has none.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import psycopg

from app.db.runs import stage_result
from app.db.units import done_units
from app.pipeline.x2_segments import WorkPackage

UnitState = Literal["done", "open", "frame", "none"]


@dataclass(frozen=True)
class UnitView:
    key: str
    path: tuple[str, ...]
    pages: tuple[int, int]
    state: UnitState
    statements: int | None  # written by X4, once done


async def document_units(connection: psycopg.AsyncConnection, document_id: UUID) -> list[UnitView]:
    """The document's units, as the last run of X2 done on it parted it."""
    kept = await stage_result(connection, document_id, "X2")
    done = await done_units(connection, document_id)
    units = []
    for package in map(WorkPackage.from_result, (kept or {}).get("packages", [])):
        done_or_open: UnitState = "done" if package.key in done else "open"
        state: UnitState = done_or_open if package.job == "statements" else package.job
        statements = done[package.key].statements if state == "done" else None
        units.append(UnitView(package.key, package.path, package.pages, state, statements))
    return units
