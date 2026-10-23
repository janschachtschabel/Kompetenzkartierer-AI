"""What a conversion asks of a file before and after converting it (plan M1, 3.5).

Before: that it opens as a PDF (``unreadable``), has no more pages than the service takes
(``too_many_pages``, MAX_PDF_PAGES) and carries a text layer the engine can read (``needs_ocr``:
pdfplumber reads no scan; Docling with OCR follows in 3b). After: that the engine found text or a
table beyond running heads and feet (``empty``). Each is a refusal with its code, which the job
records as the conversion's reason; it runs in the converting child (app/conversion/runners.py).
"""

from pathlib import Path
from typing import Literal

from app.conversion.base import Conversion, Engine
from app.conversion.text_layer import UnreadablePdf, needs_ocr, page_text_lengths

RefusalCode = Literal["unreadable", "too_many_pages", "needs_ocr", "empty"]


class ConversionRefused(ValueError):
    def __init__(self, code: RefusalCode, message: str) -> None:
        super().__init__(message)
        self.code: RefusalCode = code


def convert_file(path: Path, engine: Engine, *, max_pages: int) -> Conversion:
    try:
        pages = page_text_lengths(path)
    except UnreadablePdf:
        raise ConversionRefused("unreadable", "the file cannot be read as a PDF") from None
    if len(pages) > max_pages:
        raise ConversionRefused("too_many_pages", f"{len(pages)} pages, more than the {max_pages} taken")
    if needs_ocr(pages):
        raise ConversionRefused("needs_ocr", "too few pages carry a text layer; the file needs OCR")
    try:
        conversion = engine.convert(path)
    except UnreadablePdf:
        raise ConversionRefused("unreadable", "the file cannot be read as a PDF") from None
    if not any(block.kind in ("text", "table") for block in conversion.blocks):
        raise ConversionRefused("empty", "the conversion found no text beyond running heads and feet")
    return conversion
