"""X2's work packages (plan M1 6.5): from the document's tree and its blocks, without the model - the
title pages before the first heading, then each node's own text from its heading to the next; a
node's depth its type's or its function's, a skipped section's sections skipped with it; a package
over MOST_PAGES parted at page boundaries; every block of the text in exactly one package."""

from typing import Literal
from uuid import UUID

from app.conversion.base import Block
from app.pipeline.x2_segments import MOST_PAGES, SegmentNode, WorkPackage, depth_of, segments

CV = "https://w3id.org/wlo/curriculum/vocab#"
Kind = Literal["text", "page_header", "page_footer"]


def text(block_id: str, words: str = "Text.", kind: Kind = "text") -> Block:
    return Block(
        id=block_id, page=int(block_id[1 : block_id.index("-")]), kind=kind, text=words,
        bbox=(0, 0, 1, 1), font_size=10, bold=False, italic=False,
    )  # fmt: skip


def uuid(number: int) -> UUID:
    return UUID(int=number)


BLOCKS = [
    text("p1-b1", "Kernlehrplan Physik"),  # 0  title pages
    text("p1-b2", "Stand 2019"),  # 1
    text("p2-b1", "Kompetenzen"),  # 2  N1
    text("p2-b2"),  # 3
    text("p2-b3", "Optik"),  # 4  N2 under N1
    text("p2-b4"),  # 5
    text("p2-b5", "Kopfzeile", kind="page_header"),  # 6
    text("p3-b1"),  # 7
    text("p3-b2", "Hinweise"),  # 8  N3 under N1, a frame part
    text("p3-b3"),  # 9
    text("p4-b1", "Anhang"),  # 10 N4, skipped
    text("p4-b2", "Anhang 1"),  # 11 N5 under N4, of its own full
    text("p4-b3"),  # 12
]
NODES = [
    SegmentNode(uuid(1), None, 2, "full", "Kompetenzen"),
    SegmentNode(uuid(2), uuid(1), 4, "full", "Optik"),
    SegmentNode(uuid(3), uuid(1), 8, "typed", "Hinweise"),
    SegmentNode(uuid(4), None, 10, "skip", "Anhang"),
    SegmentNode(uuid(5), uuid(4), 11, "full", "Anhang 1"),
]


def shape(packages: list[WorkPackage]) -> list[tuple[str, UUID | None, int, int, str, str]]:
    return [(item.key, item.node_id, item.first, item.last, item.depth, item.job) for item in packages]


def test_the_title_pages_then_each_node_s_own_text_from_its_heading_to_the_next() -> None:
    packages = segments(BLOCKS, NODES)

    assert shape(packages) == [
        ("E0", None, 0, 1, "typed", "frame"),
        ("E1", uuid(1), 2, 3, "full", "statements"),
        ("E2", uuid(2), 4, 7, "full", "statements"),
        ("E3", uuid(3), 8, 9, "typed", "frame"),
        ("E4", uuid(4), 10, 10, "skip", "none"),
        ("E5", uuid(5), 11, 12, "skip", "none"),  # under a skipped section: skipped with it
    ]


def test_a_package_names_its_blocks_pages_and_path() -> None:
    package = segments(BLOCKS, NODES)[2]

    assert (package.first_block, package.last_block, package.pages) == ("p2-b3", "p3-b1", (2, 3))
    assert package.path == ("Kompetenzen", "Optik")
    assert package.as_result() == {
        "key": "E2",
        "node_id": str(uuid(2)),
        "first": 4,
        "last": 7,
        "first_block": "p2-b3",
        "last_block": "p3-b1",
        "pages": [2, 3],
        "path": ["Kompetenzen", "Optik"],
        "depth": "full",
        "job": "statements",
    }


def covered(blocks: list[Block], packages: list[WorkPackage]) -> list[int]:
    """How often each block of the text lies in a package."""
    text_positions = [
        at for at, block in enumerate(blocks) if block.kind not in ("page_header", "page_footer")
    ]
    return [sum(item.first <= at <= item.last for item in packages) for at in text_positions]


def test_every_block_of_the_text_lies_in_exactly_one_package() -> None:
    assert set(covered(BLOCKS, segments(BLOCKS, NODES))) == {1}


def test_a_document_that_opens_with_a_heading_has_no_title_package() -> None:
    packages = segments(BLOCKS[2:], [SegmentNode(uuid(1), None, 0, "full", "Kompetenzen")])

    assert [item.key for item in packages] == ["E1"]


def test_a_document_without_headings_is_one_package_of_statements() -> None:
    packages = segments(BLOCKS, [])

    assert shape(packages) == [("E1", None, 0, 12, "full", "statements")]


def test_a_package_over_its_pages_is_parted_at_page_boundaries() -> None:
    blocks = [text("p1-b1", "Lernfeld 1")] + [
        text(f"p{page}-b{line}") for page in range(1, 41) for line in (2, 3)
    ]
    packages = segments(blocks, [SegmentNode(uuid(1), None, 0, "full", "Lernfeld 1")])

    assert [(item.key, item.pages) for item in packages] == [
        ("E1", (1, MOST_PAGES)),
        ("E2", (MOST_PAGES + 1, 2 * MOST_PAGES)),
        ("E3", (2 * MOST_PAGES + 1, 40)),
    ]
    assert {item.node_id for item in packages} == {uuid(1)}
    assert set(covered(blocks, packages)) == {1}
    assert MOST_PAGES == 15


def test_a_node_s_depth_is_its_type_s_else_its_function_s() -> None:
    assert depth_of("typed", CV + "fn_unit") == "typed"
    assert depth_of(None, CV + "fn_frame") == "typed"
    assert depth_of(None, CV + "fn_nonCurricular") == "skip"
    assert depth_of(None, CV + "fn_area") == "full"


def test_a_package_ends_at_its_last_block_of_the_text_not_at_a_footer() -> None:
    blocks = [
        text("p1-b1", "Optik"),
        text("p1-b2"),
        text("p1-b3", "- 1 -", kind="page_footer"),
        text("p2-b1", "Akustik"),
    ]
    nodes = [SegmentNode(uuid(1), None, 0, "full", "Optik"), SegmentNode(uuid(2), None, 3, "full", "Akustik")]

    [optics, _] = segments(blocks, nodes)

    assert (optics.last, optics.last_block) == (1, "p1-b2")


def test_the_nodes_may_come_in_any_order() -> None:
    assert segments(BLOCKS, list(reversed(NODES))) == segments(BLOCKS, NODES)
