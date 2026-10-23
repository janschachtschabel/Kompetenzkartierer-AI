"""Words into lines, lines into blocks: runs of text set alike (plan M1, 3.2).

A line is the words at one height, left to right; a wide gap parts it, so no line runs across
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

from app.conversion.layout import RawBlock, Word, style_of

LINE_TOLERANCE = 0.5  # times the size: words this close in height stand on one line
COLUMN_GAP = 3.0  # times the size: a wider gap between two words parts a line
BLOCK_GAP = 0.5  # times the size: a line this close below another, set alike, goes on its block
SIZE_TOLERANCE = 0.5  # points: sizes this close are one


@dataclass(frozen=True)
class Line:
    words: tuple[Word, ...]  # left to right

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def x0(self) -> float:
        return min(word.x0 for word in self.words)

    @property
    def x1(self) -> float:
        return max(word.x1 for word in self.words)

    @property
    def top(self) -> float:
        return min(word.top for word in self.words)

    @property
    def bottom(self) -> float:
        return max(word.bottom for word in self.words)

    @property
    def size(self) -> float:
        """The size most of its words are set in, to half a point."""
        return Counter(round(word.size * 2) / 2 for word in self.words).most_common(1)[0][0]

    @property
    def style(self) -> tuple[bool, bool]:
        """Bold and italic where every word is: a bold lead-in does not make the line bold."""
        styles = [style_of(word.font) for word in self.words]
        return all(bold for bold, _ in styles), all(italic for _, italic in styles)


def lines_of(words: Iterable[Word]) -> list[Line]:
    """The lines of these words, top to bottom and, at one height, left to right."""
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda word: (word.top, word.x0)):
        if rows and abs(word.top - rows[-1][0].top) <= LINE_TOLERANCE * max(word.size, rows[-1][0].size):
            rows[-1].append(word)
        else:
            rows.append([word])
    lines: list[Line] = []
    for found in rows:
        part: list[Word] = []
        for word in sorted(found, key=lambda word: word.x0):
            if part and word.x0 - part[-1].x1 > COLUMN_GAP * max(word.size, part[-1].size):
                lines.append(Line(tuple(part)))
                part = []
            part.append(word)
        lines.append(Line(tuple(part)))
    return lines


def blocks_of(words: Iterable[Word], page: int) -> list[RawBlock]:
    """The text blocks of a page's words, in the order their first lines come."""
    blocks: list[list[Line]] = []
    for line in lines_of(words):
        target = next((block for block in reversed(blocks) if _goes_on(block[-1], line)), None)
        if target is None:
            blocks.append([line])
        else:
            target.append(line)
    return [_raw(block, page) for block in blocks]


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
