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
        # Roman numerals in one case only: "Li" is a word
        ("XII", "XII"),
        ("Li", None),
        ("xIi", None),
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


@pytest.mark.parametrize(("repeated", "edge"), [(2, "text"), (3, "page_header")])
def test_a_line_at_the_top_is_a_running_head_from_three_pages_on(repeated: int, edge: str) -> None:
    # of 4 pages: a fifth of them is less than 3
    pages = document(
        *[
            [block(n, "Rahmenlehrplan" if n <= repeated else f"Kopf {n}a", 30), block(n, "Text", 300)]
            for n in range(1, 5)
        ]
    )

    mark_edges(pages)

    assert [page.blocks[0].kind for page in pages[:repeated]] == [edge] * repeated


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


def test_headings_whose_numbers_do_not_run_with_the_page_stay_text() -> None:
    # "Lernfeld 1" ... "Lernfeld 5" at the top of every other page of 10
    pages = document(
        *[
            [
                block(n, f"Lernfeld {n // 2 + 1}", 40) if n % 2 else block(n, "Fortsetzung", 400),
                block(n, "Text", 300),
            ]
            for n in range(1, 11)
        ]
    )

    mark_edges(pages)

    assert all(found.kind == "text" for page in pages for found in page.blocks)


def test_a_block_that_reaches_out_of_an_edge_is_none_of_it() -> None:
    # on 3 pages each: a paragraph that begins in the top edge (67 points), one that ends in the foot's
    pages = document(
        *[
            [
                RawBlock(
                    n, "text", "Kompetenzen\nDie Lernenden planen.", (56, 60, 500, 400), 11.0, False, False
                ),
                RawBlock(n, "text", "Hinweis", (56, 500, 500, 780), 11.0, False, False),
            ]
            for n in range(1, 4)
        ]
    )

    mark_edges(pages)

    assert kinds(pages) == [["text", "text"]] * 3


def test_a_number_alone_at_the_top_of_one_page_is_a_chapter_s_and_stays_text() -> None:
    pages = document([block(1, "2", 50), block(1, "Unterrichtsgestaltung", 90), block(1, "- 14 -", 815)])

    printed = mark_edges(pages)

    assert kinds(pages) == [["text", "text", "page_footer"]]
    assert printed == ("14",)


