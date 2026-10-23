"""The gutters of a page: where its lines part into columns (plan M1, 3.2), on made-up words."""

import statistics

import pytest

from app.conversion.gutters import _median_without
from app.conversion.layout import Word
from app.conversion.lines import blocks_of, lines_of

SIZE = 11.0


def words_at(top: float, *placed: tuple[float, str]) -> list[Word]:
    """The words of ``placed``, each part a run of words a space apart from its x0, at ``top``."""
    made: list[Word] = []
    for x0, text in placed:
        for piece in text.split():
            made.append(Word(piece, x0, x0 + len(piece) * SIZE * 0.5, top, top + SIZE, SIZE, "Helvetica"))
            x0 = made[-1].x1 + SIZE * 0.3
    return made


LEFT, RIGHT = "die Lernenden planen ihre Arbeit", "und prüfen sie sorgfältig"


def two_columns(top: float, right: float = 236, text: str = RIGHT) -> list[Word]:
    """A line of two columns: the left one's words from 56 to 223.2, the right one's from ``right``."""
    return words_at(top, (56, LEFT), (right, text))


def test_a_gutter_the_page_has_parts_its_lines_however_their_columns_begin() -> None:
    # three lines confirm the gutter, 12.8 points wide; a right column's first line indented by 12
    # and a column of one line below a paragraph across both part where they cross it
    words = [
        *two_columns(100),
        *two_columns(114),
        *two_columns(128),
        *two_columns(142, right=248),
        *two_columns(156, text="Ende."),
        *words_at(200, (56, "Ein Absatz über die ganze Breite, ohne Lücke in der Mitte.")),
        *two_columns(244, right=248),
    ]

    texts = [line.text for line in lines_of(words)]

    assert texts == [
        *[LEFT, RIGHT] * 4,
        LEFT,
        "Ende.",
        "Ein Absatz über die ganze Breite, ohne Lücke in der Mitte.",
        LEFT,
        RIGHT,
    ]


def test_justified_text_across_the_page_below_two_columns_keeps_its_lines() -> None:
    # three lines of two columns, a heading, then lines across the page, their spaces 9 points
    # wide each and 5 points further on in each line: one in each lies in the gutter's strip too
    across = [
        word
        for line in range(4)
        for word in words_at(170 + 14 * line, *((56 + 5 * line + 42 * n, "Kompet") for n in range(10)))
    ]
    words = [
        *two_columns(100),
        *two_columns(114),
        *two_columns(128),
        *words_at(150, (56, "Abschnitt 2")),
        *across,
    ]

    texts = [line.text for line in lines_of(words)]

    assert texts[:7] == [LEFT, RIGHT, LEFT, RIGHT, LEFT, RIGHT, "Abschnitt 2"]
    assert texts[7:] == [" ".join(["Kompet"] * 10)] * 4


def far_below_columns() -> list[Word]:
    """Three lines of two columns, a heading and three lines across the page: a line at 210 below
    them stands past the lines that would confirm a gutter of its own."""
    across = "Ein Absatz über die ganze Breite der Seite"
    return [
        *two_columns(100),
        *two_columns(114),
        *two_columns(128),
        *words_at(150, (56, "Abschnitt 2")),
        *[word for top in (164, 178, 192) for word in words_at(top, (56, across))],
    ]


def spaced(top: float, widths: list[float], spaces: list[float]) -> list[Word]:
    """Words "w0", "w1" ... as wide as ``widths`` from 56 on, each the next of ``spaces`` apart."""
    made: list[Word] = []
    x0 = 56.0
    for n, width in enumerate(widths):
        made.append(Word(f"w{n}", x0, x0 + width, top, top + SIZE, SIZE, "Helvetica"))
        x0 = made[-1].x1 + (spaces[n] if n < len(spaces) else 0)
    return made


def test_far_below_its_columns_a_gutter_parts_a_line_where_its_gap_is_twice_its_other_spaces() -> None:
    # a gap of 10 crossing the gutter beside spaces of 5 - twice as wide - parts the line; one of 9
    # - 1.8 times - does not
    def line(gap: float) -> list[Word]:
        return spaced(210, [44, 46, 46, 21, 45, 46], [5, 5, 5, gap, 5])

    parted = [found.text for found in lines_of([*far_below_columns(), *line(10)])]
    kept = [found.text for found in lines_of([*far_below_columns(), *line(9)])]

    assert parted[-2:] == ["w0 w1 w2 w3", "w4 w5"]
    assert kept[-1] == "w0 w1 w2 w3 w4 w5"


