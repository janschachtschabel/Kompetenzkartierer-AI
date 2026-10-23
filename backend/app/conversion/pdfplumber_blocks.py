"""The engine pdfplumber: a PDF's text layer into named blocks (plan M1, 3.2).

Per page: the tables pdfplumber finds by their ruling lines (app/conversion/tables.py), and the
words outside them - a word whose middle lies in a table is the table's - with their font and
size, grouped into lines and blocks (app/conversion/lines.py). What follows is the engine's no
more (app/conversion/assemble.py). It reads no scan: the converting job asks the text layer first
(app/conversion/text_layer.py).

A sign no reader reads where it stands is dropped before words and tables are read - in a cell
of a table too - and counted on its page, by why: set upwards or turned (``vertical``: pdfplumber
would splinter its words - "dna", "6202"), its middle outside what a viewer shows - the crop box,
within the media box (``off_page``) - or smaller than a point (``tiny``): a way to hide text from
a reader, not from a model, so it is said as a finding rather than lost unseen. A sign or a table
at no finite point - a number of 400 digits in the content stream places it at NaN - is dropped
so (``unplaced``). A sign printed again over itself, to look bold, is read once. A word left
without a sign once its control signs are cleaned off is none.

The file is untrusted. Whatever pdfplumber or pdfminer raise while reading it makes it unreadable,
said without its path; so only the library's own calls stand where that is caught. So do pages
pdfplumber counts otherwise than the text layer did (a page tree of one page and three kids): the
limit on pages was checked on the text layer's. They are counted as far as one more before
pdfplumber builds them, which it does for every page the tree holds - and closing the file builds
them too where none were. A page of more signs than the service takes is
too dense (TooDense) - counted here, before its words and tables are read, since pdfium counts a
text drawn many times at one place once and pdfminer reads each. What is built of what they read
- which signs go, words, tables, lines and blocks - is ours, and its errors stay errors: in the
converting child a crash, not a verdict on the file. A page is read, then built, then the next is
read, so that the signs of one page at a time are held.
"""

import logging
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence, Set
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from itertools import islice
from pathlib import Path
from typing import Any

import pdfplumber
from pdfminer.pdfpage import PDFPage

from app.conversion.assemble import assemble
from app.conversion.base import Conversion, DropReason
from app.conversion.convert import MAX_PAGE_SIGNS
from app.conversion.layout import Box, RawPage, Word, clean_text
from app.conversion.lines import blocks_of
from app.conversion.tables import FoundTable, table_block
from app.conversion.text_layer import TooDense, UnreadablePdf

log = logging.getLogger(__name__)
MIN_SIZE = 1.0  # points: text set smaller no reader reads
TWIN = 0.1  # times the size: a sign set again this close to itself is printed over


@dataclass(frozen=True)
class PageRead:
    """What pdfplumber read off a page, as it handed it over, the dropped signs aside."""

    number: int
    height: float
    words: Sequence[Mapping[str, Any]]
    tables: Sequence[FoundTable]
    chars: Sequence[Mapping[str, Any]]  # where the page has a table: its header's signs


class PdfplumberEngine:
    name = "pdfplumber"
    version = version("pdfplumber")

    def convert(self, path: Path, *, pages: int, max_signs: int = MAX_PAGE_SIGNS) -> Conversion:
        with _reading():
            pdf = pdfplumber.open(path)
        built: list[RawPage] = []
        found: list[Any] | None = None
        try:
            with _reading():  # as far as one page more: pdf.pages builds every page the tree holds
                held = sum(1 for _ in islice(PDFPage.create_pages(pdf.doc), pages + 1))
            if held != pages:  # a page tree counting one page, its kids three
                log.warning(
                    "pdfminer found %s pages where the text layer counted %d", _upto(held, pages), pages
                )
                raise UnreadablePdf("the file's pages are counted two ways")
            with _reading():
                found = pdf.pages
            for page in found:
                with _reading():
                    number, signs, shown = page.page_number, page.chars, (page.cropbox, page.mediabox)
                if len(signs) > max_signs:
                    raise TooDense(number, len(signs), max_signs)
                twins = twin_signs(signs)
                dropped, counted = dropped_signs(
                    (sign for sign in signs if id(sign) not in twins), _within_both(*shown)
                )
                with _reading():
                    read = read_page(page, dropped | twins)
                built.append(page_of(read, counted))
        finally:
            with _reading():
                if found is None:  # pdf.close() builds every page to close it
                    pdf.stream.close()
                else:
                    pdf.close()
        return assemble(built, engine=self.name, version=self.version)


def _upto(held: int, pages: int) -> str:
    """The pages a tree holds, counted as far as one more than expected: "more than 1" beyond."""
    return str(held) if held <= pages else f"more than {pages}"


@contextmanager
def _reading() -> Iterator[None]:
    """Around the library's calls on the file: what they raise makes it unreadable."""
    try:
        yield
    except Exception as error:  # an untrusted file: whatever the library raises on it
        log.warning("pdfplumber could not read a file: %s", type(error).__name__)
        raise UnreadablePdf("pdfplumber could not read the file as a PDF") from None


