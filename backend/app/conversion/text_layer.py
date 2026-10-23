"""Whether a PDF carries a text layer to convert, or needs OCR first (plan M1, 3.5).

From the old app: running OCR on a born-digital curriculum costs half again the conversion time
for nothing, and pdfplumber reads no scan at all. The two cases are far apart and cheap to tell:
a measured 23-page curriculum carries a median of 1787 signs per page, a page without a text
layer none. The rule is document-wide on purpose: per page it would take the near-empty pages
every curriculum has (2 of 23 in the measured one) for scans.

A file pypdfium2 cannot open, or one page of which it cannot load, is unreadable, a case of its
own: it needs no OCR, it is no PDF. The pages are counted before any is read: a file of more than
the service takes is refused at once, not after reading them all.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # loaded in the converting child alone, as below
    from pypdfium2 import PdfTextPage

# Below this a page carries a running head at most
MIN_SIGNS_PER_PAGE = 20
# Under this share of pages with text, content is only OCR's to reach: the measured curriculum
# sits at 21/23 = 0.91, a scanned annex of a fifth or more falls below
MIN_TEXT_PAGE_SHARE = 0.8


class UnreadablePdf(ValueError):
    """pypdfium2 cannot open the file as a PDF, or cannot load a page of it."""


class TooManyPages(ValueError):
    def __init__(self, pages: int, max_pages: int) -> None:
        super().__init__(f"{pages} pages, more than the {max_pages} taken")
        self.pages = pages


@dataclass(frozen=True)
class PageText:
    page: int  # from 1
    signs: int  # within the page's box: what a reader sees, for the rule of OCR
    drawn: int  # every sign the page sets, in its box or not: what its blocks may weigh


def page_text_lengths(path: Path, *, max_pages: int) -> list[PageText]:
    """The signs the text layer yields on each page; TooManyPages past ``max_pages``."""
    import pypdfium2 as pdfium  # in the converting child alone

    try:
        document = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError:
        raise UnreadablePdf("the file cannot be read as a PDF") from None
    try:
        pages = len(document)
        if pages > max_pages:
            raise TooManyPages(pages, max_pages)
        try:
            return [_page_text(number, document[number - 1].get_textpage()) for number in range(1, pages + 1)]
        except pdfium.PdfiumError:  # a page the file counts but cannot give
            raise UnreadablePdf("a page of the file cannot be read") from None
    finally:
        document.close()


def _page_text(number: int, text: "PdfTextPage") -> PageText:
    return PageText(page=number, signs=len(text.get_text_bounded()), drawn=text.count_chars())


def needs_ocr(pages: Sequence[PageText]) -> bool:
    """Whether too few pages carry text to read the document without OCR; a document of no page
    has nothing to read either."""
    if not pages:
        return True
    with_text = sum(1 for page in pages if page.signs >= MIN_SIGNS_PER_PAGE)
    return with_text / len(pages) < MIN_TEXT_PAGE_SHARE
