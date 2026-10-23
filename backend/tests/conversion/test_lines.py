"""Words into lines, lines into blocks: runs of text set alike (plan M1, 3.2), on made-up words."""

import pytest

from app.conversion.layout import Word, style_of
from app.conversion.lines import blocks_of, lines_of

SIZE = 11.0


def word(text: str, x0: float, top: float, size: float = SIZE, font: str = "Helvetica") -> Word:
    return Word(
        text=text, x0=x0, x1=x0 + len(text) * size * 0.5, top=top, bottom=top + size, size=size, font=font
    )


def row(
    text: str, top: float, x0: float = 56.0, *, size: float = SIZE, font: str = "Helvetica"
) -> list[Word]:
    """A line of words a space apart, from ``x0``."""
    made: list[Word] = []
    for piece in text.split():
        made.append(word(piece, x0, top, size, font))
        x0 = made[-1].x1 + SIZE * 0.3
    return made


@pytest.mark.parametrize(
    ("font", "bold", "italic"),
    [
        ("Helvetica", False, False),
        ("Helvetica-Bold", True, False),
        ("Helvetica-Oblique", False, True),
        ("ABCDEF+Arial-BoldItalicMT", True, True),
        ("Arial,Bold", True, False),
        ("SourceSansPro-Semibold", True, False),
        ("MinionPro-It", False, True),
        ("MyriadPro-BoldIt", True, True),
        ("TimesNewRomanPS-ItalicMT", False, True),
        ("Calibri", False, False),
        ("Arial-Black", True, False),
        # Adobe's short style names, alone and combined
        ("HelveticaNeueLTStd-Bd", True, False),
        ("HelveticaNeueLTStd-BdIt", True, True),
        ("HelveticaNeueLTStd-BdCn", True, False),
        ("HelveticaNeueLTStd-Blk", True, False),
        ("HelveticaNeueLTStd-Hv", True, False),
        ("MyriadPro-SbIt", True, True),
        ("FuturaStd-Smbd", True, False),
        ("FrutigerLTStd-Obl", False, True),
        ("HelveticaNeueLTStd-LtIt", False, True),
        ("HelveticaNeueLTStd-Md", False, False),
        ("HelveticaNeueLTStd-Lt", False, False),
        # the family's name says nothing where a style follows it
        ("Academica-Regular", False, False),
        ("Blackletter-Regular", False, False),
        ("ABCDEF+Academica-Italic", False, True),
        # and all where none does
        ("ArialBold", True, False),
        ("Arial,BoldItalic", True, True),
    ],
)
def test_bold_and_italic_are_read_off_the_font_s_name(font: str, bold: bool, italic: bool) -> None:
    assert style_of(font) == (bold, italic)


def test_words_on_one_height_are_one_line_left_to_right() -> None:
    words = [word("Funktion", 120, 100), word("Die", 56, 100), word("ihrer", 90, 100.4)]

    (line,) = lines_of(words)

    assert line.text == "Die ihrer Funktion"


def test_a_word_overlapping_a_line_by_half_the_smaller_height_stands_on_it() -> None:
    # the line's span is that of its largest word, 100 to 111: a word of 6 points stands on it with
    # 3 points of its height within that span, and on a line of its own with less
    on_it, below = word("Bezug", 165, 106, size=6), word("Fußnote", 300, 108.5, size=6)

    lines = lines_of([*row("Die Lernenden planen", 100), on_it, below])

    assert [line.text for line in lines] == ["Die Lernenden planen Bezug", "Fußnote"]


def test_lines_set_solid_or_tighter_stay_two() -> None:
    words = [*row("Erste Zeile", 100), *row("Zweite Zeile", 111), *row("Dritte Zeile", 119)]

    assert [line.text for line in lines_of(words)] == ["Erste Zeile", "Zweite Zeile", "Dritte Zeile"]


