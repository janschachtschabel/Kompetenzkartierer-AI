"""The engine pdfplumber: a PDF's text layer into named blocks (plan M1, 3.2).

Per page: the tables pdfplumber finds by their ruling lines (app/conversion/tables.py), and the
words outside them - a word whose middle lies in a table is the table's - with their font and
size, grouped into lines and blocks (app/conversion/lines.py). What follows is the engine's no
more (app/conversion/assemble.py). It reads no scan: the converting job asks the text layer first
(app/conversion/text_layer.py).

A word left without a sign once its control signs are cleaned off is none. A word no reader reads
where it stands is dropped and counted on its page, by why: set upwards or turned (``vertical``:
pdfplumber splinters it - "dna", "6202" - into words of its own), its middle outside the page
(``off_page``), or smaller than a point (``tiny``) - a way to hide text from a reader, not from a
model, so it is said as a finding rather than lost unseen.

The file is untrusted. Whatever pdfplumber or pdfminer raise while reading it makes it unreadable,
said without its path; so only the library's own calls stand where that is caught. What is built
of what they read - words, tables, lines and blocks - is ours, and its errors stay errors: in the
converting child a crash, not a verdict on the file. A page is read, then built, then the next is
read, so that the signs of one page at a time are held.
"""

import logging
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
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
    """What pdfplumber read off a page, as it handed it over."""

    number: int
    height: float
    bbox: Box
    words: Sequence[Mapping[str, Any]]
    tables: Sequence[FoundTable]
    chars: Sequence[Mapping[str, Any]]  # where the page has a table: its header's signs


class PdfplumberEngine:
    name = "pdfplumber"
    version = version("pdfplumber")

    def convert(self, path: Path) -> Conversion:
        with _reading():
            pdf = pdfplumber.open(path)
        pages: list[RawPage] = []
        try:
            with _reading():
                found = pdf.pages
            for page in found:
                with _reading():
                    read = read_page(page)
                pages.append(page_of(read))
        finally:
            with _reading():
                pdf.close()
        return assemble(pages, engine=self.name, version=self.version)


@contextmanager
def _reading() -> Iterator[None]:
    """Around the library's calls on the file: what they raise makes it unreadable."""
    try:
        yield
    except Exception as error:  # an untrusted file: whatever the library raises on it
        log.warning("pdfplumber could not read a file: %s", type(error).__name__)
        raise UnreadablePdf("pdfplumber could not read the file as a PDF") from None


def read_page(page: Any) -> PageRead:
    """What pdfplumber reads off a page: the library's calls alone."""
    tables = [
        FoundTable(texts=table.extract(), boxes=[row.cells for row in table.rows], bbox=table.bbox)
        for table in page.find_tables()
    ]
    read = PageRead(
        number=page.page_number,
        height=page.height,
        bbox=page.bbox,
        words=page.extract_words(extra_attrs=["fontname", "size"]),
        tables=tables,
        chars=page.chars if tables else [],
    )
    page.flush_cache()  # pdfplumber keeps a page's objects otherwise, page by page
    return read


def page_of(read: PageRead) -> RawPage:
    """The page's blocks: its tables, and its words outside them in lines and blocks."""
    number = int(read.number)
    tables = [found for found in (table_block(table, read.chars, number) for table in read.tables) if found]
    boxes = [table.bbox for table in tables]
    words: list[Word] = []
    dropped: Counter[DropReason] = Counter()
    for found in read.words:
        word = _word(found)
        if not word.text or _within(word, boxes):
            continue
        reason = _dropped(word, found, read.bbox)
        if reason is None:
            words.append(word)
        else:
            dropped[reason] += 1
    return RawPage(number, float(read.height), [*blocks_of(words, number), *tables], dropped)


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


def _dropped(word: Word, found: Mapping[str, Any], page: Box) -> DropReason | None:
    """Why no reader reads ``word`` where it stands on the page, or None where one does."""
    if not found["upright"]:
        return "vertical"
    if not _within(word, [page]):
        return "off_page"
    if word.size < MIN_SIZE:
        return "tiny"
    return None


def _within(word: Word, boxes: list[Box]) -> bool:
    middle_x, middle_y = (word.x0 + word.x1) / 2, (word.top + word.bottom) / 2
    return any(x0 <= middle_x <= x1 and top <= middle_y <= bottom for x0, top, x1, bottom in boxes)
