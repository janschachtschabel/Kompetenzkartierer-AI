"""What a conversion asks of a file before and after converting it (plan M1, 3.5)."""

from pathlib import Path

import pytest

from app.conversion import convert
from app.conversion.base import Block, Conversion, engine
from app.conversion.convert import ConversionRefused, convert_file
from app.conversion.text_layer import page_text_lengths
from tests.conversion.raw_pdf import SENTENCE, pages_pdf

FIXTURES = Path(__file__).parent / "fixtures"


def test_a_pdf_with_a_text_layer_is_converted() -> None:
    conversion = convert_file(FIXTURES / "prose.pdf", engine("pdfplumber"), max_pages=10)

    assert conversion.pages == 2 and conversion.blocks


@pytest.mark.parametrize(
    ("name", "max_pages", "code"),
    [
        ("scan.pdf", 10, "needs_ocr"),
        ("edges.pdf", 4, "too_many_pages"),
    ],
)
def test_a_file_the_engine_cannot_serve_is_refused_with_its_reason(
    name: str, max_pages: int, code: str
) -> None:
    with pytest.raises(ConversionRefused) as refused:
        convert_file(FIXTURES / name, engine("pdfplumber"), max_pages=max_pages)

    assert refused.value.code == code


@pytest.mark.parametrize(
    "content",
    [
        b"%PDF-1.7\nthis is no document\n",
        pages_pdf([SENTENCE], count=3),
        # the page tree counts one page, its kids are three: pypdfium2 counts one, pdfplumber reads
        # three - past MAX_PDF_PAGES and the density, both counted on the one
        pages_pdf([SENTENCE] * 3, count=1),
    ],
    ids=["no document", "a page lost", "pages counted two ways"],
)
def test_a_file_that_is_no_pdf_is_refused_as_unreadable(tmp_path: Path, content: bytes) -> None:
    broken = tmp_path / "lehrplan.pdf"
    broken.write_bytes(content)

    with pytest.raises(ConversionRefused) as refused:
        convert_file(broken, engine("pdfplumber"), max_pages=10)

    assert refused.value.code == "unreadable"


def test_a_page_of_more_signs_than_any_page_holds_is_refused_as_too_dense(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    densest = max(page.drawn for page in page_text_lengths(FIXTURES / "prose.pdf", max_pages=10))
    monkeypatch.setattr(convert, "MAX_PAGE_SIGNS", densest)
    assert convert_file(FIXTURES / "prose.pdf", engine("pdfplumber"), max_pages=10).pages == 2

    monkeypatch.setattr(convert, "MAX_PAGE_SIGNS", densest - 1)
    with pytest.raises(ConversionRefused) as refused:
        convert_file(FIXTURES / "prose.pdf", engine("pdfplumber"), max_pages=10)

    assert refused.value.code == "too_dense"


def test_signs_set_beyond_the_page_count_towards_its_density(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hidden = b"BT /F1 11 Tf 72 2000 Td (" + b"x" * 5000 + b") Tj ET\n"  # far above the page's box
    dense = tmp_path / "lehrplan.pdf"
    dense.write_bytes(pages_pdf([SENTENCE + hidden]))
    monkeypatch.setattr(convert, "MAX_PAGE_SIGNS", 1000)

    with pytest.raises(ConversionRefused) as refused:
        convert_file(dense, engine("pdfplumber"), max_pages=10)

    assert refused.value.code == "too_dense"


class OnlyEdges:
    """An engine that finds nothing but running heads: the text of a document of headers alone."""

    name = "edges"
    version = "1"

    def convert(self, path: Path, *, pages: int) -> Conversion:
        head = Block(
            id="p1-b1",
            page=1,
            kind="page_header",
            text="Rahmenlehrplan",
            bbox=(56, 20, 300, 30),
            font_size=9,
            bold=False,
            italic=False,
        )
        return Conversion(engine="edges", engine_version="1", pages=1, printed_pages=(None,), blocks=(head,))


def test_a_conversion_of_nothing_but_running_heads_and_feet_is_refused_as_empty() -> None:
    with pytest.raises(ConversionRefused) as refused:
        convert_file(FIXTURES / "prose.pdf", OnlyEdges(), max_pages=10)

    assert refused.value.code == "empty"
