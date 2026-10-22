"""``python -m app.sources.research_t1 [DIRECTORY]``: the lands' own research, table T1, into the register.

The Kern's research assignments (ontology/recherche-auftraege) listed each land's documents in a
table T1 (plan M1, 2.4; Gesamtplan §7.5): Schule, Elementar and Beruf one report per land,
Hochschule and Erwachsenenbildung one for all lands. Each row becomes a candidate of no account,
unchecked, beside the comparison dataset's: the title the research read off the document, word
for word; the first address of its url field (which also holds notes for its readers and further
addresses); who publishes the copy there, as its host or the field's note on it says (an archive,
a mirror, a secondary source: §7.5 has mirrors marked); its land; the sector of its assignment;
its evidence, E from the primary document or S from a secondary source (A, an assumption, is
none). A row whose fields a semicolon moved, or
without a title or an address, is left out and counted, and so is each address an entry's url
field names beyond the first ("further_address"). A second run adds nothing: a row's key
is its report, land, title and address.

The comparison then counts the addresses of the register only the comparison dataset holds,
only the research, or both.

Exit code 0 when the register holds the research afterwards (seeded now or before), 1 when a
report or the database refused. Logs go to stderr.
"""

import asyncio
import csv
import hashlib
import io
import logging
import re
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

from app.core.logging import configure_logging
from app.core.settings import Settings
from app.db.pool import CONNECTION_OPTIONS
from app.sources.register import COMPARISON_DATASET, Evidence, SeedDataset, SourceType
from app.sources.seed import Documents, SeedError, SeedReport, SeedRow, reasons, seed_register
from app.sources.url_fetch import UrlNotAllowed, check_url

log = logging.getLogger("app.sources.research_t1")  # also when run as __main__

DATASET: SeedDataset = "laenderrecherche"
RESEARCH = "recherche-ergebnisse"  # its folder in ontology/


@dataclass(frozen=True)
class Assignment:
    reports: str  # its reports in the folder, as a glob
    title: str  # the column of T1 holding the document's title word for word
    sector: str  # its notation in cv:EducationSectors


# The overview of Beruf (03A), the module handbooks (04B), the frameworks of adult education (05B)
# and the cross-sectional assignments (06, 07) list no curricula of a land
ASSIGNMENTS = {
    "schule": Assignment("01-schule-DE-*.md", "dokumenttitel_woertlich", "school"),
    "elementar": Assignment("02-elementar-DE-*.md", "dokumenttitel_woertlich", "elementary"),
    "beruf": Assignment("03B-beruf-DE-*.md", "dokumenttitel_woertlich", "vocational"),
    "hochschule": Assignment("04A-hochschule-laender.md", "norm_titel_woertlich", "higher"),
    "eb": Assignment("05A-eb-laender.md", "titel_woertlich", "adult"),
}
_TITLE_LIMIT = 500  # what source.title holds
_T1_HEADING = re.compile(r"#.*\bT1\b")
# An address ends where the field's next one ("https://a | https://b") or a note begins
_ADDRESS = re.compile(r"https?://[^\s|]+", re.IGNORECASE)
_LAND = re.compile(r"DE(-[A-Z]{2})?")  # DE: the federation's own row of Erwachsenenbildung
_EVIDENCE = re.compile(r"([ES])\b")  # "E", "S (Portalseite)", "E (Titel) | S (Portal)"
# Hosts that keep what others published: the Wayback Machine, the GEI's depot of curricula
_ARCHIVES = frozenset({"web.archive.org", "edumedia-depot.gei.de"})
# What a note says of the copy at its address, as the research words it, in this order
_COPY_NOTES: tuple[tuple[re.Pattern[str], SourceType], ...] = (
    (re.compile(r"archivkopie", re.IGNORECASE), "archiv"),
    (re.compile(r"\bspiegel|kopie\b", re.IGNORECASE), "spiegel"),  # Spiegelkopie, Schulkopie
    (re.compile(r"sekund(ä|ae)rquelle", re.IGNORECASE), "sekundaer"),
)


@dataclass(frozen=True)
class Comparison:
    only_seed: int  # addresses only the comparison dataset holds
    only_research: int
    both: int


def read_research(directory: Path) -> Documents:
    """The candidates of the research's T1 tables, and how many rows were left out, by why;
    SeedError when an assignment has no report in the folder or a report no table T1."""
    rows: list[SeedRow] = []
    left_out: Counter[str] = Counter()
    keys: set[str] = set()
    for name, assignment in ASSIGNMENTS.items():
        reports = sorted(directory.glob(assignment.reports))
        if not reports:
            raise SeedError(f"no reports of the assignment {name} in {directory}: is ONTOLOGY_DIR right?")
        for path in reports:
            for row, further in _rows(path, assignment, left_out):
                if row.key in keys:
                    left_out["duplicate"] += 1
                else:
                    keys.add(row.key)
                    rows.append(row)
                    if further:
                        left_out["further_address"] += further
    return Documents(rows, left_out)