def test_scripts_stand_on_their_line_and_touch_their_word() -> None:
    # as reportlab sets them at 11 points: a superscript 9 points high, 4 above the line, a
    # subscript 7 below it - overlapping the line by less than half its height, glued to its word
    words = [
        Word("Die", 62.69, 79.19, 79.14, 90.14, 11.0, "Helvetica"),
        Word("Schüler", 82.25, 119.54, 79.14, 90.14, 11.0, "Helvetica"),
        Word("1", 119.54, 124.54, 75.23, 84.23, 9.0, "Helvetica"),
        Word("messen", 127.60, 166.11, 79.14, 90.14, 11.0, "Helvetica"),
        Word("CO", 169.17, 185.67, 79.14, 90.14, 11.0, "Helvetica"),
        Word("2", 185.67, 190.68, 86.23, 95.23, 9.0, "Helvetica"),
        Word("Das", 62.69, 82.25, 93.14, 104.14, 11.0, "Helvetica"),
    ]

    first, second = lines_of(words)

    assert (first.text, second.text) == ("Die Schüler1 messen CO2", "Das")
    assert first.size == 11.0


def test_words_a_change_of_font_parts_are_one_where_they_touch() -> None:
    words = [word("Das", 56, 100), word("Lern", 77, 100), word("feld", 99, 100, font="Helvetica-Bold")]

    (line,) = lines_of(words)

    assert line.text == "Das Lernfeld"


def test_a_line_s_size_is_that_of_most_of_its_signs() -> None:
    words = [word("1", 50, 98, size=9), word("Lernfeldern", 56, 100), word("2", 120, 98, size=9)]

    (line,) = lines_of(words)

    assert line.size == 11.0


def two_columns(top: float) -> list[Word]:
    """A line of two columns of 10 points, 12 points apart: "links Spalte", "rechts Spalte"."""
    return [
        word("links", 56, top, size=10),
        word("Spalte", 84, top, size=10),
        word("rechts", 126, top, size=10),
        word("Spalte", 159, top, size=10),
    ]


def test_a_gutter_three_lines_share_parts_them_however_narrow() -> None:
    words = [*two_columns(100), *two_columns(113), *two_columns(126)]

    assert [line.text for line in lines_of(words)] == ["links Spalte", "rechts Spalte"] * 3


def test_a_gap_that_wanders_from_line_to_line_is_no_gutter() -> None:
    # justified text, spaces as wide as a gutter: what follows them begins somewhere else in each line
    words: list[Word] = []
    for line in range(3):
        top = 100 + 13 * line
        words += [word("links", 56, top, size=10), word("weiter", 92 + 4 * line, top, size=10)]

    assert [line.text for line in lines_of(words)] == ["links weiter"] * 3


def test_a_gap_two_lines_share_parts_neither() -> None:
    words = [*two_columns(100), *two_columns(113)]

    assert [line.text for line in lines_of(words)] == ["links Spalte rechts Spalte"] * 2


JUSTIFIED = ["Die", "Lernenden", "planen", "ihre", "Arbeit", "sorgfältig", "und", "genau"]


def justified(top: float, wide_after: int | None) -> list[Word]:
    """A line of justified text at 10 points, its words 3 points apart, 9 behind one of them."""
    made: list[Word] = []
    x0 = 56.0
    for index, text in enumerate(JUSTIFIED):
        made.append(word(text, x0, top, size=10))
        x0 = made[-1].x1 + (9 if index == wide_after else 3)
    return made


def test_wide_gaps_justified_text_scatters_over_its_lines_part_none() -> None:
    # one beneath another in two lines, or four lines apart: no gutter
    wide_after = [2, 2, None, None, 5, 5, None, 2]
    words = [word for line, wide in enumerate(wide_after) for word in justified(100 + 13 * line, wide)]

    assert [line.text for line in lines_of(words)] == [" ".join(JUSTIFIED)] * len(wide_after)


def test_a_wide_gap_parts_a_line_into_two() -> None:
    # two columns, or a note beside the text: no line runs across the gutter
    words = [*row("linke Spalte", 100), *row("rechte Spalte", 100, x0=320)]

    assert [line.text for line in lines_of(words)] == ["linke Spalte", "rechte Spalte"]


def test_lines_close_below_one_another_and_set_alike_are_one_block() -> None:
    words = [*row("Die Schülerinnen und Schüler", 100), *row("analysieren den Aufbau.", 114)]

    (block,) = blocks_of(words, page=2)

    assert block.text == "Die Schülerinnen und Schüler\nanalysieren den Aufbau."
    assert (block.page, block.kind, block.font_size, block.bold, block.italic) == (
        2,
        "text",
        11.0,
        False,
        False,
    )
    assert block.bbox[1] == 100 and block.bbox[3] == 114 + SIZE


