"""The prefix every request about a document's units shares (plan M1 6.1, konzept §13.1): its block text
with the block ids, the document profile and the choice lists - the same bytes for every unit while
it fits, else a window for each section that keeps the title pages, the table of contents, the frame
parts and the section with its neighbours, the rest named by the outline."""

from typing import Literal

import pytest

from app.conversion.base import Block, Cell
from app.pipeline.prefix import (
    WHOLE,
    PrefixPlan,
    PrefixTooLong,
    Section,
    prefix_budget,
    render_blocks,
    render_positions,
)

Kind = Literal["text", "table", "page_header", "page_footer"]


def text(block_id: str, words: str, kind: Kind = "text") -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id,
        page=page,
        kind=kind,
        text=words,
        bbox=(0, 0, 1, 1),
        font_size=10,
        bold=False,
        italic=False,
    )


def table(block_id: str, rows: list[list[str]]) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    cells = tuple(
        Cell(id=f"T1:r{r}c{c}", page=page, row=r, column=c, text=value, header=r == 1)
        for r, row in enumerate(rows, start=1)
        for c, value in enumerate(row, start=1)
    )
    joined = "\n".join(" ".join(row) for row in rows)
    return Block(
        id=block_id, page=page, kind="table", text=joined, bbox=(0, 0, 1, 1), font_size=None, bold=False,
        italic=False, cells=cells,
    )  # fmt: skip


def test_blocks_are_written_with_their_ids_their_table_rows_and_their_pages() -> None:
    blocks = [
        text("p1-b1", "Lernfeld 1"),
        table("p1-b2", [["Nr.", "Titel"], ["1", "Kunden beraten"]]),
        text("p1-b3", "- 1 -", kind="page_footer"),
        text("p2-b1", "Kopfzeile", kind="page_header"),
        text("p2-b2", "Die Schülerinnen und Schüler\nberaten Kunden."),
    ]

    written = render_blocks(blocks, [None, "2"])

    assert written == (
        "— Seite 1 —\n"
        "[p1-b1] Lernfeld 1\n"
        "[p1-b2] Tabelle\n"
        "[T1:r1] Nr. | Titel\n"
        "[T1:r2] 1 | Kunden beraten\n"
        "— Seite 2 (gedruckt 2) —\n"
        "[p2-b2] Die Schülerinnen und Schüler\nberaten Kunden.\n"
    )


SECTIONS = "ABCD"


def document() -> tuple[list[Block], list[Section]]:
    """Title page and contents (0, 1), a frame part F (2, 3), sections A-D of a heading and two
    blocks of 300 signs each (A 4-6, B 7-9, C 10-12, D 13-15); B with B1 (8) and B2 (9)."""
    blocks = [
        text("p1-b1", "Kernlehrplan Optik"),
        text("p1-b2", "Inhalt ..... 2"),
        text("p2-b1", "Vorgaben zur Leistungsbewertung"),
        text("p2-b2", "F" * 40),
    ]
    sections = [Section("F", "Vorgaben", 1, 2, 3, frame=True)]
    for page, name in enumerate(SECTIONS, start=3):
        first = len(blocks)
        blocks += [text(f"p{page}-b1", f"Abschnitt {name}"), text(f"p{page}-b2", name * 300)]
        blocks.append(text(f"p{page}-b3", name.lower() * 300))
        sections.append(Section(name, f"Abschnitt {name}", 1, first, first + 2))
    sections += [Section("B1", "Unterabschnitt B1", 2, 8, 8), Section("B2", "Unterabschnitt B2", 2, 9, 9)]
    return blocks, sections


def plan(budget: int, always: frozenset[int] = frozenset({1})) -> PrefixPlan:
    blocks, sections = document()
    return PrefixPlan(
        blocks,
        [None] * 7,
        sections,
        profile="Dokumenttyp: Kernlehrplan",
        lists="",
        always=always,
        budget=budget,
        count=len,
    )


def whole_length() -> int:
    return len(plan(budget=100_000).for_position(0).text)


