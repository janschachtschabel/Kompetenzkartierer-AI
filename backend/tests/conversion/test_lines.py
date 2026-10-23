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


@pytest.mark.parametrize(
    ("font", "size"),
    [("Helvetica-Bold", SIZE), ("Helvetica-Oblique", SIZE), ("Helvetica", 14.0)],
    ids=["bold", "italic", "larger"],
)
def test_a_line_set_otherwise_begins_a_block_of_its_own(font: str, size: float) -> None:
    words = [
        *row("1 Lernfeld Technik", 100, size=size, font=font),
        *row("Die Lernenden planen.", 100 + 14 + 3),
    ]

    blocks = blocks_of(words, page=1)

    assert [block.text for block in blocks] == ["1 Lernfeld Technik", "Die Lernenden planen."]
    assert (blocks[0].bold, blocks[0].italic, blocks[0].font_size) == (
        font == "Helvetica-Bold",
        font == "Helvetica-Oblique",
        size,
    )


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
