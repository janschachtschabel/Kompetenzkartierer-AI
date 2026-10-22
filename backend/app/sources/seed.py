"""``python -m app.sources.seed [DOCUMENTS [NOTES]]``: the comparison dataset v62.493 into the register.

Its rows become candidates of no account, unchecked (plan M1, 2.2; Gesamtplan §7.5): what was
published of a curriculum - its address and archived copy, land, school form, subject, grades,
binding, kind of source - never the dataset's titles, descriptions, themes or node counts; the
register names an entry itself ("Bayern · Physik · Gymnasium"). ESA derivations (a plan of
another school form, cut short) and "kanonisch" rows (no document of the land's own) are no
curricula of their own and are left out. A second run adds nothing: a row's key is its
Beispiel_ID. The dataset's notes on blocked portals and detours come with it, as access notes
(app/sources/access_notes.py).

Exit code 0 when the register holds the dataset afterwards (seeded now or before), 1 when the
file or the database refused. Logs go to stderr.
"""

import asyncio
import csv
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

from app.core.ids import new_id
from app.core.logging import configure_logging
from app.core.settings import Settings
from app.db.pool import CONNECTION_OPTIONS
from app.db.sources import sector_by_notation
from app.sources.access_notes import NOTES, Notes, NotesReport, read_notes, record_notes
from app.sources.register import (
    COMPARISON_DATASET,
    EDUCATION_SECTORS,
    SEED_DIR,
    Evidence,
    SeedDataset,
    SourceType,
    land_country,
)
from app.sources.url_fetch import UrlNotAllowed, check_url

log = logging.getLogger("app.sources.seed")  # also when run as __main__

DATASET = COMPARISON_DATASET
DOCUMENTS = SEED_DIR / "lehrplan_dokumente_de.csv"
# The dataset's kind of source, as the register says who publishes the copy
_KINDS: dict[str, SourceType] = {
    "Landesportal": "amtlich",
    "KMK": "amtlich",
    "Wayback-Archiv": "archiv",
    "GEI-Depot": "archiv",
    "Drittquelle/Spiegel": "spiegel",
}
# One seed at a time. Two runs at once would each find the rows absent, and the second would
# fail on source_seed's UNIQUE key once the first commits; held, it waits and adds nothing
_SEED_LOCK = int.from_bytes(b"kka-seed", "big")
# An address with a note for its readers after it: "https://… (Sidebar, PK-Katalog)" (BW.MA.PK)
_NOTED = re.compile(r"(\S+)\s+\([^()]*\)")


class SeedError(Exception):
    """The register cannot take the seed (the education sectors are not loaded)."""


@dataclass(frozen=True)
class SeedRow:
    """A candidate of a seed dataset; what its dataset does not say stays None."""

    key: str
    title: str
    url: str
    country: str | None = None
    school_form: str | None = None
    stage: str | None = None
    subject_key: str | None = None
    subject: str | None = None
    grade_from: int | None = None
    grade_to: int | None = None
    binding: str | None = None
    source_type: SourceType | None = None
    archive_url: str | None = None
    archived_at: str | None = None
    sector: str = "school"  # its notation in cv:EducationSectors
    evidence: Evidence | None = None


@dataclass(frozen=True)
class Documents:
    rows: list[SeedRow]
    # why rows were left out: esa, kanonisch, url_invalid
    left_out: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True)
class SeedReport:
    added: int
    present: int  # of the file's rows, in the register already


def read_documents(path: Path) -> Documents:
    """The candidates of the dataset's documents file, and how many rows were left out, by why."""
    rows: list[SeedRow] = []
    left_out: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle, delimiter=";"):
            if raw["ESA-Ableitung"].strip() == "ja":
                left_out["esa"] += 1
            elif raw["Verifikation"].strip() == "kanonisch":
                left_out["kanonisch"] += 1
            else:
                try:
                    rows.append(_row(raw))
                except UrlNotAllowed:
                    left_out["url_invalid"] += 1
    return Documents(rows, left_out)


def _row(raw: dict[str, str]) -> SeedRow:
    address = (raw["URL_Original"] if raw["URL"].strip() == "lokal" else raw["URL"]).strip()
    noted = _NOTED.fullmatch(address)
    parts = (_text(raw["Land"], 80), _text(raw["Fach"], 200), _text(raw["Schulform"], 200))
    return SeedRow(
        key=raw["Beispiel_ID"].strip(),
        title=" · ".join(part for part in parts if part),
        url=check_url(noted.group(1) if noted else address),
        country=land_country(raw["Land_Kuerzel"]),
        school_form=_text(raw["Schulform"], 200),
        stage=_text(raw["Bildungsstufe"], 200),
        subject_key=_text(raw["Fach_Schluessel"], 100),
        subject=_text(raw["Fach"], 200),
        grade_from=_grade(raw["Jahrgang_von"]),
        grade_to=_grade(raw["Jahrgang_bis"]),
        binding=_text(raw["Verbindlichkeit"], 500),
        source_type=_KINDS.get(raw["Quelltyp"].strip()),
        archive_url=_archive(raw["URL_Archiv"]),
        archived_at=_text(raw["Wayback_Zeitstempel"], 40),
    )


