"""The conversion as Markdown for a reader, each block behind its name (plan M1, 3.5)."""

from app.conversion.base import Block, Cell, Conversion, cell_id
from app.conversion.markdown import markdown_of


def block(number: int, text: str, **fields: object) -> Block:
    values: dict[str, object] = {
        "id": f"p1-b{number}",
        "page": 1,
        "kind": "text",
        "text": text,
        "bbox": (56, 100 * number, 300, 100 * number + 12),
        "font_size": 11,
        "bold": False,
        "italic": False,
    }
    return Block.model_validate(values | fields)


def cells(*rows: tuple[str, ...], header: bool) -> tuple[Cell, ...]:
    return tuple(
        Cell(
            id=cell_id(1, row, column), page=1, row=row, column=column, text=text, header=header and row == 1
        )
        for row, values in enumerate(rows, start=1)
        for column, text in enumerate(values, start=1)
    )


def conversion(*blocks: Block) -> Conversion:
    return Conversion(engine="pdfplumber", engine_version="1", pages=1, printed_pages=(None,), blocks=blocks)


def test_each_block_stands_behind_its_name_a_blank_line_apart() -> None:
    found = markdown_of(conversion(block(1, "1 Lernfeld"), block(2, "Die Lernenden\nplanen.")))

    assert found == "<!-- p1-b1 -->\n1 Lernfeld\n\n<!-- p1-b2 -->\nDie Lernenden\nplanen.\n"


def test_a_table_is_a_table_under_its_header_row() -> None:
    table = block(
        1,
        "",
        kind="table",
        font_size=None,
        cells=cells(("Nr.", "Ziel | Inhalt"), ("1", "Planen"), header=True),
    )

    assert markdown_of(conversion(table)) == (
        "<!-- p1-b1 -->\n| Nr. | Ziel \\| Inhalt |\n| --- | --- |\n| 1 | Planen |\n"
    )


def test_a_table_without_a_header_row_gets_an_empty_one() -> None:
    table = block(1, "", kind="table", font_size=None, cells=cells(("1", "Planen"), header=False))

    assert markdown_of(conversion(table)) == "<!-- p1-b1 -->\n|  |  |\n| --- | --- |\n| 1 | Planen |\n"


def test_a_place_a_spanning_cell_covers_is_an_empty_cell() -> None:
    found = (
        Cell(id="T1:r1c1", page=1, row=1, column=1, text="Lernfeld", header=True),
        Cell(id="T1:r1c3", page=1, row=1, column=3, text="Zeit", header=True),
        Cell(id="T1:r2c1", page=1, row=2, column=1, text="LF 1", header=False),
        Cell(id="T1:r2c2", page=1, row=2, column=2, text="Ziel", header=False),
        Cell(id="T1:r2c3", page=1, row=2, column=3, text="40", header=False),
    )

    assert markdown_of(conversion(block(1, "", kind="table", font_size=None, cells=found))) == (
        "<!-- p1-b1 -->\n| Lernfeld |  | Zeit |\n| --- | --- | --- |\n| LF 1 | Ziel | 40 |\n"
    )
