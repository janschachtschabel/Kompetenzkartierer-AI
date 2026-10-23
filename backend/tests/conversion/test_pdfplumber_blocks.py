"""The engine pdfplumber: a PDF's text layer into named blocks (plan M1, 3.2), on the fixtures."""

from pathlib import Path

import pytest

from app.conversion.base import Conversion, engine
from app.conversion.text_layer import UnreadablePdf

FIXTURES = Path(__file__).parent / "fixtures"


def converted(name: str) -> Conversion:
    return engine("pdfplumber").convert(FIXTURES / name)


def test_the_register_hands_out_pdfplumber_at_its_version() -> None:
    found = engine("pdfplumber")

    assert (found.name, found.version) == ("pdfplumber", "0.11.10")


def test_headings_paragraphs_and_a_note_are_blocks_of_their_own() -> None:
    conversion = converted("prose.pdf")

    first_page = [block for block in conversion.blocks if block.page == 1]
    assert [(block.id, block.text.split("\n")[0][:24], block.bold, block.italic) for block in first_page] == [
        ("p1-b1", "1 Lernfeld Steuerungstec", True, False),
        ("p1-b2", "Die Schülerinnen und Sch", False, False),
        ("p1-b3", "Sie bewerten Lösungen na", False, False),
        ("p1-b4", "Hinweis: Die Inhalte sin", False, True),
        ("p1-b5", "2 Lernfeld Antriebe", True, False),
        ("p1-b6", "Die Schülerinnen und Sch", False, False),
    ]
    assert first_page[1].text.count("\n") == 2  # the paragraph's three lines
    assert (first_page[0].font_size, first_page[1].font_size) == (14.0, 11.0)
    assert [block.id for block in conversion.blocks if block.page == 2] == ["p2-b1"]
    assert conversion.pages == 2


def test_tables_are_blocks_their_words_in_no_text_block_and_joined_over_pages() -> None:
    conversion = converted("tables.pdf")

    kinds = [(block.id, block.kind) for block in conversion.blocks]
    assert kinds == [
        ("p1-b1", "text"),
        ("p1-b2", "table"),
        ("p1-b3", "text"),
        ("p1-b4", "table"),
        ("p2-b1", "text"),
        ("p3-b1", "table"),
    ]
    small, long_table, with_header = (block for block in conversion.blocks if block.kind == "table")
    assert small.cells[0].id == "T1:r1c1" and small.cells[0].header
    assert max(cell.row for cell in long_table.cells) == 28
    assert {cell.page for cell in long_table.cells} == {1, 2}
    assert max(cell.row for cell in with_header.cells) == 25
    assert [cell.text for cell in with_header.cells if cell.row == 1] == ["Nr.", "Lernfeld", "Zeitrichtwert"]
    assert not any("Einführung" in block.text for block in conversion.blocks if block.kind == "text")


def test_a_file_pdfplumber_cannot_read_is_unreadable_and_says_so_without_its_path(tmp_path: Path) -> None:
    broken = tmp_path / "geheim" / "lehrplan.pdf"
    broken.parent.mkdir()
    broken.write_bytes(b"%PDF-1.7\nthis is no document\n")

    with pytest.raises(UnreadablePdf) as refused:
        engine("pdfplumber").convert(broken)

    assert "geheim" not in str(refused.value)
