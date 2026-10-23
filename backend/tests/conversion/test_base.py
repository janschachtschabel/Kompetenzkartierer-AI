"""What a conversion (X0) makes of a document: blocks with stable IDs (plan M1, 3.1; konzept §13.2)."""

import math
import re
from typing import get_args

import pytest
from pydantic import ValidationError

from app.conversion.base import (
    BLOCK_ID,
    CELL_ID,
    Block,
    Cell,
    Conversion,
    EngineName,
    Finding,
    UnknownEngine,
    block_id,
    cell_id,
    engine,
    offered_engines,
)
from app.core.settings import REPOSITORY_ONTOLOGY

SHAPES = REPOSITORY_ONTOLOGY / "ontologie" / "cur-shapes.ttl"


def text_block(page: int = 1, number: int = 1, text: str = "Lernfeld 1", **fields: object) -> Block:
    values: dict[str, object] = {
        "id": block_id(page, number),
        "page": page,
        "kind": "text",
        "text": text,
        "bbox": (56.0, 70.0, 300.0, 82.0),
        "font_size": 11.0,
        "bold": False,
        "italic": False,
    }
    return Block.model_validate(values | fields)


def table_block(page: int = 1, number: int = 1) -> Block:
    cells = [
        Cell(id=cell_id(1, 1, 1), page=page, row=1, column=1, text="Lernfeld", header=True),
        Cell(id=cell_id(1, 2, 1), page=page, row=2, column=1, text="LF 1", header=False),
    ]
    return text_block(page, number, "| Lernfeld |\n| --- |\n| LF 1 |", kind="table", cells=cells)


def a_conversion(**fields: object) -> Conversion:
    values: dict[str, object] = {
        "engine": "pdfplumber",
        "engine_version": "0.11.10",
        "pages": 2,
        "printed_pages": ["5", None],
        "blocks": [text_block(1, 1), table_block(1, 2), text_block(2, 1)],
        "findings": [Finding(code="unmapped_symbol", params={"codepoint": "U+F0B7", "count": 3})],
    }
    return Conversion.model_validate(values | fields)


def test_a_block_is_named_by_its_page_and_place() -> None:
    assert block_id(3, 7) == "p3-b7"
    assert BLOCK_ID.fullmatch("p3-b7")


@pytest.mark.parametrize(("page", "number"), [(0, 1), (1, 0), (-2, 3)])
def test_pages_and_blocks_count_from_one(page: int, number: int) -> None:
    with pytest.raises(ValueError, match="from 1"):
        block_id(page, number)


def test_a_cell_is_named_by_its_table_row_and_column_from_one() -> None:
    # the Kern's own example (cur-kern.ttl, cur:tableCell)
    assert cell_id(4, 3, 2) == "T4:r3c2"
    assert CELL_ID.fullmatch("T4:r3c2")
    with pytest.raises(ValueError, match="from 1"):
        cell_id(1, 0, 1)


def test_the_block_pattern_is_the_one_the_shapes_check() -> None:
    shapes = SHAPES.read_text(encoding="utf-8")

    (pattern,) = re.findall(r'sh:path cur:blockId ; sh:pattern "([^"]+)"', shapes)

    assert pattern == f"^{BLOCK_ID.pattern}$"


def test_a_block_s_name_says_its_page() -> None:
    with pytest.raises(ValidationError, match="page 2"):
        text_block(page=1, id="p2-b1")


def test_a_table_holds_cells_and_only_a_table() -> None:
    assert table_block().cells[0].id == "T1:r1c1"
    with pytest.raises(ValidationError, match="cells"):
        text_block(kind="table")
    with pytest.raises(ValidationError, match="cells"):
        text_block(cells=table_block().cells)


def test_a_cell_s_name_says_its_row_and_column() -> None:
    with pytest.raises(ValidationError, match="row 2"):
        Cell(id="T1:r1c1", page=1, row=2, column=1, text="x", header=False)


@pytest.mark.parametrize("sign", [chr(0), chr(0xD800), chr(0xDFFF)], ids=["nul", "high", "low"])
def test_a_text_no_store_keeps_is_refused_in_a_block_and_a_cell(sign: str) -> None:
    # PostgreSQL's text and jsonb keep neither: a fault of the engine fails in its child, not there
    with pytest.raises(ValidationError, match="NUL"):
        text_block(text=f"Lern{sign}feld")
    with pytest.raises(ValidationError, match="NUL"):
        Cell(id="T1:r1c1", page=1, row=1, column=1, text=f"Lern{sign}feld", header=False)


@pytest.mark.parametrize(
    "place",
    [
        {"bbox": (56.0, 70.0, math.inf, 82.0)},
        {"bbox": (math.nan, 70.0, 300.0, 82.0)},
        {"font_size": math.nan},
    ],
    ids=["infinite", "nan", "size"],
)
def test_a_block_stands_at_finite_numbers(place: dict[str, object]) -> None:
    # JSON has no NaN: the child would write null, and its answer would fail to read back
    with pytest.raises(ValidationError, match="finite"):
        Block.model_validate(text_block().model_dump() | place)


def test_a_conversion_says_a_printed_page_or_none_for_each_page() -> None:
    with pytest.raises(ValidationError, match="printed"):
        a_conversion(printed_pages=["5"])


def test_a_conversion_names_each_block_once_on_one_of_its_pages() -> None:
    with pytest.raises(ValidationError, match="p1-b1"):
        a_conversion(blocks=[text_block(1, 1), text_block(1, 1, "again")])
    with pytest.raises(ValidationError, match="page 3"):
        a_conversion(blocks=[text_block(3, 1)])


def test_a_conversion_goes_as_json_and_comes_back_the_same() -> None:
    conversion = a_conversion()

    assert Conversion.model_validate_json(conversion.model_dump_json()) == conversion


def test_the_register_offers_pdfplumber_and_names_what_it_offers_for_another() -> None:
    assert offered_engines() == ("pdfplumber",)
    with pytest.raises(UnknownEngine, match="pdfplumber"):
        engine("docling")


def test_the_api_names_the_engines_the_register_offers() -> None:
    assert get_args(EngineName) == offered_engines()
