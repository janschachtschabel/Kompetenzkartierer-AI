"""Running heads and feet marked, not dropped, and the number printed on each page (plan M1, 3.3)."""

from pathlib import Path

import pytest

from app.conversion.base import engine
from app.conversion.layout import RawBlock, RawPage
from app.conversion.page_edges import mark_edges, printed_number

FIXTURES = Path(__file__).parent / "fixtures"
HEIGHT = 842.0


def block(page: int, text: str, top: float) -> RawBlock:
    return RawBlock(page, "text", text, (56, top, 400, top + 10), 9.0, False, False)


def document(*pages: list[RawBlock]) -> list[RawPage]:
    return [RawPage(number, HEIGHT, list(blocks)) for number, blocks in enumerate(pages, start=1)]


def kinds(pages: list[RawPage]) -> list[list[str]]:
    return [[found.kind for found in page.blocks] for page in pages]


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("5", "5"),
        ("- 5 -", "5"),
        ("\N{EN DASH} 12 \N{EN DASH}", "12"),
        ("Seite 5 von 12", "5"),
        ("S. 7", "7"),
        ("Rahmenlehrplan Mechatronik \N{EN DASH} Seite 23", "23"),
        ("12/40", "12"),
        ("IV", "IV"),
        ("- xii -", "xii"),
        ("Lernfeld 5", None),
        ("Die Lernenden planen 5 Schritte.", None),
        ("Inhalt", None),
    ],
)
def test_a_page_number_is_read_off_a_line_that_is_one(text: str, number: str | None) -> None:
    assert printed_number(text) == number


def test_a_line_repeated_at_the_top_or_foot_of_pages_is_marked_and_stays() -> None:
    pages = document(
        *[[block(n, "Rahmenlehrplan Mechatronik", 30), block(n, f"Inhalt {n}", 100)] for n in range(1, 4)],
        [block(4, "Anhang", 100)],
    )

    mark_edges(pages)

    assert kinds(pages) == [["page_header", "text"]] * 3 + [["text"]]
    assert pages[0].blocks[0].text == "Rahmenlehrplan Mechatronik"


def test_a_running_foot_differs_only_in_its_numbers() -> None:
    pages = document(
        *[[block(n, "Inhalt", 100), block(n, f"Stand 2026 · Kapitel {n}", 815)] for n in range(1, 4)]
    )

    mark_edges(pages)

    assert kinds(pages) == [["text", "page_footer"]] * 3


def test_a_heading_at_the_top_of_a_few_pages_of_many_stays_text() -> None:
    # "Lernfeld 1", "Lernfeld 2" … on 3 pages of 20: a heading, not a running head
    pages = document(*[[block(n, f"Lernfeld {n}" if n <= 3 else "Text", 40)] for n in range(1, 21)])

    mark_edges(pages)

    assert all(found.kind == "text" for page in pages[:3] for found in page.blocks)


def test_a_page_number_in_the_foot_is_marked_and_printed_where_it_stands_alone() -> None:
    pages = document([block(1, "Deckblatt", 100), block(1, "- 7 -", 815)], [block(2, "Text", 100)])

    printed = mark_edges(pages)

    assert kinds(pages) == [["text", "page_footer"], ["text"]]
    assert printed == ("7", None)


def test_a_number_in_the_text_of_a_page_is_no_page_number() -> None:
    pages = document([block(1, "5", 400)])

    assert mark_edges(pages) == (None,)
    assert kinds(pages) == [["text"]]


def test_the_foot_s_number_goes_before_the_head_s() -> None:
    pages = document([block(1, "Seite 3", 30), block(1, "4", 815)])

    assert mark_edges(pages) == ("4",)


def test_the_fixture_s_heads_and_feet_are_marked_and_its_pages_printed_i_ii_1_2_3() -> None:
    conversion = engine("pdfplumber").convert(FIXTURES / "edges.pdf")

    assert conversion.printed_pages == ("I", "II", "1", "2", "3")
    assert [block.kind for block in conversion.blocks if block.page == 1] == [
        "page_header",
        "text",
        "page_footer",
    ]