def test_chapter_numbers_alone_reaching_past_the_top_edge_on_two_pages_in_a_row_stay_text() -> None:
    # "2" and "3" in 20 points at 60 to 80 on pages 5 and 6 of 10, past the edge's 67: two pages
    # sharing an offset make a page number within the edge, not in the band beside it
    pages = document(
        *[
            [RawBlock(n, "text", str(n - 3), (56, 60, 80, 80), 20.0, True, False)] * (n in (5, 6))
            + [block(n, "Text", 300)]
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert [pages[n - 1].blocks[0].kind for n in (5, 6)] == ["text", "text"]
    assert printed == (None,) * 10


def test_numbers_alone_at_the_top_that_run_with_the_pages_are_their_numbers() -> None:
    # three pages unnumbered, a preface numbered iv, v, the text 1, 2: the number less the page is
    # the same on two pages, and again on two
    labels = [None, None, None, "iv", "v", "1", "2"]
    pages = document(
        *[
            [block(n, "Text", 300)] + ([block(n, label, 30)] if label else [])
            for n, label in enumerate(labels, 1)
        ]
    )

    printed = mark_edges(pages)

    assert printed == tuple(labels)
    assert kinds(pages) == [["text"]] * 3 + [["text", "page_header"]] * 4


@pytest.mark.parametrize(
    ("running", "edge", "top"),
    [("Rahmenlehrplan Mechatronik {}", "page_header", 30), ("{} | Rahmenlehrplan", "page_footer", 815)],
    ids=["head", "foot"],
)
def test_a_running_title_carries_the_page_s_number_where_one_of_its_numbers_runs_with_the_page(
    running: str, edge: str, top: float
) -> None:
    pages = document(*[[block(n, running.format(n + 4), top), block(n, "Text", 300)] for n in range(1, 5)])

    printed = mark_edges(pages)

    assert printed == ("5", "6", "7", "8")
    assert kinds(pages) == [[edge, "text"]] * 4


@pytest.mark.parametrize(
    "numbers",
    [
        [n + 4 for n in range(1, 11)] + [n + 2 for n in range(11, 21)],  # a blank page taken out
        [*range(1, 11), *range(1, 11)],  # two parts, each counted from 1
    ],
    ids=["count-jumps", "two-parts"],
)
def test_a_running_title_whose_count_jumps_is_one_still(numbers: list[int]) -> None:
    pages = document(
        *[
            [block(n, f"Rahmenlehrplan Mechatronik {number}", 30), block(n, "Text", 300)]
            for n, number in enumerate(numbers, 1)
        ]
    )

    printed = mark_edges(pages)

    assert kinds(pages) == [["page_header", "text"]] * 20
    assert printed == tuple(str(number) for number in numbers)


def test_a_running_foot_naming_its_section_and_the_page_is_one() -> None:
    # "Lernfeld 2 | 5": the section's number stays over its pages, the page's runs
    sections = [1, 1, 1, 2, 2, 3, 3, 3]
    pages = document(
        *[[block(n, "Text", 300), block(n, f"Lernfeld {s} | {n}", 815)] for n, s in enumerate(sections, 1)]
    )

    printed = mark_edges(pages)

    assert kinds(pages) == [["text", "page_footer"]] * 8
    assert printed == tuple(str(n) for n in range(1, 9))


def test_a_sign_in_an_edge_s_text_and_a_number_of_many_digits_end_nothing() -> None:
    # "#" is no number; a number of thousands of digits is no int Python makes
    long = "9" * 5000
    pages = document(
        *[[block(n, f"Rahmenlehrplan {n}", 30), block(n, f"Nr. {long}{n}", 815)] for n in range(1, 4)],
        [block(4, "Rahmenlehrplan #", 30), block(4, "Text", 300)],
    )

    printed = mark_edges(pages)

    assert kinds(pages)[:3] == [["page_header", "text"]] * 3
    assert kinds(pages)[3] == ["text", "text"]
    assert printed == ("1", "2", "3", None)


def test_numbers_alone_at_the_top_that_the_foot_s_page_numbers_belie_are_chapters() -> None:
    # chapter 1 and 2 at the top of two pages in a row, the foot printing 5 and 6
    pages = document(
        [block(1, "1", 40), block(1, "Text", 300), block(1, "- 5 -", 815)],
        [block(2, "2", 40), block(2, "Text", 300), block(2, "- 6 -", 815)],
    )

    printed = mark_edges(pages)

    assert kinds(pages) == [["text", "text", "page_footer"]] * 2
    assert printed == ("5", "6")


def test_headings_numbered_on_pages_in_a_row_that_the_foot_s_numbers_belie_stay_text() -> None:
    # "Lernfeld 1" ... "Lernfeld 5" at the top of pages 6 to 10 of 20: their number runs with the
    # pages, but not as the page numbers in the foot do
    pages = document(
        *[
            [block(n, f"Lernfeld {n - 5}", 40)] * (6 <= n <= 10)
            + [block(n, "Text", 300), block(n, f"- {n} -", 815)]
            for n in range(1, 21)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "text" for page in pages[5:10])
    assert printed == tuple(str(n) for n in range(1, 21))


@pytest.mark.parametrize(
    "foot",
    [
        {7: "1 Vgl. KMK 2021, S. 40"},  # a footnote with a page reference, read as a page number
        {1: "2026"},  # a year at the foot of the cover, no page number at all
    ],
    ids=["footnote", "year"],
)
def test_one_page_whose_foot_belies_a_running_head_takes_it_from_no_other_page(foot: dict[int, str]) -> None:
    pages = document(
        *[
            [block(n, f"Rahmenlehrplan Mechatronik {n}", 30), block(n, "Text", 300)]
            + ([block(n, foot[n], 815)] if n in foot else [])
            for n in range(1, 21)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "page_header" for page in pages)
    assert [printed[n - 1] for n in range(1, 21) if n not in foot] == [
        str(n) for n in range(1, 21) if n not in foot
    ]


@pytest.mark.parametrize("variant", ["head-misprint", "foot-misprint", "foot-in-two-parts"])
def test_a_running_head_the_foot_belies_on_some_pages_runs_where_as_many_agree(variant: str) -> None:
    # page 5 prints 6 in its head, or in its foot; or the foot counts pages 6 to 10 from 1 again
    def number(n: int, edge: str) -> int:
        if variant == "foot-in-two-parts" and edge == "foot" and n > 5:
            return n - 5
        return 6 if n == 5 and variant == f"{edge}-misprint" else n

    pages = document(
        *[
            [
                block(n, f"Rahmenlehrplan Mechatronik {number(n, 'head')}", 30),
                block(n, "Text", 300),
                block(n, f"- {number(n, 'foot')} -", 815),
            ]
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "page_header" for page in pages)
    assert printed == tuple(str(number(n, "foot")) for n in range(1, 11))


def test_numbered_captions_in_the_foot_on_pages_in_pairs_stay_text_beside_its_page_numbers() -> None:
    captions = {4: 1, 5: 2, 9: 3, 10: 4}
    pages = document(
        *[
            [block(n, "Text", 300)]
            + ([block(n, f"Abbildung {captions[n]}", 790)] if n in captions else [])
            + [block(n, f"- {n} -", 815)]
            for n in range(1, 21)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[1].kind == "text" for n, page in enumerate(pages, 1) if n in captions)
    assert printed == tuple(str(n) for n in range(1, 21))


def test_a_footnote_reaching_into_the_foot_is_no_page_number_however_it_ends() -> None:
    # two lines begun in the bottom 12 %, ending with a page reference
    footnote = RawBlock(3, "text", "1 Siehe\nSeite 12", (56, 760, 400, 779.8), 9.0, False, False)
    pages = document(
        *[
            [block(n, "Text", 300), *([footnote] if n == 3 else []), block(n, f"- {n} -", 815)]
            for n in range(1, 6)
        ]
    )

    printed = mark_edges(pages)

    assert pages[2].blocks[1].kind == "text"
    assert printed == ("1", "2", "3", "4", "5")


@pytest.mark.parametrize("numbered", [True, False], ids=["foot-numbers", "no-foot-numbers"])
def test_footnotes_reaching_into_the_foot_of_two_pages_are_no_page_numbers_though_their_ends_agree(
    numbered: bool,
) -> None:
    # pages 3 and 6 end on a reference seven pages on: two pages share its offset, as page numbers do
    def footnote(n: int) -> RawBlock:
        text = f"1 Vgl. KMK, Handreichung\nzur Erarbeitung, S. {n + 7}"
        return RawBlock(n, "text", text, (56, 760, 400, 779.8), 9.0, False, False)

    pages = document(
        *[
            [block(n, f"Rahmenlehrplan Mechatronik {n}", 30), block(n, "Text", 300)]
            + [footnote(n)] * (n in (3, 6))
            + [block(n, f"- {n} -", 815)] * numbered
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert [pages[n - 1].blocks[2].kind for n in (3, 6)] == ["text", "text"]
    assert all(page.blocks[0].kind == "page_header" for page in pages)
    assert printed == tuple(str(n) for n in range(1, 11))


@pytest.mark.parametrize(
    ("text", "box", "kind"),
    [
        (
            "Rahmenlehrplan\nMechatronik\nTeil III",
            (56, 40, 400, 77.4),
            "page_header",
        ),  # three lines, 11 on 13.2
        ("Rahmenlehrplan\nMechatronik\nTeil III\nAnhang", (56, 40, 400, 90.6), "text"),  # four lines
        ("Rahmenlehrplan\nMechatronik", (56, 50, 400, 126), "text"),  # past 12 %, 101 points
        ("Rahmenlehrplan\nMechatronik", (56, 761, 400, 785), "page_footer"),  # the foot's near band
    ],
    ids=["three-lines", "four-lines", "past-the-band", "foot"],
)
def test_a_running_head_or_foot_of_a_few_lines_may_reach_a_little_past_its_edge(
    text: str, box: tuple[float, float, float, float], kind: str
) -> None:
    pages = document(
        *[[RawBlock(n, "text", text, box, 11.0, False, False), block(n, "Text", 300)] for n in range(1, 4)]
    )

    mark_edges(pages)

    assert [page.blocks[0].kind for page in pages] == [kind] * 3


def test_headings_numbered_on_pages_in_a_row_reaching_past_the_edge_stay_text() -> None:
    # "Lernfeld 1" ... "Lernfeld 5" in 14 points at 55 to 69, past the edge's 67: the band beside the
    # edge takes a running head of a few lines, not a count that runs
    pages = document(
        *[
            [RawBlock(n, "text", f"Lernfeld {n}", (56, 55, 400, 69), 14.0, True, False)] * (n <= 5)
            + [block(n, "Text", 300)]
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "text" for page in pages)
    assert printed == (None,) * 10


@pytest.mark.parametrize("variant", ["one-within-the-edge", "two-within-the-edge", "one-foot-number"])
def test_headings_numbered_in_a_row_half_past_the_edge_or_more_stay_text(variant: str) -> None:
    # "Lernfeld 1" ... "Lernfeld 4" at 60 to 72 on pages 5 to 8 of 12; on page 5, or on 5 and 6,
    # within the edge instead, or a page number in the foot of page 8 alone: none makes their count
    # a running one
    within = {"one-within-the-edge": {5}, "two-within-the-edge": {5, 6}}.get(variant, set())

    def heading(n: int) -> RawBlock:
        top = 30.0 if n in within else 60.0
        return RawBlock(n, "text", f"Lernfeld {n - 4}", (56, top, 400, top + 12), 14.0, True, False)

    pages = document(
        *[
            [heading(n)] * (5 <= n <= 8)
            + [block(n, "Text", 300)]
            + [block(n, str(n), 815)] * (variant == "one-foot-number" and n == 8)
            for n in range(1, 13)
        ]
    )

    mark_edges(pages)

    assert all(page.blocks[0].kind == "text" for page in pages[4:8])


def test_a_number_that_stays_over_stretches_beside_none_that_runs_makes_no_running_head() -> None:
    # "Kapitel 1" on pages 1 and 2, "Kapitel 2" on 3 and 4 ...: a heading kept a while, not a running head
    pages = document(*[[block(n, f"Kapitel {(n + 1) // 2}", 30), block(n, "Text", 300)] for n in range(1, 9)])

    mark_edges(pages)

    assert all(page.blocks[0].kind == "text" for page in pages)


def test_the_foot_s_page_number_goes_before_the_head_s_where_both_run() -> None:
    labels = ["i", "ii", "iii"]
    pages = document(
        *[[block(n, str(n), 30), block(n, "Text", 300), block(n, labels[n - 1], 815)] for n in range(1, 4)]
    )

    assert mark_edges(pages) == ("i", "ii", "iii")


def test_a_running_head_agrees_with_the_first_page_number_of_its_foot() -> None:
    # each foot prints the page and, below it, the page counted from the cover: the head goes by the first
    pages = document(
        *[
            [
                block(n, f"Rahmenlehrplan Mechatronik {n}", 30),
                block(n, "Text", 300),
                block(n, f"- {n} -", 800),
                block(n, str(n + 2), 815),
            ]
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "page_header" for page in pages)
    assert printed == tuple(str(n) for n in range(1, 11))


def test_a_number_counts_each_page_once_however_often_its_block_stands_there() -> None:
    # "Rahmenlehrplan 1" twice on page 1: one page whose offset no other shares, so nothing runs
    pages = document(
        [block(1, "Rahmenlehrplan 1", 20), block(1, "Rahmenlehrplan 1", 40)],
        [block(2, "Rahmenlehrplan 4", 30)],
        [block(3, "Rahmenlehrplan 5", 30)],
    )

    mark_edges(pages)

    assert kinds(pages) == [["text", "text"], ["text"], ["text"]]


def test_a_running_head_of_two_lines_reaching_a_little_past_the_edge_is_one() -> None:
    # the edge is 67 points of 842; two lines of 11 points begun at 45 end at 69
    pages = document(
        *[
            [
                RawBlock(n, "text", "Rahmenlehrplan\nMechatronik", (56, 45, 400, 69), 11.0, False, False),
                block(n, "Text", 300),
            ]
            for n in range(1, 4)
        ]
    )

    mark_edges(pages)

    assert kinds(pages) == [["page_header", "text"]] * 3


def test_a_year_alone_at_the_foot_of_a_cover_is_no_page_number() -> None:
    pages = document([block(1, "Rahmenlehrplan", 300), block(1, "2026", 815)], [block(2, "Text", 300)])

    printed = mark_edges(pages)

    assert printed == (None, None)
    assert kinds(pages) == [["text", "text"], ["text"]]


def test_in_one_edge_the_number_alone_goes_before_the_running_one() -> None:
    # both count the page alike; the foot prints it in Roman numerals alone
    labels = ["i", "ii", "iii"]
    pages = document(
        *[
            [block(n, "Text", 300), block(n, f"Rahmenlehrplan {n}", 790), block(n, labels[n - 1], 815)]
            for n in range(1, 4)
        ]
    )

    assert mark_edges(pages) == ("i", "ii", "iii")
    assert kinds(pages) == [["text", "page_footer", "page_footer"]] * 3


@pytest.mark.parametrize(
    ("head", "top", "bottom", "numbered"),
    [
        ("Rahmenlehrplan Mechatronik\nSeite {n} von 10", 45, 69, True),  # two lines, past the edge
        ("Rahmenlehrplan Mechatronik\nSeite {n} von 10", 45, 69, False),  # a page number alone, unfooted
        ("Rahmenlehrplan\nMechatronik {n}", 45, 69, True),  # running with the foot's page numbers
        ("Rahmenlehrplan Mechatronik {n}", 30, 40, True),  # within the edge, but on page 4 lower
        ("Rahmenlehrplan Mechatronik {n}", 30, 40, False),  # one of ten past the edge: no count of headings
    ],
    ids=[
        "two-lines-with-a-number",
        "two-lines-unfooted",
        "two-lines-running",
        "one-page-lower",
        "one-unfooted",
    ],
)
def test_a_running_head_with_its_page_number_reaching_into_the_band_beside_the_edge_runs(
    head: str, top: float, bottom: float, numbered: bool
) -> None:
    def placed(n: int) -> tuple[float, float, float, float]:
        lower = 30.0 if n == 4 and top == 30 else 0.0  # 30 + 30 points: into the band
        return (56, top + lower, 400, bottom + lower)

    pages = document(
        *[
            [
                RawBlock(n, "text", head.format(n=n), placed(n), 11.0, False, False),
                block(n, "Text", 300),
                *[block(n, f"- {n} -", 815)] * numbered,
            ]
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "page_header" for page in pages)
    assert printed == tuple(str(n) for n in range(1, 11))


def test_a_page_number_alone_just_above_the_foot_s_edge_is_one_where_it_runs_with_the_pages() -> None:
    # "- 5 -" at 770 to 780: the foot's edge begins at 775
    pages = document(
        *[
            [block(n, "Text", 300), RawBlock(n, "text", f"- {n} -", (280, 770, 320, 780), 9.0, False, False)]
            for n in range(1, 6)
        ]
    )

    printed = mark_edges(pages)

    assert kinds(pages) == [["text", "page_footer"]] * 5
    assert printed == ("1", "2", "3", "4", "5")


@pytest.mark.parametrize("footed", [(7, 8), (8, 9)], ids=["two-belie", "one-belies"])
def test_headings_numbered_in_a_row_stay_text_where_the_foot_s_running_numbers_belie_some(
    footed: tuple[int, int],
) -> None:
    # "Lernfeld 1" ... "Lernfeld 4" at the top of pages 5 to 8; only two pages print their number,
    # both of them among the headings' or one
    pages = document(
        *[
            [block(n, f"Lernfeld {n - 4}", 40)] * (5 <= n <= 8)
            + [block(n, "Text", 300)]
            + [block(n, f"- {n} -", 815)] * (n in footed)
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "text" for page in pages[4:8])
    assert printed[4:8] == tuple(str(n) if n in footed else None for n in range(5, 9))


def test_a_year_alone_in_every_foot_takes_nothing_from_a_running_head() -> None:
    pages = document(
        *[
            [block(n, f"Rahmenlehrplan Mechatronik {n}", 30), block(n, "Text", 300), block(n, "2026", 815)]
            for n in range(1, 11)
        ]
    )

    printed = mark_edges(pages)

    assert all(page.blocks[0].kind == "page_header" for page in pages)
    assert printed == tuple(str(n) for n in range(1, 11))


@pytest.mark.parametrize(("footnoted", "runs"), [(5, True), (6, False)])
def test_a_running_head_goes_on_where_half_its_pages_agree_with_the_foot(footnoted: int, runs: bool) -> None:
    # a footnote taken for a page number on the first pages: each says another, and none agrees
    pages = document(
        *[
            [block(n, f"Rahmenlehrplan Mechatronik {n}", 30), block(n, "Text", 300)]
            + ([block(n, "1 Vgl. KMK 2021, S. 40", 815)] if n <= footnoted else [])
            for n in range(1, 11)
        ]
    )

    mark_edges(pages)

    assert all((page.blocks[0].kind == "page_header") is runs for page in pages)


def test_a_line_twice_at_the_top_of_one_page_counts_one_page() -> None:
    # of 4 pages, 3 are needed: twice on page 1 and once on page 2 is on two pages
    pages = document(
        [block(1, "Rahmenlehrplan", 20), block(1, "Rahmenlehrplan", 40)],
        [block(2, "Rahmenlehrplan", 30)],
        [block(3, "Text", 300)],
        [block(4, "Text", 300)],
    )

    mark_edges(pages)

    assert kinds(pages)[:2] == [["text", "text"], ["text"]]


def test_a_page_number_alone_in_the_foot_goes_before_the_running_title_s() -> None:
    pages = document(
        *[
            [block(n, f"Rahmenlehrplan {n + 4}", 30), block(n, "Text", 300), block(n, f"- {n} -", 815)]
            for n in range(1, 4)
        ]
    )

    assert mark_edges(pages) == ("1", "2", "3")


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
    conversion = engine("pdfplumber").convert(FIXTURES / "edges.pdf", pages=5)

    assert conversion.printed_pages == ("I", "II", "1", "2", "3")
    assert [block.kind for block in conversion.blocks if block.page == 1] == [
        "page_header",
        "text",
        "page_footer",
    ]