def test_a_gap_of_half_a_line_parts_two_paragraphs() -> None:
    # 3 points between the lines of a paragraph, 6 and more between paragraphs
    words = [*row("Erster Absatz.", 100), *row("Zweiter Absatz.", 100 + SIZE + 6)]

    assert [block.text for block in blocks_of(words, page=1)] == ["Erster Absatz.", "Zweiter Absatz."]


def test_a_line_half_its_size_below_the_last_goes_on_its_block() -> None:
    words = [*row("Erster Absatz,", 100), *row("noch derselbe.", 100 + SIZE + 0.5 * SIZE)]

    assert [block.text for block in blocks_of(words, page=1)] == ["Erster Absatz,\nnoch derselbe."]


def test_a_line_set_into_the_one_above_by_more_than_half_its_size_is_a_block_of_its_own() -> None:
    # "Drüber" reaches 7 points up into the line "Erste Zeile" (its last word lower): text set
    # over text, not the next line
    words = [word("Erste", 56, 100), word("Zeile", 87, 104), word("Drüber", 56, 108)]

    assert [block.text for block in blocks_of(words, page=1)] == ["Erste Zeile", "Drüber"]


@pytest.mark.parametrize(
    ("size", "blocks"),
    [(SIZE + 0.5, 1), (SIZE - 0.5, 1), (SIZE + 1, 2), (SIZE - 1, 2)],
    ids=["half_larger", "half_smaller", "point_larger", "point_smaller"],
)
def test_sizes_half_a_point_apart_are_one_and_a_point_apart_two(size: float, blocks: int) -> None:
    # a line's size is read to half a point: 11.6 points are 11.5
    words = [*row("Erste Zeile", 100), *row("zweite Zeile", 100 + SIZE + 3, size=size)]

    assert len(blocks_of(words, page=1)) == blocks


@pytest.mark.parametrize(
    ("font", "size"),
    [("Helvetica-Bold", SIZE), ("Helvetica-Oblique", SIZE), ("Helvetica", 14.0)],
    ids=["bold", "italic", "larger"],
)
def test_a_line_set_otherwise_begins_a_block_of_its_own(font: str, size: float) -> None:
    # 3 points below: as close as the lines of a paragraph
    words = [
        *row("1 Lernfeld Technik", 100, size=size, font=font),
        *row("Die Lernenden planen.", 100 + size + 3),
    ]

    blocks = blocks_of(words, page=1)

    assert [block.text for block in blocks] == ["1 Lernfeld Technik", "Die Lernenden planen."]
    assert (blocks[0].bold, blocks[0].italic, blocks[0].font_size) == (
        font == "Helvetica-Bold",
        font == "Helvetica-Oblique",
        size,
    )


def test_a_block_s_size_is_that_of_most_of_its_signs_not_of_its_first_line() -> None:
    # sizes half a point apart are one block; the short first line is set smaller
    words = [
        *row("Kurz", 100, size=10.5),
        *row("die Lernenden planen ihre Arbeit", 113),
        *row("und prüfen sie.", 127),
    ]

    (block,) = blocks_of(words, page=1)

    assert block.font_size == SIZE


def test_a_line_bold_in_part_is_not_bold() -> None:
    words = [word("Hinweis:", 56, 100, font="Helvetica-Bold"), *row("die Inhalte gelten.", 100, x0=110)]

    (block,) = blocks_of(words, page=1)

    assert not block.bold


def test_columns_stay_blocks_of_their_own() -> None:
    words = [
        *row("links eins", 100),
        *row("rechts eins", 100, x0=320),
        *row("links zwei", 114),
        *row("rechts zwei", 114, x0=320),
    ]

    texts = sorted(block.text for block in blocks_of(words, page=1))

    assert texts == ["links eins\nlinks zwei", "rechts eins\nrechts zwei"]


def test_no_words_are_no_blocks() -> None:
    assert blocks_of([], page=1) == []
