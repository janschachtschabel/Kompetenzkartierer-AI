"""The reading order of a page's blocks (plan M1, 3.2): columns left to right, each top down."""

import pytest

from app.conversion.layout import RawBlock, RawCell
from app.conversion.reading_order import reading_order


def block(text: str, x0: float, top: float, x1: float, bottom: float) -> RawBlock:
    return RawBlock(1, "text", text, (x0, top, x1, bottom), 10.0, False, False)


def table(name: str, x0: float, top: float, x1: float, bottom: float) -> RawBlock:
    """A table, its name as its text for the test: its rows give it the text it has."""
    return RawBlock(
        1, "table", name, (x0, top, x1, bottom), None, False, False, ((RawCell(name, False, 1),),)
    )


def read(blocks: list[RawBlock]) -> list[str]:
    return [found.text for found in reading_order(blocks)]


def test_two_columns_are_read_one_after_the_other_each_top_down() -> None:
    # the right column's first paragraph begins above the left column's second
    blocks = [
        block("R2", 305, 220, 540, 600),
        block("L2", 56, 320, 290, 500),
        block("R1", 305, 90, 540, 200),
        block("L1", 56, 100, 290, 300),
    ]

    assert read(blocks) == ["L1", "L2", "R1", "R2"]


def test_a_heading_across_the_columns_goes_before_them_and_a_foot_after() -> None:
    blocks = [
        block("Fuß", 56, 800, 540, 810),
        block("R1", 305, 100, 540, 400),
        block("L1", 56, 100, 290, 300),
        block("Kapitel", 56, 60, 540, 80),
        block("L2", 56, 320, 290, 700),
    ]

    assert read(blocks) == ["Kapitel", "L1", "L2", "R1", "Fuß"]


def test_a_page_of_one_column_reads_top_down_as_before() -> None:
    # an indented paragraph, a short heading, a page number in the middle of the foot
    blocks = [
        block("eingerückt", 70, 200, 540, 260),
        block("5", 290, 810, 300, 820),
        block("Überschrift", 56, 100, 300, 114),
        block("Absatz", 56, 130, 540, 190),
    ]

    assert read(blocks) == ["Überschrift", "Absatz", "eingerückt", "5"]


def test_blocks_side_by_side_above_one_across_both_are_read_by_their_rows() -> None:
    blocks = [
        block("unten", 56, 400, 520, 412),
        block("rechts", 320, 100, 520, 112),
        block("links", 56, 100, 256, 112),
    ]

    assert read(blocks) == ["links", "rechts", "unten"]


def test_a_table_is_read_in_its_column() -> None:
    blocks = [
        block("Hinweis", 340, 340, 470, 352),
        table("T", 56, 85, 283, 760),
        block("Danach", 56, 780, 540, 792),
    ]

    assert read(blocks) == ["T", "Hinweis", "Danach"]


def test_blocks_no_strip_parts_are_read_top_down_whatever_their_left_edges() -> None:
    # each reaches into the other's height and breadth: no cut, the higher one first
    blocks = [block("tiefer, links", 56, 150, 300, 250), block("höher, rechts", 250, 100, 540, 200)]

    assert read(blocks) == ["höher, rechts", "tiefer, links"]


@pytest.mark.parametrize(("strip", "order"), [(0.5, ["A", "B", "C"]), (2.0, ["A", "C", "B"])])
def test_a_strip_wider_than_a_point_cuts_and_a_narrower_one_does_not(strip: float, order: list[str]) -> None:
    # A and B side by side, C below A: a strip between A and B down the page makes two columns
    blocks = [
        block("C", 56, 130, 300, 142),
        block("B", 300 + strip, 100, 540, 112),
        block("A", 56, 100, 300, 112),
    ]

    assert read(blocks) == order


def test_no_blocks_are_none_and_one_is_one() -> None:
    assert reading_order([]) == []
    assert read([block("allein", 56, 100, 300, 112)]) == ["allein"]
