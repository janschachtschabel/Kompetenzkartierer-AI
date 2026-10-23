"""Words into lines, lines into blocks: runs of text set alike (plan M1, 3.2).

A line is the words at one height, left to right. A word stands on the line whose span - that of
the size most of its signs are set in, so neither a superscript nor a large initial moves it - it
overlaps most, by half the smaller height at least. A word more than 1.5 times as high as that
span, or as low, stands on no such line as it comes: a watermark, a symbol beside two lines or an
initial across three would take them all in, line by line, and splice its letters into one of
them. A sub- or superscript - set smaller, glued to its word (at most twice its size), overlapping
it - stands on its word's line however little it overlaps it (reportlab lowers a subscript by
half a line), and so does a mark far smaller than its word that comes before it; both are placed
once every line stands, with the word they overlap most, since a mark raised to the line above
may touch a word's end there as well. Then a single word far smaller than a line, a space apart
from its words - a footnote's mark, "[1]" - stands on the line whose span holds its middle, and so
do words far smaller between its words ("[1, 2]"), and a single word far larger among them, no
further from one than their size - a formula's operator; but never where the larger covers the
middle of another line too. Words far smaller beside a line, more than one, are a line of their
own: a note in the margin, a label behind a title. Two words of one size are never glued: where
lines are set tight, a word's edge meets one above by chance. Two words a gap narrower than a
tenth of their size apart are one: pdfplumber parts a word where its font or size changes ("Lern"
"feld", "CO" "2"). A line's size is that of most of its signs. No line runs across the gutter
between two columns or into a note beside the text (app/conversion/gutters.py).

A block is the lines below one another, close, overlapping across and set alike - the same size,
bold and italic. A heading begins a block of its own however close the text below it stands, and
a paragraph does where the space above it is more than half its size: the lines of a paragraph
stand 3 points apart at 11 points, paragraphs 6 and more (the fixtures, and what Lehrpläne set).
The lines of a block keep their breaks: its text is the document's wording, line by line.
"""

from bisect import bisect_left, bisect_right, insort
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from itertools import accumulate, pairwise, takewhile

from app.conversion.gutters import parts_of
from app.conversion.layout import RawBlock, Word, style_of

LINE_TOLERANCE = 0.5  # times the size: a line this far up into the one above still goes below it
LINE_OVERLAP = 0.5  # of the smaller height: a word overlapping a line's span this much stands on it
TALL = 1.5  # times the height: a word this much higher than a line's span, or lower, is none of its
WORD_SPACE = 0.1  # times the larger size: two words a narrower gap apart are one
GLUE_RATIO = 2.0  # times the size: a script glues to a word at most this much larger
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
    """The words of a line while they are found, and its span: that of the size most of its
    signs are set in, so a watermark or an initial it holds does not stretch it."""

    words: list[Word] = field(default_factory=list)
    signs: Counter[float] = field(default_factory=Counter)  # by size, to half a point
    spans: dict[float, tuple[float, float]] = field(default_factory=dict)  # the first word's of a size

    @classmethod
    def of(cls, word: Word) -> "_Row":
        row = cls()
        row.add(word)
        return row

    def add(self, word: Word) -> None:
        self.words.append(word)
        size = round(word.size * 2) / 2
        self.signs[size] += len(word.text)
        self.spans.setdefault(size, (word.top, word.bottom))

    @property
    def span(self) -> tuple[float, float]:
        return self.spans[self.signs.most_common(1)[0][0]]

    def overlap(self, word: Word) -> float:
        top, bottom = self.span
        return min(bottom, word.bottom) - max(top, word.top)

    def holds(self, word: Word) -> bool:
        top, bottom = self.span
        height, own = bottom - top, word.bottom - word.top
        if own > TALL * height or height > TALL * own:
            return False
        overlap = self.overlap(word)
        return overlap > 0 and overlap >= LINE_OVERLAP * min(height, own)


@dataclass(frozen=True)
class _Script:
    """A word placed once every line stands: one that stands on no line by its overlap but is
    glued to a larger word - a sub- or superscript - or that began a line of its own before its
    word came."""

    word: Word
    near: list[_Row]  # the lines open when it came
    begun: int  # how many lines had begun by then: those after may be its word's


def lines_of(words: Iterable[Word]) -> list[Line]:
    """The lines of these words, top to bottom and, at one height, left to right."""
    rows = [sorted(row.words, key=lambda word: word.x0) for row in _rows(words)]
    return [Line(tuple(part)) for parts in parts_of(rows) for part in parts]


