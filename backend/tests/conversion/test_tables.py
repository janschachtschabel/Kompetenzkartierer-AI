"""Tables as pdfplumber finds them, and tables continued over a page break (plan M1, 3.2)."""

from pathlib import Path

import pdfplumber

from app.conversion.layout import RawBlock, RawCell, RawPage
from app.conversion.pdfplumber_blocks import read_page
from app.conversion.tables import FoundTable, merge_across_pages, table_block

FIXTURES = Path(__file__).parent / "fixtures"
HEADER = ("Nr.", "Lernfeld", "Zeitrichtwert")


def tables_of_fixture() -> list[list[RawBlock]]:
    with pdfplumber.open(FIXTURES / "tables.pdf") as pdf:
        pages = [read_page(page) for page in pdf.pages]
    found = [[table_block(table, page.chars, page.number) for table in page.tables] for page in pages]
    return [[block for block in blocks if block is not None] for blocks in found]


def texts(block: RawBlock) -> list[list[str]]:
    return [[cell.text if cell else "" for cell in row] for row in block.rows]


def test_a_table_holds_its_rows_and_knows_a_bold_first_row_for_its_header() -> None:
    first = tables_of_fixture()[0][0]

    assert first.kind == "table" and first.page == 1
    assert texts(first) == [list(HEADER), ["1", "Einführung", "40 Stunden"], ["2", "Planung", "60 Stunden"]]
    assert [cell.header for cell in first.rows[0] if cell] == [True, True, True]
    assert not any(cell.header for row in first.rows[1:] for cell in row if cell)
    assert first.bbox[1] < first.bbox[3]


def test_a_table_without_a_bold_first_row_has_no_header() -> None:
    long_table = tables_of_fixture()[0][1]

    assert texts(long_table)[0] == ["LF 1", "Ziel 1: Die Lernenden planen Schritt 1.", "20 Stunden"]
    assert not any(cell.header for row in long_table.rows for cell in row if cell)


def found_table(texts: list[list[str | None]]) -> FoundTable:
    """A table as pdfplumber reads it, a cell a unit square, None where a spanning cell covers it."""
    boxes = [[(0.0, 0.0, 1.0, 1.0) if text is not None else None for text in row] for row in texts]
    return FoundTable(texts=texts, boxes=boxes, bbox=(56.0, 100.0, 500.0, 200.0))


def grid(texts: list[list[str]], fonts: list[str | list[str]]) -> tuple[FoundTable, list[dict[str, object]]]:
    """A ruled table, each row 10 points high and each cell 50 wide, and its signs a point apart:
    those of a row set in the row's font, or in each cell's of a list."""
    boxes = [
        [(50.0 * column, 10.0 * row, 50.0 * column + 50, 10.0 * row + 10) for column in range(len(cells))]
        for row, cells in enumerate(texts)
    ]
    chars: list[dict[str, object]] = [
        {"x0": x0 + 1 + at, "x1": x0 + 2 + at, "top": top + 1, "bottom": top + 9}
        | {"text": sign, "fontname": font if isinstance(font, str) else font[column]}
        for cells, places, font in zip(texts, boxes, fonts, strict=True)
        for column, (text, (x0, top, _, _)) in enumerate(zip(cells, places, strict=True))
        for at, sign in enumerate(text)
    ]
    return FoundTable(texts=texts, boxes=boxes, bbox=(0.0, 0.0, 100.0, 10.0 * len(texts))), chars


def test_the_header_is_the_first_row_with_text_where_an_empty_one_stands_above() -> None:
    found, chars = grid(
        [["", ""], ["Nr.", "Lernfeld"], ["1", "Einführung"]], ["Helvetica", "Helvetica-Bold", "Helvetica"]
    )

    block = table_block(found, chars, page=1)

    assert block is not None and texts(block) == [["Nr.", "Lernfeld"], ["1", "Einführung"]]
    assert [[cell.header for cell in row if cell] for row in block.rows] == [[True, True], [False, False]]


def test_a_first_row_bold_in_part_is_no_header() -> None:
    found, chars = grid(
        [["Nr.", "Lernfeld"], ["1", "Einführung"]], [["Helvetica-Bold", "Helvetica"], "Helvetica"]
    )

    block = table_block(found, chars, page=1)

    assert block is not None and not any(cell.header for row in block.rows for cell in row if cell)


def test_a_cell_s_text_holds_no_control_sign() -> None:
    found = table_block(found_table([[f"Lern{chr(0)}feld{chr(0x7F)}", chr(0) * 2]]), [], page=1)

    assert found is not None and texts(found) == [["Lernfeld", ""]]


def test_a_table_of_empty_rows_is_no_block() -> None:
    assert table_block(found_table([["", None], [" ", ""]]), [], page=7) is None


def test_a_place_a_spanning_cell_covers_stays_empty_and_the_columns_stay() -> None:
    found = table_block(found_table([["Lernfeld", None, "Zeit"], ["LF 1", "Ziel", "40"]]), [], page=7)

    assert found is not None
    assert [cell.text if cell else None for cell in found.rows[0]] == ["Lernfeld", None, "Zeit"]
    assert found.page == 7 and not found.rows[0][0].header  # type: ignore[union-attr]