@pytest.mark.parametrize(
    ("widths", "spaces", "texts"),
    [([120, 44, 45], [5, 10], ["w0 w1", "w2"]), ([169, 45], [10], ["w0 w1"])],
    ids=["three-words", "two-words"],
)
def test_far_below_its_columns_a_short_line_weighs_its_gap_against_its_other_spaces_alone(
    widths: list[float], spaces: list[float], texts: list[str]
) -> None:
    # three words: the gap of 10 crossing the gutter is twice the other space; two: there is none
    # to weigh it against, and the line stays whole
    found = [line.text for line in lines_of([*far_below_columns(), *spaced(210, widths, spaces)])]

    assert found[-len(texts) :] == texts


@pytest.mark.parametrize(
    "spaces",
    [
        [3.3, 3.3, 3.3],
        [1.0, 2.0, 3.0, 4.0],
        [10.0, 1.0, 4.0, 2.0, 3.0],
        [4.0, 4.0, 1.0, 9.0, 4.0, 2.0],
        [0.0, -0.5, 2.0],
        [5.0, 2.0],
    ],
)
def test_a_row_s_other_spaces_have_the_median_of_its_spaces_but_the_one(spaces: list[float]) -> None:
    ordered = sorted(spaces)

    for at, value in enumerate(spaces):
        assert _median_without(ordered, value) == statistics.median(spaces[:at] + spaces[at + 1 :])


def test_a_gutter_is_confirmed_by_lines_three_above_and_below() -> None:
    # the gap at lines 1, 4 and 7 of seven: each of the outer ones three lines from the middle one
    words = [
        word
        for line in range(7)
        for word in (two_columns(100 + 14 * line) if line % 3 == 0 else words_at(100 + 14 * line, (56, LEFT)))
    ]

    texts = [line.text for line in lines_of(words)]

    assert texts == [LEFT, RIGHT, LEFT, LEFT, LEFT, RIGHT, LEFT, LEFT, LEFT, RIGHT]


def test_a_note_of_two_lines_three_and_a_half_sizes_beside_the_text_is_a_line_of_its_own() -> None:
    # two lines share no gutter; their gap parts them as it is
    beside = 223.2 + 3.5 * SIZE
    words = [
        *words_at(100, (56, LEFT), (beside, "Hinweis am Rand")),
        *words_at(114, (56, LEFT), (beside, "zur Arbeit")),
        *words_at(128, (56, LEFT)),
    ]

    assert [line.text for line in lines_of(words)] == [LEFT, "Hinweis am Rand", LEFT, "zur Arbeit", LEFT]


def test_the_marks_of_a_list_with_a_hanging_indent_stay_before_their_text() -> None:
    # the marks at 56, each item's text and its second line at 74: the text begins at one place
    words = [
        *words_at(100, (56, "•"), (74, "beschreiben den Aufbau,")),
        *words_at(114, (56, "•"), (74, "erklären die Funktion ihrer")),
        *words_at(128, (74, "Baugruppen und wählen Messmittel,")),
        *words_at(142, (56, "•"), (74, "bewerten die Lösungen,")),
        *words_at(156, (56, "•"), (74, "präsentieren sie.")),
    ]

    (block,) = blocks_of(words, page=1)

    assert block.text.split("\n") == [
        "• beschreiben den Aufbau,",
        "• erklären die Funktion ihrer",
        "Baugruppen und wählen Messmittel,",
        "• bewerten die Lösungen,",
        "• präsentieren sie.",
    ]


def test_the_numbers_of_a_list_without_space_between_its_items_stay_before_their_text() -> None:
    items = [
        "beschreiben den Aufbau,",
        "erklären die Funktion,",
        "bewerten die Lösungen,",
        "präsentieren sie.",
    ]
    words = [
        word for n, text in enumerate(items, 1) for word in words_at(100 + 14 * n, (56, f"{n}."), (78, text))
    ]

    (block,) = blocks_of(words, page=1)

    assert block.text.split("\n") == [f"{n}. {text}" for n, text in enumerate(items, 1)]


def test_a_table_of_contents_keeps_each_number_before_its_title() -> None:
    entries = [
        ("1", "Einleitung", "3"),
        ("2", "Kompetenzen", "5"),
        ("2.1", "Fachkompetenz", "6"),
        ("3", "Anhang", "40"),
    ]
    words = [
        word
        for n, (number, title, page) in enumerate(entries)
        for word in words_at(100 + 16 * n, (56, number), (90, title), (530, page))
    ]

    texts = [line.text for line in lines_of(words)]

    assert texts == [part for number, title, page in entries for part in (f"{number} {title}", page)]
