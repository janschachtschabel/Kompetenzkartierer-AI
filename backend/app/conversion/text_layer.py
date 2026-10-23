"""Whether a PDF carries a text layer to convert, or needs OCR first (plan M1, 3.5).

From the old app: running OCR on a born-digital curriculum costs half again the conversion time
for nothing, and pdfplumber reads no scan at all. The two cases are far apart and cheap to tell:
a measured 23-page curriculum carries a median of 1787 signs per page, a page without a text
layer none. The rule is document-wide on purpose: per page it would take the near-empty pages
every curriculum has (2 of 23 in the measured one) for scans.

A file pypdfium2 cannot open is unreadable, a case of its own: it needs no OCR, it is no PDF.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Below this a page carries a running head at most
MIN_SIGNS_PER_PAGE = 20
# Under this share of pages with text, content is only OCR's to reach: the measured curriculum
# sits at 21/23 = 0.91, a scanned annex of a fifth or more falls below
MIN_TEXT_PAGE_SHARE = 0.8


class UnreadablePdf(ValueError):
    """pypdfium2 cannot open the file as a PDF."""


@dataclass(frozen=True)
class PageText:
    page: int  # from 1
    signs: int


def page_text_lengths(path: Path) -> list[PageText]:
    """The signs the text layer yields on each page."""
    import pypdfium2 as pdfium  # in the converting child alone

    try:
        document = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError:
        raise UnreadablePdf("the file cannot be read as a PDF") from None
    try:
        return [
            PageText(page=number, signs=len(page.get_textpage().get_text_bounded()))
            for number, page in enumerate(document, start=1)
        ]
    finally:
        document.close()


def needs_ocr(pages: Sequence[PageText]) -> bool:
    """Whether too few pages carry text to read the document without OCR; a document of no page
    has nothing to read either."""
    if not pages:
        return True
    with_text = sum(1 for page in pages if page.signs >= MIN_SIGNS_PER_PAGE)
    return with_text / len(pages) < MIN_TEXT_PAGE_SHARE