def _rows(words: Iterable[Word]) -> list[_Row]:
    """The words at each height, the rows in the order their first words come, top down."""
    rows: list[_Row] = []
    open_rows: list[_Row] = []  # those a word further down may still overlap
    scripts: list[_Script] = []
    firsts: list[_Script] = []  # each row's first word, as it came
    for word in sorted(words, key=lambda word: (word.top, word.x0)):
        open_rows = [row for row in open_rows if row.span[1] > word.top]
        holding = [row for row in open_rows if row.holds(word)]
        if holding:
            max(holding, key=lambda row: row.overlap(word)).add(word)
        elif any(_glued(word, other) for row in open_rows for other in row.words):
            scripts.append(_Script(word, open_rows, len(rows)))
        else:
            firsts.append(_Script(word, open_rows, len(rows)))
            rows.append(_Row.of(word))
            open_rows.append(rows[-1])
    # a mark far smaller than its word, raised a little above it, begins a line before its word does
    alone = {
        id(row)
        for row, first in zip(rows, firsts, strict=True)
        if len(row.words) == 1 and _partners(first, rows, set())
    }
    scripts += [first for row, first in zip(rows, firsts, strict=True) if id(row) in alone]
    gone = set(alone)  # the rows whose words went to another
    middles = sorted((row.span[0] + row.span[1]) / 2 for row in rows)
    for row, first in zip(rows, firsts, strict=True):
        if id(row) not in gone and (home := _home(first, row, rows, gone, middles)):
            for word in row.words:
                home.add(word)
            gone.add(id(row))
    kept = [row for row in rows if id(row) not in gone]
    for script in scripts:
        partners = _partners(script, rows, gone)
        if partners:
            max(partners, key=lambda found: _overlap(script.word, found[1]))[0].add(script.word)
        else:  # its word was a mark as well
            insort(kept, _Row.of(script.word), key=lambda row: row.words[0].top)
    return kept


def _home(first: _Script, own: _Row, rows: list[_Row], gone: set[int], middles: list[float]) -> _Row | None:
    """The line a single word far smaller or larger than its span stands on though it glues to none
    of its words - a footnote's mark a space before its note, "[1]" within a sentence, a formula's
    large operator no further from one of them than their size: the one line near whose span holds
    the middle of the word's. Words far smaller, more than one, stand on it between its words alone
    - "[1, 2]" within a sentence; beside it they are a line of their own: a note in the margin, a
    label behind a title. The larger of the two covers the middle of no line but the other's - of
    all the page's lines, ``middles``: a watermark, an initial, a symbol beside two lines does."""
    top, bottom = own.span
    begun = takewhile(lambda row: row.words[0].top < bottom, rows[first.begun :])
    near = [row for row in [*first.near, *begun] if row is not own and id(row) not in gone]
    middle = (top + bottom) / 2
    holding = [row for row in near if row.span[0] <= middle <= row.span[1]]
    if len(holding) != 1:
        return None
    home = holding[0]
    height, own_height = home.span[1] - home.span[0], bottom - top
    if len(own.words) != 1 and not (height > TALL * own_height and _between(own, home)):
        return None
    if own_height > TALL * height:
        # an operator stands among its line's words; a title a little off a small label does not
        large = own.words[0]
        if not any(_distance(large, other) <= other.size for other in home.words):
            return None
        larger = own.span
    elif height > TALL * own_height:
        larger = home.span
    else:
        return None
    # the middles the larger covers: its own and the other's alone
    return home if bisect_right(middles, larger[1]) - bisect_left(middles, larger[0]) == 2 else None


def _partners(script: _Script, rows: list[_Row], moved: set[int]) -> list[tuple[_Row, Word]]:
    """The words, with their rows, the script's word is glued to: on the lines open when it came,
    or on those begun after whose first word begins above its foot - ``moved`` rows aside."""
    begun = takewhile(lambda row: row.words[0].top < script.word.bottom, rows[script.begun :])
    return [
        (row, other)
        for row in [*script.near, *begun]
        if id(row) not in moved
        for other in row.words
        if _glued(script.word, other)
    ]


def _between(own: _Row, home: _Row) -> bool:
    """Whether words of ``home`` stand on either side of those of ``own``: within the line, not
    beside it."""
    first, last = min(word.x0 for word in own.words), max(word.x1 for word in own.words)
    return any(other.x1 <= first for other in home.words) and any(other.x0 >= last for other in home.words)


def _distance(word: Word, other: Word) -> float:
    """How far apart two words stand across the page; none where they overlap across."""
    return max(other.x0 - word.x1, word.x0 - other.x1, 0.0)


def _overlap(word: Word, other: Word) -> float:
    return min(word.bottom, other.bottom) - max(word.top, other.top)


def _apart(before: Word, word: Word) -> bool:
    """Whether a space parts two words side by side: their gap is a tenth of their size or more."""
    return word.x0 - before.x1 >= WORD_SPACE * max(before.size, word.size)


def _glued(word: Word, other: Word) -> bool:
    """Whether ``word``, set smaller, touches ``other`` side by side, on either side, and overlaps
    it: a sub- or superscript and its word. Not two words one above the other, which overlap
    across; nor two of one size, whose edges meet by chance where lines are set tight; nor a word
    and one more than twice its size - an initial, a symbol, a watermark beside the line, whose
    tenth of a size reaches 3.6 points at 36."""
    gap = max(other.x0 - word.x1, word.x0 - other.x1)
    return (
        word.size < other.size - SIZE_TOLERANCE
        and other.size <= GLUE_RATIO * word.size
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
