"""What a conversion asks of a file before and after converting it (plan M1, 3.5)."""

from pathlib import Path

import pytest

from app.conversion.base import Block, Conversion, engine
from app.conversion.convert import ConversionRefused, convert_file
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
    [b"%PDF-1.7\nthis is no document\n", pages_pdf([SENTENCE], count=3)],
    ids=["no document", "a page lost"],
)
def test_a_file_that_is_no_pdf_is_refused_as_unreadable(tmp_path: Path, content: bytes) -> None:
    broken = tmp_path / "lehrplan.pdf"
    broken.write_bytes(content)

    with pytest.raises(ConversionRefused) as refused:
        convert_file(broken, engine("pdfplumber"), max_pages=10)

    assert refused.value.code == "unreadable"


class OnlyEdges:
    """An engine that finds nothing but running heads: the text of a document of headers alone."""

    name = "edges"
    version = "1"

    def convert(self, path: Path) -> Conversion:
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
