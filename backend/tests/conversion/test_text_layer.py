"""Whether a PDF carries a text layer pdfplumber can read, or needs OCR first (plan M1, 3.5)."""

from pathlib import Path

import pytest

from app.conversion.text_layer import PageText, TooManyPages, UnreadablePdf, needs_ocr, page_text_lengths
from tests.conversion.raw_pdf import SENTENCE, pages_pdf

FIXTURES = Path(__file__).parent / "fixtures"
PAGES = 100


def test_each_page_yields_the_signs_of_its_text_layer() -> None:
    pages = page_text_lengths(FIXTURES / "edges.pdf", max_pages=PAGES)

    assert [page.page for page in pages] == [1, 2, 3, 4, 5]
    assert all(page.signs > 100 for page in pages)


def test_a_page_of_an_image_yields_no_text() -> None:
    pages = page_text_lengths(FIXTURES / "scan.pdf", max_pages=PAGES)

    assert [page.signs > 0 for page in pages] == [True, False, False, False]


def test_a_scan_needs_ocr_and_a_born_digital_plan_does_not() -> None:
    assert needs_ocr(page_text_lengths(FIXTURES / "scan.pdf", max_pages=PAGES))
    assert not needs_ocr(page_text_lengths(FIXTURES / "edges.pdf", max_pages=PAGES))


@pytest.mark.parametrize(
    ("with_text", "without", "wanted"),
    [
        (21, 2, False),  # a measured curriculum: two near-empty pages of 23
        (6, 3, True),  # a third without text: a scanned annex
        (0, 0, True),  # no page at all: nothing to read
    ],
)
def test_a_document_needs_ocr_where_under_four_fifths_of_its_pages_carry_text(
    with_text: int, without: int, wanted: bool
) -> None:
    pages = [PageText(page=n, signs=1500, drawn=1500) for n in range(1, with_text + 1)]
    pages += [PageText(page=with_text + n, signs=12, drawn=12) for n in range(1, without + 1)]

    assert needs_ocr(pages) is wanted


def test_a_file_that_is_no_pdf_is_unreadable_and_says_so_without_its_path(tmp_path: Path) -> None:
    broken = tmp_path / "geheim" / "lehrplan.pdf"
    broken.parent.mkdir()
    broken.write_bytes(b"%PDF-1.7\nthis is no document\n")

    with pytest.raises(UnreadablePdf) as refused:
        page_text_lengths(broken, max_pages=PAGES)

    assert "geheim" not in str(refused.value)


def test_a_page_the_file_claims_but_lacks_makes_it_unreadable(tmp_path: Path) -> None:
    lying = tmp_path / "lehrplan.pdf"
    lying.write_bytes(pages_pdf([SENTENCE], count=3))  # a common breakage: the tree counts pages it lost

    with pytest.raises(UnreadablePdf):
        page_text_lengths(lying, max_pages=PAGES)


def test_too_many_pages_are_counted_before_any_page_is_read(tmp_path: Path) -> None:
    lying = tmp_path / "lehrplan.pdf"
    lying.write_bytes(pages_pdf([SENTENCE], count=3))  # reading a page past the first would fail

    with pytest.raises(TooManyPages) as refused:
        page_text_lengths(lying, max_pages=2)

    assert refused.value.pages == 3
