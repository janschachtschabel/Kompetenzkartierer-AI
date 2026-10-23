"""Running heads and feet marked, not dropped, and the number printed on each page (plan M1, 3.3).

The edges of a page are its top and bottom 8 %; a text block is in one where the whole of it is,
or where it begins there, has no more than three lines and ends within 12 % - a running head of
two lines reaching a little past the edge. Such a block is a running head or foot of the same
text only, never one whose number runs, nor a page number alone (headings "Lernfeld 1" ...
"Lernfeld 5" at the top of pages in a row, a footnote ending "Seite 12"). A paragraph that begins
there and runs on below is text.

A block there is a running head or foot where its text stands in the same edge on at least 3
pages and a fifth of the document's - the same text, or one whose numbers each stay as they are,
run with the page, or stay over stretches of pages beside one that runs ("Stand 2026 - Seite 5",
"Lernfeld 2 | 5"). A number runs with the page where each of its offsets from the page is shared
by two pages at least: a count that jumps once - a blank page taken out, two parts counted from
1 - still runs; "Lernfeld 1" ... "Lernfeld 5" at the top of every other page of 10 do not, and
stay headings. A number runs only as the foot's page numbers do, where a page has one: headings
and captions numbered on pages in a row are no running head or foot beside them. A page whose
foot says otherwise - a misprint, a reference taken for a page number - is left out of that
count, not counted against it: a running head goes on where at least half its pages agree.

A block that is a page number alone is one in the foot wherever it stands - a year at the foot of
a cover only where such a number recurs; in the head where such numbers run with the page on two
pages at least and agree with the foot's page number where the page has one: a chapter's number
alone at the top of a page stays text. Nothing is dropped: the stages after X0 skip what is
marked, and a quote can still find it.

The printed number is read off the foot before the head, and in each off a page number alone
before a running head or foot whose number runs with the page: "5", "- 5 -", "Seite 5 von 12",
"Rahmenlehrplan - Seite 5", Roman numerals of a preface ("IV", "xii") in one case; then
"Rahmenlehrplan Mechatronik 5", "5 | Rahmenlehrplan". The pattern is the old app's, which skipped
these lines; here it keeps the number.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Literal

from app.conversion.layout import RawBlock, RawPage

EDGE_SHARE = 0.08  # of the page's height, at the top and at the bottom
NEAR_EDGE_SHARE = 0.12  # how far a running head of a few lines may reach past its edge
NEAR_EDGE_LINES = 3
MIN_REPEATS = 3
MIN_PAGE_SHARE = 0.2
MIN_RUNNING = 2  # pages that share a number's offset from the page: it runs with the pages
MAX_PAGE_DIGITS = 4  # a page number's; a longer number never runs with the page
YEAR_OFFSET = 1000  # a number alone this far above its page is a year, unless it recurs so
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
    alone: str | None  # the page number it is alone, where it is one - not where it reaches past the edge
    near: bool  # in its edge by the band beside it alone

    @property
    def key(self) -> tuple[Edge, tuple[str, ...]]:
        """Its edge and its text between the numbers: blocks of one key differ in numbers alone."""
        return self.edge, tuple(_DIGITS.split(self.text))


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
    groups: defaultdict[tuple[Edge, tuple[str, ...]], list[_AtEdge]] = defaultdict(list)
    for at in found:
        groups[at.key].append(at)
    offsets = {
        edge: Counter(_offset(at) for at in found if at.alone and at.edge == edge)
        for edge in ("page_footer", "page_header")
    }
    feet: dict[int, int] = {}  # each page's number in the foot, as it is printed: its offset from the page
    for at in found:
        if at.edge == "page_footer" and _is_page_number(at, offsets["page_footer"], {}):
            feet.setdefault(at.page, _offset(at))
    repeated: dict[_AtEdge, int | None] = {}  # the running heads and feet, each with its running number
    for group in groups.values():
        repeated |= _repeated(group, needed, feet)
    by_number = {page.number: page for page in pages}
    alone: dict[tuple[int, Edge], str] = {}  # the page number alone in each edge of a page
    running: dict[tuple[int, Edge], str] = {}  # the number of a running head or foot that runs
    for at in found:
        is_number = _is_page_number(at, offsets[at.edge], feet)
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
        found_edge = _edge(block, page)
        if found_edge is not None:
            edge, near = found_edge
            text = " ".join(block.text.split()).casefold()
            numbers = tuple(_DIGITS.findall(text))
            alone = None if near else printed_number(block.text)
            found.append(_AtEdge(page.number, index, edge, text, numbers, alone, near))
    return found


def _is_page_number(at: _AtEdge, offsets: Counter[int], feet: dict[int, int]) -> bool:
    """Whether the block is its page's number: in the foot, a year only where it recurs; in the
    head where it runs with the pages and agrees with the foot's."""
    if at.alone is None:
        return False
    offset = _offset(at)
    if at.edge == "page_footer":
        return offset <= YEAR_OFFSET or offsets[offset] >= MIN_RUNNING
    return offsets[offset] >= MIN_RUNNING and feet.get(at.page, offset) == offset