def test_a_prefix_that_fits_is_the_same_for_every_unit() -> None:
    whole = plan(budget=100_000)

    first, last = whole.for_position(0), whole.for_position(15)

    assert first == last
    assert first.window == WHOLE
    assert "[p6-b2] " + "D" * 300 in first.text and "Dokumenttyp: Kernlehrplan" in first.text
    assert first.text.index("=== DOKUMENT ===") < first.text.index("=== DOKUMENTPROFIL ===")


def test_a_prefix_too_long_keeps_the_frame_and_the_unit_s_section_with_its_neighbours() -> None:
    # the whole is too long; a section with its two neighbours fits
    cut = plan(budget=whole_length() - 200)

    in_b, also_in_b, in_d = cut.for_position(8), cut.for_position(9), cut.for_position(14)

    assert in_b == also_in_b
    assert (in_b.window, in_d.window) == ("B", "D")
    for kept in ("Kernlehrplan Optik", "Inhalt ..... 2", "F" * 40, "A" * 300, "B" * 300, "C" * 300):
        assert kept in in_b.text
    assert "D" * 300 not in in_b.text
    assert "Abschnitt D" in in_b.text  # the outline names what the window leaves out
    assert "C" * 300 in in_d.text and "A" * 300 not in in_d.text


def test_a_section_too_long_with_its_neighbours_goes_one_level_down() -> None:
    # A, B and C no longer fit side by side: B's own text, B1 and B2 with the frame do
    tight = plan(budget=whole_length() - 1000)

    in_b2 = tight.for_position(9)

    assert in_b2.window == "B2"
    assert "[p4-b1] Abschnitt B" in in_b2.text and "B" * 300 in in_b2.text  # B's own text, not its title
    assert "A" * 300 not in in_b2.text and "C" * 300 not in in_b2.text
    assert "F" * 40 in in_b2.text


def test_a_window_keeps_the_contents_wherever_they_stand() -> None:
    # a table of contents after the first heading is kept as the title pages are
    in_d = plan(budget=whole_length() - 200, always=frozenset({5})).for_position(14)

    assert in_d.window == "D"
    assert "[p3-b2] " + "A" * 300 in in_d.text and "a" * 300 not in in_d.text


def test_a_document_too_long_for_any_window_is_refused() -> None:
    with pytest.raises(PrefixTooLong):
        plan(budget=200).for_position(8)


def test_a_prefix_may_hold_the_window_less_the_rest_of_a_request_and_the_answer_a_tenth_beside() -> None:
    # gpt-6-luna's 272,000 with the answer's cap of 16,000 and the 17,000 a request needs beside
    assert prefix_budget(272_000, 16_000) == 217_272


def test_a_section_whose_neighbours_do_not_fit_is_read_alone() -> None:
    # D has no subsections: the least that holds it is D alone beside the frame
    budget, alone = whole_length(), None
    while True:
        try:
            alone = plan(budget=budget).for_position(14)
        except PrefixTooLong:
            break
        budget -= 50
    assert alone is not None

    assert alone.window == "D"
    assert "D" * 300 in alone.text and "C" * 300 not in alone.text
    assert "„Abschnitt D“;" in alone.text and "Nachbarn" not in alone.text  # it says what it holds


def test_a_prefix_is_counted_once_for_each_text_it_may_be() -> None:
    counted: list[int] = []

    def count(text: str) -> int:
        counted.append(len(text))
        return len(text)

    blocks, sections = document()
    budget = whole_length() - 200
    shared = PrefixPlan(
        blocks, [None] * 7, sections, profile="", lists="", always={1}, budget=budget, count=count
    )
    first = shared.for_position(8)
    counted_once = len(counted)

    assert shared.for_position(9) == first
    assert len(counted) == counted_once


def test_blocks_left_out_before_the_first_shown_are_marked() -> None:
    blocks = [text("p1-b1", "Titel"), text("p1-b2", "Vorwort"), text("p1-b3", "Inhalt")]

    assert render_positions(blocks, [2], [None]).startswith("[…]\n— Seite 1 —\n[p1-b3] Inhalt")
