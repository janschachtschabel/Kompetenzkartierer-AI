"""Words into lines, lines into blocks: runs of text set alike (plan M1, 3.2).

A line is the words at one height, left to right. A word stands on the line whose span - that of
its largest word, so a superscript does not lift it - it overlaps most, by half the smaller height
at least. A sub- or superscript - set smaller, glued to its word, overlapping it - stands on its
word's line however little it overlaps it (reportlab lowers a subscript by half a line); it is
placed once every line stands, with the word it overlaps most, since a mark raised to the line
above may touch a word's end there as well. Two words of one size are never glued: where lines
are set tight, a word's edge meets one above by chance. Two words a gap narrower than a tenth of
their size apart are one: pdfplumber parts a word where its font or size changes ("Lern" "feld",
"CO" "2"). A line's size is that of most of its signs.

No line runs across the gutter between two columns or into a note beside the text. A gap of three
sizes parts a line always; a gutter is narrower - 12 points or 8 mm at 10 points - so a gap of
0.8 sizes parts it too where 2 of the 3 lines above and below have one in the same strip, behind
which the next column begins at the same place. Justified text spreads its spaces as wide where
it is not hyphenated, but they wander from line to line; a single wide space parts nothing.

A block is the lines below one another, close, overlapping across and set alike - the same size,
bold and italic. A heading begins a block of its own however close the text below it stands, and
a paragraph does where the space above it is more than half its size: the lines of a paragraph
stand 3 points apart at 11 points, paragraphs 6 and more (the fixtures, and what Lehrpläne set).
The lines of a block keep their breaks: its text is the document's wording, line by line.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from itertools import accumulate, pairwise, takewhile

from app.conversion.layout import RawBlock, Word, style_of

LINE_TOLERANCE = 0.5  # times the size: a line this far up into the one above still goes below it
LINE_OVERLAP = 0.5  # of the smaller height: a word overlapping a line's span this much stands on it
WORD_SPACE = 0.1  # times the larger size: two words a narrower gap apart are one
COLUMN_GAP = 3.0  # times the size: a wider gap between two words parts a line
GUTTER_GAP = 0.8  # times the size: a gap this wide parts a line where lines near it share it
GUTTER_WINDOW = 3  # lines above and below: those that count as near
GUTTER_SUPPORT = 2  # of the lines near: as many share a gap that is a gutter
GUTTER_ALIGN = 0.1  # times the size: the columns behind a gutter begin this close in each line
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
        return overlap > 0 and overlap >= LINE_OVERLAP * min(self.bottom - self.top, word.bottom - word.top)


@dataclass(frozen=True)
class _Script:
    """A word that stands on no line by its overlap but is glued to a larger word: a sub- or
    superscript, placed once every line stands, since its own word may come after it."""

    word: Word
    near: list[_Row]  # the lines open when it came
    begun: int  # how many lines had begun by then: those after may be its word's


def lines_of(words: Iterable[Word]) -> list[Line]:
    """The lines of these words, top to bottom and, at one height, left to right."""
    rows = [sorted(row.words, key=lambda word: word.x0) for row in _rows(words)]
    gaps = [_wide_gaps(row) for row in rows]
    lines: list[Line] = []
    for index, row in enumerate(rows):
        near = [*gaps[max(0, index - GUTTER_WINDOW) : index], *gaps[index + 1 : index + GUTTER_WINDOW + 1]]
        # the words behind a gutter, by identity: a word printed twice over, to look bold, has a twin
        behind = {
            id(gap.after)
            for gap in gaps[index]
            if sum(_shared(gap, other) for other in near) >= GUTTER_SUPPORT
        }
        part: list[Word] = []
        for word in row:
            if part and (
                word.x0 - part[-1].x1 > COLUMN_GAP * max(word.size, part[-1].size) or id(word) in behind
            ):
                lines.append(Line(tuple(part)))
                part = []
            part.append(word)
        lines.append(Line(tuple(part)))
    return lines


def _rows(words: Iterable[Word]) -> list[_Row]:
    """The words at each height, the rows in the order their first words come, top down."""
    rows: list[_Row] = []
    open_rows: list[_Row] = []  # those a word further down may still overlap
    scripts: list[_Script] = []
    for word in sorted(words, key=lambda word: (word.top, word.x0)):
        open_rows = [row for row in open_rows if row.bottom > word.top]
        holding = [row for row in open_rows if row.holds(word)]
        if holding:
            max(holding, key=lambda row: row.overlap(word)).add(word)
        elif any(_glued(word, other) for row in open_rows for other in row.words):
            scripts.append(_Script(word, open_rows, len(rows)))
        else:
            rows.append(_Row([word], word.top, word.bottom, word.size))
            open_rows.append(rows[-1])
    for script in scripts:
        _partner_row(script.word, [*script.near, *_begun_by(rows[script.begun :], script.word)]).add(
            script.word
        )
    return rows


def _begun_by(rows: list[_Row], word: Word) -> list[_Row]:
    """The rows of ``rows``, in the order begun, whose first word begins above the word's foot."""
    return list(takewhile(lambda row: row.words[0].top < word.bottom, rows))


def _partner_row(word: Word, rows: list[_Row]) -> _Row:
    """The row of the word ``word`` is glued to that it overlaps most."""
    glued = [(row, other) for row in rows for other in row.words if _glued(word, other)]
    return max(glued, key=lambda found: _overlap(word, found[1]))[0]


def _overlap(word: Word, other: Word) -> float:
    return min(word.bottom, other.bottom) - max(word.top, other.top)


@dataclass(frozen=True)
class _Gap:
    before: Word
    after: Word  # the word that begins the part behind the gap

    @property
    def size(self) -> float:
        return max(self.before.size, self.after.size)


def _wide_gaps(row: list[Word]) -> list[_Gap]:
    """The gaps between the row's words, left to right, wide enough to be part of a gutter."""
    gaps = [_Gap(before, word) for before, word in pairwise(row)]
    return [gap for gap in gaps if gap.after.x0 - gap.before.x1 >= GUTTER_GAP * gap.size]


def _shared(gap: _Gap, gaps: list[_Gap]) -> bool:
    """Whether one of ``gaps`` lies in the same strip of the page as ``gap``, across, and the part
    behind both begins at one place: justified text, wide spaces and all, wanders from line to line,
    a column begins where it begins."""
    return any(
        min(gap.after.x0, other.after.x0) > max(gap.before.x1, other.before.x1)
        and abs(gap.after.x0 - other.after.x0) <= GUTTER_ALIGN * max(gap.size, other.size)
        for other in gaps
    )


def _apart(before: Word, word: Word) -> bool:
    """Whether a space parts two words side by side: their gap is a tenth of their size or more."""
    return word.x0 - before.x1 >= WORD_SPACE * max(before.size, word.size)


def _glued(word: Word, other: Word) -> bool:
    """Whether ``word``, set smaller, touches ``other`` side by side, on either side, and overlaps
    it: a sub- or superscript and its word. Not two words one above the other, which overlap
    across; nor two of one size, whose edges meet by chance where lines are set tight."""
    gap = max(other.x0 - word.x1, word.x0 - other.x1)
    return (
        word.size < other.size - SIZE_TOLERANCE
        and abs(gap) < WORD_SPACE * max(word.size, other.size)
        and _overlap(word, other) > 0
    )


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
    signs: Counter[float] = Counter()
    for line in lines:
        signs[line.size] += len(line.text)
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
        font_size=signs.most_common(1)[0][0],  # sizes creep half a point a line: the most of them
        bold=bold,
        italic=italic,
    )
