"""The engine pdfplumber: a PDF's text layer into named blocks (plan M1, 3.2).

Per page: the tables pdfplumber finds by their ruling lines (app/conversion/tables.py), and the
words outside them - a word whose middle lies in a table is the table's - with their font and
size, grouped into lines and blocks (app/conversion/lines.py). What follows is the engine's no
more (app/conversion/assemble.py). It reads no scan: the converting job asks the text layer first
(app/conversion/text_layer.py).

The file is untrusted. Whatever pdfplumber or pdfminer raise while reading it makes it unreadable,
said without its path; the grouping after the reading is ours, and its errors stay errors.
"""

import logging
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pdfplumber

from app.conversion.assemble import assemble
from app.conversion.base import Conversion
from app.conversion.layout import Box, RawBlock, RawPage, Word
from app.conversion.lines import blocks_of
from app.conversion.tables import table_block
from app.conversion.text_layer import UnreadablePdf

log = logging.getLogger(__name__)


class PdfplumberEngine:
    name = "pdfplumber"
    version = version("pdfplumber")

    def convert(self, path: Path) -> Conversion:
        try:
            with pdfplumber.open(path) as pdf:
                read = [_read(page) for page in pdf.pages]
        except Exception as error:  # an untrusted file: whatever the library raises on it
            log.info("pdfplumber could not read a file: %s", type(error).__name__)
            raise UnreadablePdf("pdfplumber could not read the file as a PDF") from None
        pages = [
            RawPage(number, height, [*blocks_of(words, number), *tables])
            for number, height, words, tables in read
        ]
        return assemble(pages, engine=self.name, version=self.version)


def _read(page: Any) -> tuple[int, float, list[Word], list[RawBlock]]:
    """What pdfplumber reads off a page: its number, height, the words outside its tables, the tables."""
    tables = [found for found in (table_block(table, page) for table in page.find_tables()) if found]
    words = [
        Word(
            text=word["text"],
            x0=float(word["x0"]),
            x1=float(word["x1"]),
            top=float(word["top"]),
            bottom=float(word["bottom"]),
            size=float(word["size"]),
            font=str(word["fontname"]),
        )
        for word in page.extract_words(extra_attrs=["fontname", "size"])
        if not _within(word, [table.bbox for table in tables])
    ]
    number, height = int(page.page_number), float(page.height)
    page.flush_cache()  # pdfplumber keeps a page's objects otherwise, page by page
    return number, height, words, tables


def _within(word: dict[str, Any], boxes: list[Box]) -> bool:
    middle_x, middle_y = (word["x0"] + word["x1"]) / 2, (word["top"] + word["bottom"]) / 2
    return any(x0 <= middle_x <= x1 and top <= middle_y <= bottom for x0, top, x1, bottom in boxes)
