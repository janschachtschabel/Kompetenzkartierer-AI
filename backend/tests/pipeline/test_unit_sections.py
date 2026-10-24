"""The sections the prefix of X3's and X4's requests is cut by where the document does not fit whole
(plan M1 7b, F5; app/pipeline/prefix.py): one for each node at its heading, from its heading to
before the next heading of its level or one above, at its level in the tree; a frame part where X2
reads it typed - by its own depth, and no section it lies in skipped."""

from uuid import UUID

from app.pipeline.prefix import Section
from app.pipeline.unit_prefix import sections
from app.pipeline.x2_segments import SegmentNode


def uuid(number: int) -> UUID:
    return UUID(int=number)


# the shape of tests/pipeline/test_x2_segments.py: 13 blocks, the title pages at 0 and 1
NODES = [
    SegmentNode(uuid(1), None, 2, "full", "Kompetenzen"),
    SegmentNode(uuid(2), uuid(1), 4, "full", "Optik"),
    SegmentNode(uuid(3), uuid(1), 8, "typed", "Hinweise"),
    SegmentNode(uuid(4), None, 10, "skip", "Anhang"),
    SegmentNode(uuid(5), uuid(4), 11, "typed", "Anhang 1"),
]


def test_each_node_s_section_runs_to_the_next_heading_of_its_level_or_one_above() -> None:
    assert sections(NODES, 13) == [
        Section(str(uuid(1)), "Kompetenzen", 1, 2, 9),
        Section(str(uuid(2)), "Optik", 2, 4, 7),
        Section(str(uuid(3)), "Hinweise", 2, 8, 9, frame=True),
        Section(str(uuid(4)), "Anhang", 1, 10, 12),
        # typed of its own, but in a section skipped: X2 reads nothing of it, no window keeps it
        Section(str(uuid(5)), "Anhang 1", 2, 11, 12),
    ]


def test_the_nodes_may_come_in_any_order() -> None:
    assert sections(list(reversed(NODES)), 13) == sections(NODES, 13)


def test_a_node_whose_parent_has_no_heading_stands_at_the_top() -> None:
    nodes = [
        SegmentNode(uuid(1), uuid(9), 0, "full", "Erster"),
        SegmentNode(uuid(2), uuid(1), 2, "full", "Darunter"),
        SegmentNode(uuid(3), None, 4, "full", "Zweiter"),
    ]

    assert [(item.title, item.level, item.first, item.last) for item in sections(nodes, 6)] == [
        ("Erster", 1, 0, 3),
        ("Darunter", 2, 2, 3),
        ("Zweiter", 1, 4, 5),
    ]


def test_a_document_without_headings_has_no_sections() -> None:
    assert sections([], 5) == []
