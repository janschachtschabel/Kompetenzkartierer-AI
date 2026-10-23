"""Words into lines, lines into blocks: runs of text set alike (plan M1, 3.2).

A line is the words at one height, left to right. A word stands on the line whose span - that of
its largest word, so a superscript does not lift it - it overlaps most, by half the smaller height
at least; a sub- or superscript glued to a word of the line stands on it where it overlaps it at
all (reportlab lowers a subscript by half a line). Two words a gap narrower than a tenth of their
size apart are one: pdfplumber parts a word where its font or size changes ("Lern" "feld", "CO"
"2"). A line's size is that of most of its signs. A wide gap parts a line, so no line runs across
the gutter between two columns or into a note beside the text. A block is the lines below one
another, close, overlapping across and set alike - the same size, bold and italic. A heading
begins a block of its own however close the text below it stands, and a paragraph does where the
space above it is half a line or more: the lines of a paragraph stand 3 points apart at 11
points, paragraphs 6 and more (the fixtures, and what Lehrpläne set). The lines of a block keep
their breaks: its text is the document's wording, line by line.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from itertools import accumulate, pairwise

from app.conversion.layout import RawBlock, Word, style_of

LINE_TOLERANCE = 0.5  # times the size: a line this far up into the one above still goes below it
LINE_OVERLAP = 0.5  # of the smaller height: a word overlapping a line's span this much stands on it
WORD_SPACE = 0.1  # times the larger size: two words a narrower gap apart are one
COLUMN_GAP = 3.0  # times the size: a wider gap between two words parts a line
BLOCK_GAP = 0.5  # times the size: a line this close below another, set alike, goes on its block
SIZE_TOLERANCE = 0.5  # points: sizes this close are one


@dataclass(frozen=True)
class Line:
    """A line's words; what follows of them is reckoned once, since a page's blocks ask it often."""

    words: tuple[Word, ...]  # left to right

    @cached_property
    def text(self) -> str:
        parts = [self.words[0].text]
        for before, word in pairwise(self.words):
            if _apart(before, word):
                parts.append(" ")
            parts.append(word.text)
        return "".join(parts)

    @cached_property
    def x0(self) -> float:
        return min(word.x0 for word in self.words)

    @cached_property
    def x1(self) -> float:
        return max(word.x1 for word in self.words)

    @cached_property
    def top(self) -> float:
        return min(word.top for word in self.words)

    @cached_property
    def bottom(self) -> float:
        return max(word.bottom for word in self.words)

    @cached_property
    def size(self) -> float:
        """The size most of its signs are set in, to half a point: a superscript is one sign."""
        signs: Counter[float] = Counter()
        for word in self.words:
            signs[round(word.size * 2) / 2] += len(word.text)
        return signs.most_common(1)[0][0]

    @cached_property
    def style(self) -> tuple[bool, bool]:
        """Bold and italic where every word is: a bold lead-in does not make the line bold."""
        styles = [style_of(word.font) for word in self.words]
        return all(bold for bold, _ in styles), all(italic for _, italic in styles)


@dataclass
class _Row:
    """The words of a line while they are found, and its span: that of its largest word."""

    words: list[Word]
    top: float
    bottom: float
    size: float

    def add(self, word: Word) -> None:
        self.words.append(word)
        if word.size > self.size:
            self.top, self.bottom, self.size = word.top, word.bottom, word.size

    def overlap(self, word: Word) -> float:
        return min(self.bottom, word.bottom) - max(self.top, word.top)

    def holds(self, word: Word) -> bool:
        overlap = self.overlap(word)
        if overlap <= 0:
            return False
        least = LINE_OVERLAP * min(self.bottom - self.top, word.bottom - word.top)
        return overlap >= least or any(_glued(word, other) for other in self.words)


def lines_of(words: Iterable[Word]) -> list[Line]:
    """The lines of these words, top to bottom and, at one height, left to right."""
    rows: list[_Row] = []
    open_rows: list[_Row] = []  # those a word further down may still overlap
    for word in sorted(words, key=lambda word: (word.top, word.x0)):
        open_rows = [row for row in open_rows if row.bottom > word.top]
        holding = [row for row in open_rows if row.holds(word)]
        if holding:
            max(holding, key=lambda row: row.overlap(word)).add(word)
        else:
            rows.append(_Row([word], word.top, word.bottom, word.size))
            open_rows.append(rows[-1])
    lines: list[Line] = []
    for found in rows:
        part: list[Word] = []
        for word in sorted(found.words, key=lambda word: word.x0):
            if part and word.x0 - part[-1].x1 > COLUMN_GAP * max(word.size, part[-1].size):
                lines.append(Line(tuple(part)))
                part = []
            part.append(word)
        lines.append(Line(tuple(part)))
    return lines


def _apart(before: Word, word: Word) -> bool:
    """Whether a space parts two words side by side: their gap is a tenth of their size or more."""
    return word.x0 - before.x1 >= WORD_SPACE * max(before.size, word.size)


def _glued(word: Word, other: Word) -> bool:
    """Whether the words touch side by side, on either side: a sub- or superscript and its word,
    not two words one above the other, which overlap across."""
    gap = max(other.x0 - word.x1, word.x0 - other.x1)
    return abs(gap) < WORD_SPACE * max(word.size, other.size)


def blocks_of(words: Iterable[Word], page: int) -> list[RawBlock]:
    """The text blocks of a page's words, in the order their first lines come. A block whose last
    line ends further above every line still to come than a line may stand below it is closed: no
    line is matched against the many blocks of a long page."""
    lines = lines_of(words)
    # the highest top of each line and those after it
    highest = list(accumulate((line.top for line in reversed(lines)), min))[::-1]
    blocks: list[list[Line]] = []
    open_blocks: list[list[Line]] = []
    for line, top in zip(lines, highest, strict=True):
        open_blocks = [block for block in open_blocks if _reach(block[-1]) >= top]
        target = next((block for block in reversed(open_blocks) if _goes_on(block[-1], line)), None)
        if target is None:
            blocks.append([line])
            open_blocks.append(blocks[-1])
        else:
            target.append(line)
    return [_raw(block, page) for block in blocks]


def _reach(last: Line) -> float:
    """How far down a line may begin and still go on the block that ``last`` ends (_goes_on)."""
    return last.bottom + BLOCK_GAP * (last.size + SIZE_TOLERANCE)


def _goes_on(last: Line, line: Line) -> bool:
    """Whether ``line`` continues the block that ``last`` ends."""
    size = max(line.size, last.size)
    gap = line.top - last.bottom
    return (
        -LINE_TOLERANCE * size < gap <= BLOCK_GAP * size
        and abs(line.size - last.size) <= SIZE_TOLERANCE
        and line.style == last.style
        and line.x0 < last.x1
        and line.x1 > last.x0
    )


def _raw(lines: list[Line], page: int) -> RawBlock:
    bold, italic = lines[0].style
    return RawBlock(
        page=page,
        kind="text",
        text="\n".join(line.text for line in lines),
        bbox=(
            min(line.x0 for line in lines),
            min(line.top for line in lines),
            max(line.x1 for line in lines),
            max(line.bottom for line in lines),
        ),
        font_size=lines[0].size,
        bold=bold,
        italic=italic,
    )
