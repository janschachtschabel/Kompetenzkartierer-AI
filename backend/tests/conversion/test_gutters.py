"""The gutters of a page: where its lines part into columns (plan M1, 3.2), on made-up words."""

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
