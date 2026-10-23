"""The pages as an engine read them become a conversion: blocks in reading order with their names
(plan M1, 3.2)."""

from collections import Counter

from app.conversion.assemble import assemble
from app.conversion.base import Conversion
from app.conversion.layout import RawBlock, RawCell, RawPage


def text(page: int, words: str, top: float, x0: float = 56.0) -> RawBlock:
    return RawBlock(page, "text", words, (x0, top, x0 + 200, top + 12), 11.0, False, False)


def table(page: int, top: float, *rows: tuple[str | None, ...], header: bool = False) -> RawBlock:
    cells = tuple(
        tuple(None if value is None else RawCell(value, header and index == 0, page) for value in row)
        for index, row in enumerate(rows)
    )
    return RawBlock(page, "table", "", (56, top, 500, top + 80), None, False, False, cells)


def converted(*blocks_per_page: list[RawBlock]) -> Conversion:
    pages = [RawPage(number, 842.0, list(blocks)) for number, blocks in enumerate(blocks_per_page, start=1)]
    return assemble(pages, engine="pdfplumber", version="0.11.10")


def test_the_blocks_of_a_page_are_named_in_reading_order_top_down_then_left_to_right() -> None:
    conversion = converted(
        [text(1, "unten", 400), text(1, "rechts", 100, x0=320), text(1, "links", 100)],
        [text(2, "zweite Seite", 80)],
    )

    assert [(block.id, block.text) for block in conversion.blocks] == [
        ("p1-b1", "links"),
        ("p1-b2", "rechts"),
        ("p1-b3", "unten"),
        ("p2-b1", "zweite Seite"),
    ]
    assert (conversion.engine, conversion.engine_version, conversion.pages) == ("pdfplumber", "0.11.10", 2)


def test_tables_are_counted_across_the_document_and_their_cells_named_by_row_and_column() -> None:
    conversion = converted(
        [table(1, 100, ("Nr.", "Lernfeld"), ("1", "Einführung"), header=True)],
        [text(2, "Zwischentext", 60), table(2, 200, ("Modul", None, "ECTS"), ("M1", "Grundlagen", "5"))],
    )

    first, _, second = conversion.blocks
    assert [cell.id for cell in first.cells] == ["T1:r1c1", "T1:r1c2", "T1:r2c1", "T1:r2c2"]
    assert [cell.header for cell in first.cells] == [True, True, False, False]
    # the place a spanning cell covers has no cell; the next keeps its column
    assert [cell.id for cell in second.cells] == ["T2:r1c1", "T2:r1c3", "T2:r2c1", "T2:r2c2", "T2:r2c3"]
    assert (first.kind, first.font_size, first.bold) == ("table", None, False)


def test_a_table_s_text_is_its_rows_its_cells_parted_by_bars() -> None:
    conversion = converted([table(1, 100, ("Nr.", "Ziel | Inhalt"), ("1", ""), header=True)])

    assert conversion.blocks[0].text == "Nr. | Ziel \\| Inhalt\n1 | "


def test_a_table_continued_over_a_page_is_one_block_whose_cells_stand_on_both_pages() -> None:
    conversion = converted(
        [text(1, "Übersicht", 60), table(1, 600, ("1", "a"), ("2", "b"))],
        [table(2, 70, ("3", "c")), text(2, "Danach", 300)],
    )

    assert [block.id for block in conversion.blocks] == ["p1-b1", "p1-b2", "p2-b1"]
    merged = conversion.blocks[1]
    assert [(cell.id, cell.page) for cell in merged.cells if cell.column == 1] == [
        ("T1:r1c1", 1),
        ("T1:r2c1", 1),
        ("T1:r3c1", 2),
    ]
    assert conversion.blocks[2].text == "Danach"


def test_a_page_of_nothing_is_a_page_still() -> None:
    conversion = converted([text(1, "Deckblatt", 100)], [])

    assert conversion.pages == 2
    assert len(conversion.printed_pages) == 2


def test_the_text_an_engine_dropped_is_a_finding_for_each_reason_with_its_words_and_pages() -> None:
    pages = [
        RawPage(1, 842.0, [text(1, "Deckblatt", 100)], dropped=Counter({"tiny": 2, "vertical": 1})),
        RawPage(2, 842.0, [text(2, "Inhalt", 100)]),
        RawPage(3, 842.0, [], dropped=Counter({"tiny": 1})),
    ]

    conversion = assemble(pages, engine="pdfplumber", version="0.11.10")

    assert [(finding.code, finding.params) for finding in conversion.findings] == [
        ("text_dropped", {"reason": "vertical", "count": 1, "pages": [1]}),
        ("text_dropped", {"reason": "tiny", "count": 3, "pages": [1, 3]}),
    ]


def test_a_conversion_shows_the_symbols_mapped_and_carries_the_findings() -> None:
    arrow, bullet, broken = chr(0xF0DA), chr(0xF0B7), chr(0xFFFD)
    conversion = converted(
        [text(1, f"{arrow} Lernbereich 2", 100), text(1, f"{bullet} Punkt", 200), text(1, broken * 40, 300)]
    )

    assert conversion.blocks[0].text == f"{chr(0x2794)} Lernbereich 2"
    assert [finding.code for finding in conversion.findings] == ["unmapped_symbol", "encoding_suspect"]
