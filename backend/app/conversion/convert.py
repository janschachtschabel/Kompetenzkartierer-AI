"""What a conversion asks of a file before and after converting it (plan M1, 3.5).

Before: that it opens as a PDF (``unreadable``), has no more pages than the service takes
(``too_many_pages``, MAX_PDF_PAGES), no page of more signs than a page holds (``too_dense``: a
file made to fill the database) and carries a text layer the engine can read (``needs_ocr``:
pdfplumber reads no scan; Docling with OCR follows in 3b). After: that the engine found text or a
table beyond running heads and feet (``empty``). Each is a refusal with its code, which the job
records as the conversion's reason; it runs in the converting child (app/conversion/runners.py).
"""

from pathlib import Path
from typing import Literal

from app.conversion.base import Conversion, Engine
from app.conversion.text_layer import TooManyPages, UnreadablePdf, needs_ocr, page_text_lengths

RefusalCode = Literal["unreadable", "too_many_pages", "too_dense", "needs_ocr", "empty"]
# A dense page of a Lehrplan - small print, a table without rules - holds some 6,000 signs; this
# is many times that, and bounds what one page's blocks weigh in the database and in an answer
MAX_PAGE_SIGNS = 100_000


class ConversionRefused(ValueError):
    def __init__(self, code: RefusalCode, message: str) -> None:
        super().__init__(message)
        self.code: RefusalCode = code


def convert_file(path: Path, engine: Engine, *, max_pages: int) -> Conversion:
    try:
        pages = page_text_lengths(path, max_pages=max_pages)
    except UnreadablePdf:
        raise ConversionRefused("unreadable", "the file cannot be read as a PDF") from None
    except TooManyPages as counted:
        raise ConversionRefused("too_many_pages", str(counted)) from None
    if any(page.drawn > MAX_PAGE_SIGNS for page in pages):
        raise ConversionRefused("too_dense", f"a page holds more than the {MAX_PAGE_SIGNS} signs taken")
    if needs_ocr(pages):
        raise ConversionRefused("needs_ocr", "too few pages carry a text layer; the file needs OCR")
    try:
        conversion = engine.convert(path)
    except UnreadablePdf:
        raise ConversionRefused("unreadable", "the file cannot be read as a PDF") from None
    if not any(block.kind in ("text", "table") for block in conversion.blocks):
        raise ConversionRefused("empty", "the conversion found no text beyond running heads and feet")
    return conversion
