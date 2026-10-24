"""A document's table of contents (plan M1 6.3), read from its blocks without the model.

An entry is a line that ends in a page - behind a leader ("2.1 Ziele ..... 5", "Vorwort . . . iii"),
or behind a numbered title without one ("2.1 Ziele 5"), or as a contents' pattern of the lexicon
has it (a cue that maps to the contents, ``cv:occ_toc``; one that only occurs in them is the word
of a heading the contents name too, no entry's form). Blocks most of whose lines are entries,
one after another (pages may part them), are the contents where they hold three entries at least,
with a title right before them ("Inhalt", "Inhaltsverzeichnis"), and where their pages run as a
contents' do: never back, within the document's pages, not all one - lines of numbers elsewhere
(a learning fields' overview with its hours, notes with their years) are none. An entry's level
is the depth of its numbering; an entry without one has none, since a block's lines share their
indentation. The contents are never a section of the document (the old app's lesson: they became
a root with the headings again as children), and a heading they name is one whatever its type
(app/pipeline/skeleton.py). The first run of entries with a title, or within the first
FRONT_PAGES pages, says where the title pages end, whether its pages are read or not: with a
title, there; without one, there only where they are read, else nowhere. No run later on (a
list of figures, an annex's contents) ends them.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from app.conversion.base import Block
from app.domain.lexicon import Cue
from app.pipeline.patterns import PatternSearch

LEAST_ENTRIES = 3
FRONT_PAGES = 5  # contents within them, untitled, are the title pages' own
OUTSIDE = frozenset({"page_header", "page_footer"})  # the kinds of block no part of the text is

# A numbering that leads a title: "1", "1.2", "1.2." - two digits a part, so a year leads none -
# or a letter or Roman numeral with its full stop ("A.", "IV.")
_NUMBER = re.compile(r"(\d{1,2}(?:\.\d{1,2})*)\.?(?=\s)|([A-Z]|[IVX]+)\.(?=\s)")
_LEADER = re.compile(r"(?P<title>\S.*?)\s*(?:[.…·_]\s*){2,}(?P<page>\d{1,4}|[ivxlc]{1,7})")
_NUMBERED = re.compile(r"(?P<title>\d{1,2}(?:\.\d{1,2})*\.?\s+\S.*?)\s+(?P<page>\d{1,4})")
_PAGE = re.compile(r"\d{1,4}|[ivxlc]{1,7}")
_TITLE = re.compile(r"(?i:inhalt|inhaltsverzeichnis|inhaltsübersicht|gliederung)")


@dataclass(frozen=True)
class TocEntry:
    title: str  # as printed, its numbering with it
    page: str  # the printed page the contents give
    level: int | None  # the depth of its numbering
    position: int  # of the block it stands in, among the conversion's blocks


@dataclass(frozen=True)
class Contents:
    entries: tuple[TocEntry, ...]
    positions: frozenset[int]  # the blocks the contents fill, their title with them
    front_end: int | None = None  # where the title pages end: the first block of the contents that end them


def leading_number(text: str) -> str | None:
    """The numbering a title begins with ("1.2" of "1.2 Ziele", "IV" of "IV. Anhang"), or None."""
    found = _NUMBER.match(text)
    return None if found is None else found[1] or found[2]


def number_depth(number: str) -> int:
    """How deep a numbering lies: "2" at 1, "2.1" at 2; a letter or a Roman numeral at 1."""
    return number.count(".") + 1


def title_key(title: str) -> str:
    """A title as a heading and its entry are compared: without its numbering, its letters and
    digits alone, in one case."""
    number = _NUMBER.match(title)
    rest = title[number.end() :] if number is not None else title
    return "".join(sign for sign in unicodedata.normalize("NFC", rest).casefold() if sign.isalnum())


def find_contents(blocks: Sequence[Block], cues: Sequence[Cue], search: PatternSearch) -> Contents:
    """The contents among the blocks (all of a conversion's, in order); ``cues`` are the lexicon's
    for contents lines."""
    order = [position for position, block in enumerate(blocks) if block.kind not in OUTSIDE]
    runs: list[list[tuple[int, list[TocEntry]]]] = [[]]
    for position in order:
        if found := _entries(blocks[position], position, cues, search):
            runs[-1].append((position, found))
        elif runs[-1]:
            runs.append([])
    pages = max((block.page for block in blocks), default=0)
    entries: list[TocEntry] = []
    positions: set[int] = set()
    front_end: int | None = None
    decided = False
    for run in runs:
        listed = [entry for _, found in run for entry in found]
        if len(listed) < LEAST_ENTRIES:
            continue
        first = run[0][0]
        before = order.index(first) - 1
        titled = before >= 0 and _TITLE.fullmatch(blocks[order[before]].text.strip()) is not None
        paged = _paged(listed, pages)
        if not decided and (titled or blocks[first].page <= FRONT_PAGES):
            # the contents up front, read or not: a later run (an annex's) ends no title pages
            decided = True
            front_end = first if titled or paged else None  # the title before it is theirs too
        if not paged:
            continue
        if titled:
            positions.add(order[before])
        positions.update(position for position, _ in run)
        entries.extend(listed)
    return Contents(tuple(entries), frozenset(positions), front_end)


def _paged(entries: Sequence[TocEntry], pages: int) -> bool:
    """Whether the entries' pages run as a contents' do: never back, within the document, not all
    one page; Roman numerals alone are the front matter's own."""
    numbers = [int(entry.page) for entry in entries if entry.page.isdigit()]
    if not numbers:
        return True
    rising = all(earlier <= later for earlier, later in pairwise(numbers))
    return rising and max(numbers) <= pages and len(set(numbers)) > 1


def _entries(block: Block, position: int, cues: Sequence[Cue], search: PatternSearch) -> list[TocEntry]:
    """The entries of a block most of whose lines are entries; none of any other."""
    if block.kind != "text":
        return []
    # each run of white space as one: the entry's forms are then read in linear time
    lines = [joined for line in block.text.splitlines() if (joined := " ".join(line.split()))]
    entries = [entry for line in lines if (entry := _entry(line, position, cues, search)) is not None]
    return entries if entries and 2 * len(entries) >= len(lines) else []


def _entry(line: str, position: int, cues: Sequence[Cue], search: PatternSearch) -> TocEntry | None:
    found = _LEADER.fullmatch(line) or _NUMBERED.fullmatch(line)
    if found is not None:
        title, page = found["title"], found["page"]
    elif any(search.found(cue, line) for cue in cues) and len(parts := line.rsplit(maxsplit=1)) == 2:
        title, page = parts
        if _PAGE.fullmatch(page) is None:
            return None
    else:
        return None
    number = leading_number(title)
    return TocEntry(title, page, None if number is None else number_depth(number), position)