def _text(value: str, limit: int) -> str | None:
    value = " ".join(value.split())
    return value[:limit] or None


def _grade(value: str) -> int | None:
    value = value.strip()
    return int(value) if value.isdigit() and int(value) <= 13 else None


def _archive(value: str) -> str | None:
    try:
        return check_url(value.strip()) if value.strip() else None
    except UrlNotAllowed:
        return None


async def seed_register(
    connection: psycopg.AsyncConnection, rows: list[SeedRow], dataset: SeedDataset = DATASET
) -> SeedReport:
    """Add the rows of the dataset the register lacks, in one transaction; SeedError without the
    sectors they name."""
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(%s)", (_SEED_LOCK,))
        notations = sorted({row.sector for row in rows})
        sectors = {notation: await sector_by_notation(connection, notation) for notation in notations}
        missing = ", ".join(notation for notation, iri in sectors.items() if iri is None)
        if missing:
            raise SeedError(
                f"the education sectors are not loaded ({missing}): run python -m app.vocab.load first"
            )
        cursor = await connection.execute("SELECT seed_key FROM source_seed WHERE dataset = %s", (dataset,))
        present = {key for (key,) in await cursor.fetchall()}
        new = [(new_id(), row) for row in rows if row.key not in present]
        async with connection.cursor() as writer:
            await writer.executemany(
                "INSERT INTO entity (id, kind) VALUES (%s, 'source')", [(id_,) for id_, _ in new]
            )
            await writer.executemany(
                "INSERT INTO source (id, provenance, title, url, country, sector_scheme, sector_iri,"
                " source_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        id_,
                        dataset,
                        row.title,
                        row.url,
                        row.country,
                        EDUCATION_SECTORS,
                        sectors[row.sector],
                        row.source_type,
                    )
                    for id_, row in new
                ],
            )
            await writer.executemany(
                "INSERT INTO source_seed (source_id, dataset, seed_key, school_form, stage, subject_key,"
                " subject, grade_from, grade_to, binding, archive_url, archived_at, evidence)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [_seed_values(id_, dataset, row) for id_, row in new],
            )
    return SeedReport(added=len(new), present=len(rows) - len(new))


def _seed_values(id_: Any, dataset: SeedDataset, row: SeedRow) -> tuple[Any, ...]:
    # grades the wrong way round are no grades: the CHECK would refuse the whole seed
    grades = (row.grade_from, row.grade_to)
    if None not in grades and grades[0] > grades[1]:  # type: ignore[operator]
        grades = (None, None)
    return (
        id_,
        dataset,
        row.key,
        row.school_form,
        row.stage,
        row.subject_key,
        row.subject,
        *grades,
        row.binding,
        row.archive_url,
        row.archived_at,
        row.evidence,
    )


def reasons(left_out: Counter[str]) -> str:
    """Why rows were left out, as the commands log it: "esa 90, kanonisch 243" or "none"."""
    return ", ".join(f"{reason} {count}" for reason, count in sorted(left_out.items())) or "none"


async def _seed(settings: Settings, documents: Documents, notes: Notes) -> tuple[SeedReport, NotesReport]:
    url = settings.database_url.get_secret_value()
    async with await psycopg.AsyncConnection.connect(url, **CONNECTION_OPTIONS) as connection:
        return await seed_register(connection, documents.rows), await record_notes(connection, notes.notes)


def main(arguments: list[str]) -> int:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    documents_path = Path(arguments[0]) if arguments else DOCUMENTS
    notes_path = Path(arguments[1]) if len(arguments) > 1 else NOTES
    try:
        documents, notes = read_documents(documents_path), read_notes(notes_path)
        seeded, noted = asyncio.run(_seed(settings, documents, notes), loop_factory=asyncio.SelectorEventLoop)
    except (SeedError, OSError, csv.Error, KeyError, psycopg.Error) as error:
        log.error("register not seeded: %s", " ".join(str(error).split()))
        return 1
    for what, report, left_out in (
        ("entries", seeded, documents.left_out),
        ("access notes", noted, notes.left_out),
    ):
        log.info(
            "%d %s added, %d in the register already; left out: %s",
            report.added,
            what,
            report.present,
            reasons(left_out),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