def _repeated(group: list[_AtEdge], needed: float, feet: dict[int, int]) -> dict[_AtEdge, int | None]:
    """The blocks of one key that are running heads or feet, and for each the place among its
    numbers of the one that runs with the page, if one does. The key holds where every number
    stays, runs with the page, or stays over stretches beside one that runs; else each text
    counts by itself."""
    kinds = [_place(group, place, feet) for place in range(len(group[0].numbers))]
    near = any(at.near for at in group)  # the band beside the edge: a running text, not a count
    if all(kinds) and ("holds" not in kinds or "runs" in kinds) and not (near and "runs" in kinds):
        if len({at.page for at in group}) < needed:
            return {}
        running = next((place for place, kind in enumerate(kinds) if kind == "runs"), None)
        return dict.fromkeys(group, running)
    by_text: defaultdict[str, set[int]] = defaultdict(set)
    for at in group:
        by_text[at.text].add(at.page)
    return {at: None for at in group if len(by_text[at.text]) >= needed}


def _place(group: list[_AtEdge], place: int, feet: dict[int, int]) -> str | None:
    """How the number at ``place`` goes over the group's pages: it ``stays`` the same, ``runs``
    with the page - each offset from the page shared by two pages at least, so a count may jump; a
    page whose number in ``feet`` says otherwise left out, and at least half the pages agreeing -
    or ``holds`` each of its values over two pages at least; None where it does none of these."""
    values = {(at.numbers[place], at.page) for at in group}  # a page counts once
    if len({value for value, _ in values}) == 1:
        return "stays"
    if all(len(value) <= MAX_PAGE_DIGITS for value, _ in values):
        agreeing = [
            int(value) - page
            for value, page in values
            if feet.get(page, int(value) - page) == int(value) - page
        ]
        offsets = Counter(agreeing)
        if 2 * len(agreeing) >= len(values) and offsets and min(offsets.values()) >= MIN_RUNNING:
            return "runs"
    if min(Counter(value for value, _ in values).values()) >= MIN_RUNNING:
        return "holds"
    return None


def _printed(
    alone: dict[tuple[int, Edge], str], running: dict[tuple[int, Edge], str], page: int
) -> str | None:
    """The page's printed number: the foot's before the head's, a number alone before a running one."""
    for edge in ("page_footer", "page_header"):
        for numbers in (alone, running):
            if (page, edge) in numbers:
                return numbers[(page, edge)]
    return None


def _edge(block: RawBlock, page: RawPage) -> tuple[Edge, bool] | None:
    """The edge the block is in, and whether it reaches past it into the band beside it."""
    if block.kind != "text":
        return None
    _x0, top, _x1, bottom = block.bbox
    few_lines = len(block.text.splitlines()) <= NEAR_EDGE_LINES
    edge, near = EDGE_SHARE * page.height, NEAR_EDGE_SHARE * page.height
    if bottom <= edge:
        return "page_header", False
    if top >= page.height - edge:
        return "page_footer", False
    if few_lines and top < edge and bottom <= near:
        return "page_header", True
    if few_lines and bottom > page.height - edge and top >= page.height - near:
        return "page_footer", True
    return None


def _offset(at: _AtEdge) -> int:
    """The page number the block is alone, less its page."""
    assert at.alone is not None  # noqa: S101 - asked of page numbers alone
    return _value(at.alone) - at.page


def _value(number: str) -> int:
    """What a page number counts: arabic, or Roman."""
    if number.isdigit():
        return int(number)
    values = [_ROMAN_VALUES[sign] for sign in number.casefold()]
    return sum(
        -value if value < after else value for value, after in zip(values, [*values[1:], 0], strict=True)
    )
