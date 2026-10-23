"""Running heads and feet marked, not dropped, and the number printed on each page (plan M1, 3.3).

The edges of a page are its top and bottom 8 %. A text block there is a running head or foot
where its text - numbers aside - stands in the same edge on at least 3 pages and a fifth of the
document's: "Lernfeld 1" … "Lernfeld 3" at the top of 3 pages of 20 are headings, not a running
head. A block there that is a page number alone is one wherever it stands once. Nothing is
dropped: the stages after X0 skip what is marked, and a quote can still find it.

The printed number is read off such a block, the foot's before the head's: "5", "- 5 -",
"Seite 5 von 12", "Rahmenlehrplan - Seite 5", Roman numerals of a preface ("IV", "xii"). The
pattern is the old app's, which skipped these lines; here it keeps the number.
"""

import re
from collections import Counter
from dataclasses import replace
from typing import Literal

from app.conversion.layout import RawBlock, RawPage

EDGE_SHARE = 0.08  # of the page's height, at the top and at the bottom
MIN_REPEATS = 3
MIN_PAGE_SHARE = 0.2
_PAGE_NUMBER = re.compile(
    r"(?:.{0,120}?\b(?:Seite|S\.)\s*)?[-\u2013\u2014]?\s*(?P<number>\d{1,4}|[ivxlc]{1,7})"
    r"(?:\s*(?:von|/)\s*\d{1,4})?\s*[-\u2013\u2014]?",
    re.IGNORECASE,
)
_ROMAN = re.compile(r"(?=[mdclxvi])m{0,4}(c[md]|d?c{0,3})(x[cl]|l?x{0,3})(i[xv]|v?i{0,3})", re.IGNORECASE)
_DIGITS = re.compile(r"[0-9]+")
Edge = Literal["page_header", "page_footer"]


def printed_number(text: str) -> str | None:
    """The page number a line is, or None where it is none: arabic, or a well-formed Roman one."""
    found = _PAGE_NUMBER.fullmatch(" ".join(text.split()))
    if found is None:
        return None
    number = found["number"]
    if not number.isdigit() and _ROMAN.fullmatch(number) is None:
        return None
    return number


def mark_edges(pages: list[RawPage]) -> tuple[str | None, ...]:
    """Mark the running heads and feet of ``pages`` in place; the number printed on each page."""
    repeats: Counter[tuple[Edge, str]] = Counter()
    for page in pages:
        repeats.update({(edge, _key(block)) for block in page.blocks if (edge := _edge(block, page))})
    needed = max(MIN_REPEATS, MIN_PAGE_SHARE * len(pages))
    printed: list[str | None] = []
    for page in pages:
        numbers: dict[Edge, str] = {}
        for index, block in enumerate(page.blocks):
            edge = _edge(block, page)
            if edge is None:
                continue
            number = printed_number(block.text)
            if number is not None:
                numbers.setdefault(edge, number)
            if number is not None or repeats[(edge, _key(block))] >= needed:
                page.blocks[index] = replace(block, kind=edge)
        printed.append(numbers.get("page_footer", numbers.get("page_header")))
    return tuple(printed)


def _edge(block: RawBlock, page: RawPage) -> Edge | None:
    if block.kind != "text":
        return None
    if block.bbox[1] < EDGE_SHARE * page.height:
        return "page_header"
    if block.bbox[3] > (1 - EDGE_SHARE) * page.height:
        return "page_footer"
    return None


def _key(block: RawBlock) -> str:
    return _DIGITS.sub("#", " ".join(block.text.split()).casefold())
