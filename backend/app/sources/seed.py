"""``python -m app.sources.seed [FILE]``: the comparison dataset v62.493 into the source register.

Its rows become candidates of no account, unchecked (plan M1, 2.2; Gesamtplan §7.5): what was
published of a curriculum - its address and archived copy, land, school form, subject, grades,
binding, kind of source - never the dataset's titles, descriptions, themes or node counts; the
register names an entry itself ("Bayern · Physik · Gymnasium"). ESA derivations (a plan of
another school form, cut short) and "kanonisch" rows (no document of the land's own) are no
curricula of their own and are left out. A second run adds nothing: a row's key is its
Beispiel_ID.

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
from app.sources.register import EDUCATION_SECTORS, SeedDataset, SourceType
from app.sources.url_fetch import UrlNotAllowed, check_url

log = logging.getLogger("app.sources.seed")  # also when run as __main__

DATASET: SeedDataset = "vergleichsdatensatz-v62.493"
SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed" / "vergleichsdatensatz"
DOCUMENTS = SEED_DIR / "lehrplan_dokumente_de.csv"
# The dataset's kind of source, as the register says who publishes the copy
_KINDS: dict[str, SourceType] = {
    "Landesportal": "amtlich",
    "KMK": "amtlich",
    "Wayback-Archiv": "archiv",
    "GEI-Depot": "archiv",
    "Drittquelle/Spiegel": "spiegel",
}
# One seed at a time: two runs at once would each find a row absent and add it twice
_SEED_LOCK = int.from_bytes(b"kka-seed", "big")
_LAND = re.compile(r"[A-Z]{2}")
# An address with a note for its readers after it: "https://… (Sidebar, PK-Katalog)" (BW.MA.PK)
_NOTED = re.compile(r"(\S+)\s+\([^()]*\)")


class SeedError(Exception):
    """The register cannot take the seed (the education sectors are not loaded)."""


@dataclass(frozen=True)
class SeedRow:
    key: str
    title: str
    url: str
    country: str | None
    school_form: str | None
    stage: str | None
    subject_key: str | None
    subject: str | None
    grade_from: int | None
    grade_to: int | None
    binding: str | None
    source_type: SourceType | None
    archive_url: str | None
    archived_at: str | None


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
    land = raw["Land_Kuerzel"].strip()
    parts = (_text(raw["Land"], 80), _text(raw["Fach"], 200), _text(raw["Schulform"], 200))
    return SeedRow(
        key=raw["Beispiel_ID"].strip(),
        title=" · ".join(part for part in parts if part),
        url=check_url(noted.group(1) if noted else address),
        country=f"DE-{land}" if _LAND.fullmatch(land) else None,
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


async def seed_register(connection: psycopg.AsyncConnection, rows: list[SeedRow]) -> SeedReport:
    """Add the rows the register lacks, in one transaction; SeedError without the sectors."""
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(%s)", (_SEED_LOCK,))
        sector = await sector_by_notation(connection, "school")
        if sector is None:
            raise SeedError("the education sectors are not loaded: run python -m app.vocab.load first")
        cursor = await connection.execute("SELECT seed_key FROM source_seed WHERE dataset = %s", (DATASET,))
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
                        DATASET,
                        row.title,
                        row.url,
                        row.country,
                        EDUCATION_SECTORS,
                        sector,
                        row.source_type,
                    )
                    for id_, row in new
                ],
            )
            await writer.executemany(
                "INSERT INTO source_seed (source_id, dataset, seed_key, school_form, stage, subject_key,"
                " subject, grade_from, grade_to, binding, archive_url, archived_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [_seed_values(id_, row) for id_, row in new],
            )
    return SeedReport(added=len(new), present=len(rows) - len(new))


def _seed_values(id_: Any, row: SeedRow) -> tuple[Any, ...]:
    # grades the wrong way round are no grades: the CHECK would refuse the whole seed
    grades = (row.grade_from, row.grade_to)
    if None not in grades and grades[0] > grades[1]:  # type: ignore[operator]
        grades = (None, None)
    return (
        id_,
        DATASET,
        row.key,
        row.school_form,
        row.stage,
        row.subject_key,
        row.subject,
        *grades,
        row.binding,
        row.archive_url,
        row.archived_at,
    )


async def _seed(settings: Settings, rows: list[SeedRow]) -> SeedReport:
    url = settings.database_url.get_secret_value()
    async with await psycopg.AsyncConnection.connect(url, **CONNECTION_OPTIONS) as connection:
        return await seed_register(connection, rows)


def main(arguments: list[str]) -> int:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    path = Path(arguments[0]) if arguments else DOCUMENTS
    try:
        documents = read_documents(path)
        report = asyncio.run(_seed(settings, documents.rows), loop_factory=asyncio.SelectorEventLoop)
    except (SeedError, OSError, csv.Error, KeyError, psycopg.Error) as error:
        log.error("register not seeded: %s", " ".join(str(error).split()))
        return 1
    left_out = ", ".join(f"{reason} {count}" for reason, count in sorted(documents.left_out.items()))
    log.info(
        "%d entries added, %d in the register already; left out: %s",
        report.added,
        report.present,
        left_out or "none",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