def table(page: int, *rows: tuple[str, ...], header: bool = False, top: float = 600.0) -> RawBlock:
    cells = tuple(
        tuple(RawCell(text=text, header=header and index == 0, page=page) for text in row)
        for index, row in enumerate(rows)
    )
    return RawBlock(page, "table", "", (56, top, 500, top + 100), None, False, False, cells)


def text(page: int, words: str, kind: str = "text", top: float = 100.0) -> RawBlock:
    return RawBlock(page, kind, words, (56, top, 500, top + 12), 11.0, False, False)  # type: ignore[arg-type]


def pages(*blocks_per_page: list[RawBlock]) -> list[RawPage]:
    return [RawPage(number, 842.0, list(blocks)) for number, blocks in enumerate(blocks_per_page, start=1)]


def test_a_table_continued_without_a_header_is_one_table_whose_cells_keep_their_pages() -> None:
    document = pages(
        [text(1, "Übersicht"), table(1, HEADER, ("1", "a", "40"), header=True)],
        [table(2, ("2", "b", "60"), ("3", "c", "80"), top=70), text(2, "Danach", top=300)],
    )

    merge_across_pages(document)

    (merged,) = [block for block in document[0].blocks if block.kind == "table"]
    assert texts(merged) == [list(HEADER), ["1", "a", "40"], ["2", "b", "60"], ["3", "c", "80"]]
    assert [row[0].page for row in merged.rows if row[0]] == [1, 1, 2, 2]
    assert [block.text for block in document[1].blocks] == ["Danach"]


def test_a_header_repeated_on_the_next_page_goes_and_the_table_runs_on() -> None:
    document = pages(
        [table(1, HEADER, ("1", "a", "40"), header=True)],
        [table(2, HEADER, ("2", "b", "60"), header=True, top=70)],
    )

    merge_across_pages(document)

    assert texts(document[0].blocks[0]) == [list(HEADER), ["1", "a", "40"], ["2", "b", "60"]]
    assert document[1].blocks == []


def test_a_running_head_and_foot_between_the_parts_do_not_part_them() -> None:
    document = pages(
        [table(1, ("1", "a", "40")), text(1, "- 1 -", "page_footer", top=820)],
        [text(2, "Rahmenlehrplan", "page_header", top=20), table(2, ("2", "b", "60"), top=70)],
    )

    merge_across_pages(document)

    assert len(document[0].blocks[0].rows) == 2
    assert [block.kind for block in document[1].blocks] == ["page_header"]


def test_a_table_over_three_pages_is_one() -> None:
    document = pages(
        [table(1, ("1", "a", "40"))],
        [table(2, ("2", "b", "60"), top=70)],
        [table(3, ("3", "c", "80"), top=70)],
    )

    merge_across_pages(document)

    assert texts(document[0].blocks[0]) == [["1", "a", "40"], ["2", "b", "60"], ["3", "c", "80"]]
    assert document[1].blocks == [] and document[2].blocks == []


def test_a_table_ends_its_page_where_text_beside_it_ends_above_it() -> None:
    # read after the table, the note beside it ends far above the table's foot
    long_table = RawBlock(1, "table", "", (56, 85, 283, 765), None, False, False, table(1, ("1", "a")).rows)
    document = pages(
        [long_table, RawBlock(1, "text", "Hinweis", (340, 332, 461, 342), 10.0, False, False)],
        [table(2, ("2", "b"), top=85)],
    )

    merge_across_pages(document)

    assert texts(document[0].blocks[0]) == [["1", "a"], ["2", "b"]]
    assert document[1].blocks == []


def test_a_page_without_text_or_table_between_two_ends_the_first() -> None:
    # an empty page, or one of a picture: what follows it is no continuation
    for between in ([], [text(2, "- 2 -", "page_footer", top=820)]):
        document = pages([table(1, ("1", "a", "40"))], between, [table(3, ("3", "c", "80"), top=70)])

        merge_across_pages(document)

        assert len(document[0].blocks[0].rows) == 1 and len(document[2].blocks) == 1


def test_tables_that_do_not_continue_one_another_stay_apart() -> None:
    other_header = ("Modul", "Titel", "ECTS")
    cases = [
        # another header: a table of its own
        pages(
            [table(1, HEADER, ("1", "a", "40"), header=True)],
            [table(2, other_header, ("M1", "x", "5"), header=True)],
        ),
        # another number of columns
        pages([table(1, ("1", "a", "40"))], [table(2, ("2", "b"), top=70)]),
        # text after the first table, or before the second
        pages([table(1, ("1", "a", "40")), text(1, "Ende", top=750)], [table(2, ("2", "b", "60"), top=70)]),
        pages([table(1, ("1", "a", "40"))], [text(2, "Anfang", top=60), table(2, ("2", "b", "60"), top=90)]),
    ]
    for document in cases:
        merge_across_pages(document)

        assert len([block for block in document[1].blocks if block.kind == "table"]) == 1


def test_a_table_continued_on_the_fixture_s_pages_is_merged_both_ways() -> None:
    found = tables_of_fixture()
    document = pages(*found)

    merge_across_pages(document)

    # page 1: the small table, then the long one with page 2's rows; page 3: the one with a header,
    # page 4's rows behind its own, the repeated header gone
    assert [len(block.rows) for block in document[0].blocks] == [3, 28]
    assert document[1].blocks == []
    (third,) = document[2].blocks
    assert texts(third)[0] == list(HEADER)
    assert len(third.rows) == 25 and document[3].blocks == []
