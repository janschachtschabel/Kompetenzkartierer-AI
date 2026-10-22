"""The comparison dataset's notes on blocked portals and detours, as access notes (plan M1, 2.3).

Each note belongs to a land, school form and subject; an entry seeded with the same three shows
it (app/db/source_queries.seed_of), and a note that names no school form or no subject holds for
all of them in its land. A note no entry matches is kept all the same: it shows once one does.
Taken as published (CC0), its categories split; an empty note is left out, an address that is
none ("lokal") is no address.
"""

import csv
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from app.core.ids import new_id
from app.sources.register import COMPARISON_DATASET as DATASET
from app.sources.register import SEED_DIR, land_country
from app.sources.url_fetch import UrlNotAllowed, check_url

NOTES = SEED_DIR / "umgehungshinweise_de.csv"
# One import at a time: two at once would each find the notes absent and each report them added,
# though ON CONFLICT lets only one of them write them
_NOTES_LOCK = int.from_bytes(b"kka-note", "big")


@dataclass(frozen=True)
class AccessNote:
    key: str  # the SHA-256 of the row as published
    country: str | None
    school_form: str | None
    subject: str | None
    categories: list[str]
    dataset_field: str | None  # where the dataset kept the note: its bookkeeping, not shown
    text: str
    url: str | None
    dataset_origin: str | None  # whence the dataset took it; no origin in the Kern's sense


@dataclass(frozen=True)
class Notes:
    notes: list[AccessNote]
    left_out: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True)
class NotesReport:
    added: int
    present: int


def read_notes(path: Path) -> Notes:
    notes: list[AccessNote] = []
    left_out: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle, delimiter=";"):
            text = _text(raw["Hinweis"], 4000)
            if text is None:
                left_out["empty"] += 1
                continue
            notes.append(
                AccessNote(
                    key=hashlib.sha256("\x1f".join(raw.values()).encode()).hexdigest(),
                    country=land_country(raw["Land_Kuerzel"]),
                    school_form=_text(raw["Schulform"], 200),
                    subject=_text(raw["Fach"], 200),
                    categories=[
                        part for part in (_text(item, 200) for item in raw["Kategorien"].split(";")) if part
                    ],
                    dataset_field=_text(raw["Feld"], 200),
                    text=text,
                    url=_address(raw["URL_im_Text"]),
                    dataset_origin=_text(raw["Herkunft"], 200),
                )
            )
    return Notes(notes, left_out)


def _text(value: str, limit: int) -> str | None:
    value = " ".join(value.split())
    return value[:limit] or None


def _address(value: str) -> str | None:
    try:
        return check_url(value.strip()) if value.strip().startswith("http") else None
    except UrlNotAllowed:
        return None


async def record_notes(connection: psycopg.AsyncConnection, notes: list[AccessNote]) -> NotesReport:
    """Add the notes the register lacks, in one transaction."""
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(%s)", (_NOTES_LOCK,))
        cursor = await connection.execute("SELECT note_key FROM access_note WHERE dataset = %s", (DATASET,))
        present = {key for (key,) in await cursor.fetchall()}
        new = [note for note in notes if note.key not in present]
        async with connection.cursor() as writer:
            await writer.executemany(
                "INSERT INTO access_note (id, dataset, note_key, country, school_form, subject, categories,"
                " dataset_field, text, url, dataset_origin) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                " %s) ON CONFLICT (dataset, note_key) DO NOTHING",
                [
                    (
                        new_id(),
                        DATASET,
                        note.key,
                        note.country,
                        note.school_form,
                        note.subject,
                        note.categories,
                        note.dataset_field,
                        note.text,
                        note.url,
                        note.dataset_origin,
                    )
                    for note in new
                ],
            )
    return NotesReport(added=len(new), present=len(notes) - len(new))