def read_page(page: Any, dropped: Set[int] = frozenset()) -> PageRead:
    """What pdfplumber reads off a page, the signs ``dropped`` (by identity) aside: the library's
    calls alone."""
    shown = page.filter(lambda found: id(found) not in dropped)
    tables = [
        FoundTable(texts=table.extract(), boxes=[row.cells for row in table.rows], bbox=table.bbox)
        for table in shown.find_tables()
    ]
    read = PageRead(
        number=page.page_number,
        height=page.height,
        words=shown.extract_words(extra_attrs=["fontname", "size"]),
        tables=tables,
        chars=shown.chars if tables else [],
    )
    page.flush_cache()  # pdfplumber keeps a page's objects otherwise, page by page
    return read


def twin_signs(signs: Iterable[Mapping[str, Any]]) -> set[int]:
    """The signs, by identity, printed again over one before them - its text in its font and size,
    within a tenth of the size - to look bold, or to weigh a page down: pdfium reads them once,
    pdfminer each time ("DDiiee"). A grid of a tenth of the size finds the one before in the cells
    around, so that a page of many signs costs no more than few - pdfplumber's dedupe_chars sorts
    by index, 17 s for 30,000 signs."""
    kept: defaultdict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    twins: set[int] = set()
    for sign in signs:
        size = sign["size"]
        if not _finite((sign["x0"], sign["top"], size)) or size <= 0:
            continue  # no place to be printed again at: dropped as it is
        near = TWIN * size
        kind = (sign["text"], sign["fontname"], size, sign["upright"])
        column, row = math.floor(sign["x0"] / near), math.floor(sign["top"] / near)
        cells = [(*kind, column + across, row + down) for across in (-1, 0, 1) for down in (-1, 0, 1)]
        if any(
            abs(other["x0"] - sign["x0"]) <= near and abs(other["top"] - sign["top"]) <= near
            for cell in cells
            for other in kept.get(cell, ())
        ):
            twins.add(id(sign))
        else:
            kept[(*kind, column, row)].append(sign)
    return twins


def dropped_signs(signs: Iterable[Mapping[str, Any]], shown: Box) -> tuple[set[int], Counter[DropReason]]:
    """The signs no reader reads, by identity, and how many there are by why, spaces aside."""
    dropped: set[int] = set()
    counted: Counter[DropReason] = Counter()
    for sign in signs:
        reason = why_dropped(sign, shown)
        if reason is not None:
            dropped.add(id(sign))
            counted[reason] += _signs(sign["text"])
    return dropped, +counted


def why_dropped(sign: Mapping[str, Any], shown: Box) -> DropReason | None:
    """Why no reader reads ``sign`` where it stands, or None where one does."""
    if not _finite((sign["x0"], sign["top"], sign["x1"], sign["bottom"], sign["size"])):
        return "unplaced"  # first: NaN lies anywhere and is no size
    if not sign["upright"]:
        return "vertical"
    if not _middle_within((sign["x0"], sign["top"], sign["x1"], sign["bottom"]), [shown]):
        return "off_page"
    if sign["size"] < MIN_SIZE:
        return "tiny"
    return None


def page_of(read: PageRead, dropped: Mapping[DropReason, int] | None = None) -> RawPage:
    """The page's blocks: its tables, and its words outside them in lines and blocks; with the
    signs dropped from it, by why."""
    number = int(read.number)
    counted: Counter[DropReason] = Counter(dropped or {})
    tables = []
    for table in read.tables:
        if not _finite(table.bbox):
            counted["unplaced"] += sum(_signs(text or "") for row in table.texts for text in row)
        elif (block := table_block(table, read.chars, number)) is not None:
            tables.append(block)
    boxes = [table.bbox for table in tables]
    words = [
        word
        for word in map(_word, read.words)
        if word.text and not _middle_within((word.x0, word.top, word.x1, word.bottom), boxes)
    ]
    return RawPage(number, float(read.height), [*blocks_of(words, number), *tables], +counted)


def _signs(text: str) -> int:
    """The signs of a text, spaces and control signs aside: what a dropping counts."""
    return sum(not sign.isspace() for sign in clean_text(text))


def _word(found: Mapping[str, Any]) -> Word:
    return Word(
        text=clean_text(found["text"]),
        x0=float(found["x0"]),
        x1=float(found["x1"]),
        top=float(found["top"]),
        bottom=float(found["bottom"]),
        size=float(found["size"]),
        font=str(found["fontname"]),
    )


def _within_both(crop: Box, media: Box) -> Box:
    """What a viewer shows of a page: its crop box, as far as it lies within its media box."""
    return max(crop[0], media[0]), max(crop[1], media[1]), min(crop[2], media[2]), min(crop[3], media[3])


def _finite(numbers: Iterable[float]) -> bool:
    return all(map(math.isfinite, numbers))


def _middle_within(place: Box, boxes: list[Box]) -> bool:
    middle_x, middle_y = (place[0] + place[2]) / 2, (place[1] + place[3]) / 2
    return any(x0 <= middle_x <= x1 and top <= middle_y <= bottom for x0, top, x1, bottom in boxes)
