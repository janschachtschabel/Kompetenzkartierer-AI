"""Running heads and feet marked, not dropped, and the number printed on each page (plan M1, 3.3).

The edges of a page are its top and bottom 8 %; a text block is in one where the whole of it is:
a paragraph that begins there and runs on below is text. A block there is a running head or foot
where its text stands in the same edge on at least 3 pages and a fifth of the document's - the
same text, or one whose numbers each stay as they are or run with the page ("Stand 2026 - Seite
5"): "Lernfeld 1" ... "Lernfeld 5" at the top of 5 pages of 10 are headings, not a running head.
A block that is a page number alone is one in the foot wherever it stands; in the head where such
numbers run with the page on two pages at least, its number less the page the same - a chapter's
number alone at the top of a page stays text. Nothing is dropped: the stages after X0 skip what
is marked, and a quote can still find it.

The printed number is read off such a block, the foot's before the head's: "5", "- 5 -",
"Seite 5 von 12", "Rahmenlehrplan - Seite 5", Roman numerals of a preface ("IV", "xii") in one
case; else off a running head or foot whose number runs with the page ("Rahmenlehrplan
Mechatronik 5", "5 | Rahmenlehrplan"). The pattern is the old app's, which skipped these lines;
here it keeps the number.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Literal

from app.conversion.layout import RawBlock, RawPage

EDGE_SHARE = 0.08  # of the page's height, at the top and at the bottom
MIN_REPEATS = 3
MIN_PAGE_SHARE = 0.2
MIN_RUNNING = 2  # pages: a number alone at the top of as many, running with the page, is its number
_PAGE_NUMBER = re.compile(
    r"(?:.{0,120}?\b(?:Seite|S\.)\s*)?[-\u2013\u2014]?\s*(?P<number>\d{1,4}|[ivxlc]{1,7})"
    r"(?:\s*(?:von|/)\s*\d{1,4})?\s*[-\u2013\u2014]?",
    re.IGNORECASE,
)
_ROMAN = re.compile(r"(?=[mdclxvi])m{0,4}(c[md]|d?c{0,3})(x[cl]|l?x{0,3})(i[xv]|v?i{0,3})", re.IGNORECASE)
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_DIGITS = re.compile(r"[0-9]+")
Edge = Literal["page_header", "page_footer"]


@dataclass(frozen=True)
class _AtEdge:
    """A text block in an edge of its page."""

    page: int
    index: int  # among the page's blocks
    edge: Edge
    text: str  # its words, a space apart, in one case
    numbers: tuple[str, ...]  # as its text writes them
    alone: str | None  # the page number it is alone, where it is one

    @property
    def key(self) -> tuple[Edge, str]:
        return self.edge, _DIGITS.sub("#", self.text)


def printed_number(text: str) -> str | None:
    """The page number a line is, or None where it is none: arabic, or a well-formed Roman one
    in one case."""
    found = _PAGE_NUMBER.fullmatch(" ".join(text.split()))
    if found is None:
        return None
    number = found["number"]
    if not number.isdigit() and (
        _ROMAN.fullmatch(number) is None or not (number.isupper() or number.islower())
    ):
        return None
    return number


def mark_edges(pages: list[RawPage]) -> tuple[str | None, ...]:
    """Mark the running heads and feet of ``pages`` in place; the number printed on each page."""
    found = [at for page in pages for at in _at_edges(page)]
    needed = max(MIN_REPEATS, MIN_PAGE_SHARE * len(pages))
    groups: defaultdict[tuple[Edge, str], list[_AtEdge]] = defaultdict(list)
    for at in found:
        groups[at.key].append(at)
    repeated: dict[_AtEdge, int | None] = {}  # the running heads and feet, each with its running number
    for group in groups.values():
        repeated |= _repeated(group, needed)
    head_offsets = Counter(
        _value(at.alone) - at.page for at in found if at.alone and at.edge == "page_header"
    )
    by_number = {page.number: page for page in pages}
    alone: dict[tuple[int, Edge], str] = {}  # the page number alone in each edge of a page
    running: dict[tuple[int, Edge], str] = {}  # the number of a running head or foot that runs
    for at in found:
        is_number = at.alone is not None and (
            at.edge == "page_footer" or head_offsets[_value(at.alone) - at.page] >= MIN_RUNNING
        )
        if is_number and at.alone is not None:
            alone.setdefault((at.page, at.edge), at.alone)
        if (place := repeated.get(at)) is not None:
            running.setdefault((at.page, at.edge), at.numbers[place])
        if is_number or at in repeated:
            page = by_number[at.page]
            page.blocks[at.index] = replace(page.blocks[at.index], kind=at.edge)
    return tuple(_printed(alone, running, page.number) for page in pages)


def _at_edges(page: RawPage) -> list[_AtEdge]:
    """The text blocks in the edges of the page."""
    found: list[_AtEdge] = []
    for index, block in enumerate(page.blocks):
        edge = _edge(block, page)
        if edge is not None:
            text = " ".join(block.text.split()).casefold()
            numbers = tuple(_DIGITS.findall(text))
            found.append(_AtEdge(page.number, index, edge, text, numbers, printed_number(block.text)))
    return found


def _repeated(group: list[_AtEdge], needed: float) -> dict[_AtEdge, int | None]:
    """The blocks of one key that are running heads or feet, and for each the place among its
    numbers of the one that runs with the page, if one does. The key holds where every number
    stays or runs with the page; else each text counts by itself."""
    places = range(len(group[0].numbers))
    stays = [len({at.numbers[place] for at in group}) == 1 for place in places]
    runs = [len({int(at.numbers[place]) - at.page for at in group}) == 1 for place in places]
    if all(stay or run for stay, run in zip(stays, runs, strict=True)):
        if len({at.page for at in group}) < needed:
            return {}
        running = next((place for place in places if runs[place] and not stays[place]), None)
        return dict.fromkeys(group, running)
    by_text: defaultdict[str, set[int]] = defaultdict(set)
    for at in group:
        by_text[at.text].add(at.page)
    return {at: None for at in group if len(by_text[at.text]) >= needed}


def _printed(
    alone: dict[tuple[int, Edge], str], running: dict[tuple[int, Edge], str], page: int
) -> str | None:
    """The page's printed number: the foot's before the head's, a number alone before a running one."""
    for edge in ("page_footer", "page_header"):
        for numbers in (alone, running):
            if (page, edge) in numbers:
                return numbers[(page, edge)]
    return None


def _edge(block: RawBlock, page: RawPage) -> Edge | None:
    if block.kind != "text":
        return None
    if block.bbox[3] <= EDGE_SHARE * page.height:
        return "page_header"
    if block.bbox[1] >= (1 - EDGE_SHARE) * page.height:
        return "page_footer"
    return None


def _value(number: str) -> int:
    """What a page number counts: arabic, or Roman."""
    if number.isdigit():
        return int(number)
    values = [_ROMAN_VALUES[sign] for sign in number.casefold()]
    return sum(
        -value if value < after else value for value, after in zip(values, [*values[1:], 0], strict=True)
    )
