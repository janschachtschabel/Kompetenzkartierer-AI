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
so (``unplaced``). A word left without a sign once its control signs are cleaned off is none.

The file is untrusted. Whatever pdfplumber or pdfminer raise while reading it makes it unreadable,
said without its path; so only the library's own calls stand where that is caught. So do pages
pdfplumber counts otherwise than the text layer did (a page tree of one page and three kids): the
limits on pages and on their signs were checked on the text layer's. What is built of what they
read - which signs go, words, tables, lines and blocks - is ours, and its errors stay errors: in
the converting child a crash, not a verdict on the file. A page is read, then built, then the
next is read, so that the signs of one page at a time are held.
"""

import logging
import math
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence, Set
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pdfplumber

from app.conversion.assemble import assemble
from app.conversion.base import Conversion, DropReason
from app.conversion.layout import Box, RawPage, Word, clean_text
from app.conversion.lines import blocks_of
from app.conversion.tables import FoundTable, table_block
from app.conversion.text_layer import UnreadablePdf

log = logging.getLogger(__name__)
MIN_SIZE = 1.0  # points: text set smaller no reader reads


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

    def convert(self, path: Path, *, pages: int) -> Conversion:
        with _reading():
            pdf = pdfplumber.open(path)
        built: list[RawPage] = []
        try:
            with _reading():
                found = pdf.pages
            if len(found) != pages:  # a page tree counting one page, its kids three
                log.warning("pdfplumber read %d pages where the text layer counted %d", len(found), pages)
                raise UnreadablePdf("the file's pages are counted two ways")
            for page in found:
                with _reading():
                    signs, shown = page.chars, (page.cropbox, page.mediabox)
                dropped, counted = dropped_signs(signs, _within_both(*shown))
                with _reading():
                    read = read_page(page, dropped)
                built.append(page_of(read, counted))
        finally:
            with _reading():
                pdf.close()
        return assemble(built, engine=self.name, version=self.version)


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