def _rows(path: Path, assignment: Assignment, left_out: Counter[str]) -> Iterator[tuple[SeedRow, int]]:
    """The candidates of a report's table T1, each with how many addresses its url field names
    beyond the first."""
    reader = csv.DictReader(io.StringIO("\n".join(_t1(path))), delimiter=";")
    missing = [
        column
        for column in ("land", assignment.title, "url", "beleg")
        if column not in (reader.fieldnames or [])
    ]
    if missing:
        raise SeedError(f"{path.name}: its table T1 lacks the columns {', '.join(missing)}")
    for raw in reader:
        # more fields than the header: a semicolon in a field moved those after it
        if None in raw or None in raw.values():
            left_out["shifted"] += 1
            continue
        title = " ".join(raw[assignment.title].split())[:_TITLE_LIMIT]
        address = _address(raw["url"])
        if not title:
            left_out["no_title"] += 1
            continue
        if address is None:
            left_out["no_url"] += 1
            continue
        try:
            url = check_url(address)
        except UrlNotAllowed:
            left_out["url_invalid"] += 1
            continue
        land = raw["land"].strip()
        found = SeedRow(
            key=hashlib.sha256("\x1f".join((path.name, land, title, url)).encode()).hexdigest(),
            title=title,
            url=url,
            country=land if _LAND.fullmatch(land) else None,
            source_type=_source_type(raw["url"], url),
            sector=assignment.sector,
            evidence=_evidence(raw["beleg"]),
        )
        yield found, len(_ADDRESS.findall(raw["url"])) - 1


def _t1(path: Path) -> list[str]:
    """The lines of table T1: the first csv block under a heading naming T1, else the report's first."""
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = next((index for index, line in enumerate(lines) if _T1_HEADING.match(line)), 0)
    start = next(
        (index for index in range(heading, len(lines)) if lines[index].strip().startswith("```csv")), None
    )
    if start is None:
        raise SeedError(f"{path.name} holds no table T1")
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].strip().startswith("```")), None
    )
    return lines[start + 1 : end]


def _address(field: str) -> str | None:
    found = _ADDRESS.search(field)
    if found is None:
        return None
    address = found.group(0).rstrip(".,:")
    # "(https://…/lp.pdf)": the bracket closes the note, unless the address opened one
    while address.endswith(")") and address.count(")") > address.count("("):
        address = address[:-1].rstrip(".,:")
    return address


def _source_type(field: str, url: str) -> SourceType | None:
    """Who publishes the copy at the field's first address: an archive by its host, else as the
    research noted it there. The note runs from the address to the field's next "|"; one that
    names a further address speaks of that one ("(gelesen als Kopie https://…)"), not of the
    first, and counts for nothing."""
    if urlsplit(url).hostname in _ARCHIVES:
        return "archiv"
    found = _ADDRESS.search(field)
    note = field[found.end() :].split("|", 1)[0] if found else ""
    if _ADDRESS.search(note):
        return None
    return next((kind for pattern, kind in _COPY_NOTES if pattern.search(note)), None)


def _evidence(field: str) -> Evidence | None:
    found = _EVIDENCE.match(field.strip())
    if found is None:
        return None
    return "E" if found.group(1) == "E" else "S"


async def compare_addresses(connection: psycopg.AsyncConnection) -> Comparison:
    """The register's addresses by which of the two seeds holds them."""
    cursor = await connection.execute(
        "SELECT DISTINCT provenance, url FROM source WHERE provenance IN (%s, %s) AND url IS NOT NULL",
        (COMPARISON_DATASET, DATASET),
    )
    held: dict[str, set[str]] = {COMPARISON_DATASET: set(), DATASET: set()}
    for provenance, url in await cursor.fetchall():
        held[provenance].add(url)
    seed, research = held[COMPARISON_DATASET], held[DATASET]
    return Comparison(
        only_seed=len(seed - research), only_research=len(research - seed), both=len(seed & research)
    )


async def _seed(settings: Settings, research: Documents) -> tuple[SeedReport, Comparison]:
    url = settings.database_url.get_secret_value()
    async with await psycopg.AsyncConnection.connect(url, **CONNECTION_OPTIONS) as connection:
        return await seed_register(connection, research.rows, DATASET), await compare_addresses(connection)


def main(arguments: list[str]) -> int:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    directory = Path(arguments[0]) if arguments else settings.ontology_dir / RESEARCH
    try:
        research = read_research(directory)
        seeded, comparison = asyncio.run(_seed(settings, research), loop_factory=asyncio.SelectorEventLoop)
    except (SeedError, OSError, UnicodeDecodeError, csv.Error, psycopg.Error) as error:
        log.error("register not seeded: %s", " ".join(str(error).split()))
        return 1
    log.info(
        "%d entries added, %d in the register already; left out: %s",
        seeded.added,
        seeded.present,
        reasons(research.left_out),
    )
    log.info(
        "addresses only in the comparison dataset %d, only in the research %d, in both %d",
        comparison.only_seed,
        comparison.only_research,
        comparison.both,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
