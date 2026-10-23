"""The gutters of a page: where its lines part into columns (plan M1, 3.2).

No line runs across the gutter between two columns or into a note beside the text. A gap of three
sizes parts a line always; a gutter is narrower - 12 points or 8 mm at 10 points - so a gap of
0.8 sizes parts it too where 2 of the 3 lines above and below have one in the same strip, behind
which the next column begins at the same place, and text of 4 sizes at least on either side.
Justified text spreads its spaces as wide where it is not hyphenated, but they wander from line
to line; a single wide space parts nothing. A list's text begins at one place behind its marks
as well, but "•", "1.", "a)", "2.1" or "LF 1" are narrower than a column's line: a list, a table
of contents, stays a column of its own with its marks.

A gutter so found parts more lines than those that share it: a line next to one of them whose gap
of 0.8 sizes crosses its strip - the right column's first line indented - and, anywhere on the
page, a line whose gap crossing it is twice as wide as its other spaces as a rule - a column of a
line or two below a paragraph across both. Not justified text across the page below the columns,
whose spaces, wide where it is not hyphenated, are alike. The gutters of one page are not those of
the next: where a page holds a single line or two in a second column, nothing parts them.
"""

from bisect import bisect_left, insort
from dataclasses import dataclass
from itertools import pairwise
from statistics import median

from app.conversion.layout import Word

COLUMN_GAP = 3.0  # times the size: a wider gap between two words parts a line
GUTTER_GAP = 0.8  # times the size: a gap this wide parts a line where lines near it share it
GUTTER_WINDOW = 3  # lines above and below: those that count as near
GUTTER_SUPPORT = 2  # of the lines near: as many share a gap that is a gutter
GUTTER_ALIGN = 0.1  # times the size: the columns behind a gutter begin this close in each line
GUTTER_TEXT = 4.0  # times the size: the text the lines near carry on either side of a gutter
GUTTER_NEAR = 1  # rows: a gutter parts the rows this close to those that confirm it
GUTTER_WIDEST = 2.0  # times the row's median space: a gap so wide crossing a gutter parts its row


@dataclass(frozen=True)
class _Gap:
    before: Word
    after: Word  # the word that begins the part behind the gap
    first: Word  # the word that begins the part before it: behind the last wide gap, or the row's
    last: Word  # the word that ends the part behind it: before the next wide gap, or the row's
    at: int  # which of the row's spaces it is, from the left

    @property
    def size(self) -> float:
        return max(self.before.size, self.after.size)

    @property
    def between_text(self) -> bool:
        """Whether text as wide as a column's line stands on either side - no list's mark does."""
        least = GUTTER_TEXT * self.size
        return self.before.x1 - self.first.x0 >= least and self.last.x1 - self.after.x0 >= least


def parts_of(rows: list[list[Word]]) -> list[list[list[Word]]]:
    """The parts of each row, its words left to right, that wide gaps and gutters part it into;
    the rows in order, top down."""
    gaps = [_wide_gaps(row) for row in rows]
    gutters = [
        (index, gap)
        for index, found in enumerate(gaps)
        for near in [
            [*gaps[max(0, index - GUTTER_WINDOW) : index], *gaps[index + 1 : index + GUTTER_WINDOW + 1]]
        ]
        for gap in found
        if sum(_shared(gap, other) for other in near) >= GUTTER_SUPPORT
    ]
    strips = _strips(gutters)
    parted: list[list[list[Word]]] = []
    for index, (row, found) in enumerate(zip(rows, gaps, strict=True)):
        spaces = [word.x0 - before.x1 for before, word in pairwise(row)]
        # the words behind a gutter, by identity: a word printed twice over, to look bold, has a twin
        behind = {id(gap.after) for gap in found if any(strip.parts(gap, index, spaces) for strip in strips)}
        parts: list[list[Word]] = [[]]
        for word in row:
            if parts[-1] and (_far_apart(parts[-1][-1], word) or id(word) in behind):
                parts.append([])
            parts[-1].append(word)
        parted.append(parts)
    return parted


@dataclass
class _Strip:
    """A strip of the page the gutters at one column's beginning share, and the rows they stand in."""

    left: float  # the right end of the line before the column that reaches furthest
    right: float  # where the column begins
    rows: list[int]  # by their place on the page, in order

    def parts(self, gap: _Gap, row: int, spaces: list[float]) -> bool:
        """Whether ``gap``, the ``gap.at``th of the spaces of the ``row``th row, parts it here: where
        it crosses the strip in a row next to one that stands in it, or, further off, where it is
        twice as wide as the row's other spaces are as a rule - justified text across the page
        below the columns spreads its spaces alike."""
        if not (gap.before.x1 < self.right and gap.after.x0 > self.left):
            return False
        place = bisect_left(self.rows, row)
        if any(
            abs(self.rows[at] - row) <= GUTTER_NEAR for at in (place - 1, place) if 0 <= at < len(self.rows)
        ):
            return True
        others = [space for at, space in enumerate(spaces) if at != gap.at]
        return bool(others) and spaces[gap.at] >= GUTTER_WIDEST * median(others)


def _strips(gutters: list[tuple[int, _Gap]]) -> list[_Strip]:
    """The strips the page's gutters share, with the rows they stand in: for each place a column
    begins, from the right end of the line before it that reaches furthest. A gutter behind a short
    line spans most of the column before it, whose wide spaces it would part."""
    strips: list[_Strip] = []
    for row, gap in sorted(gutters, key=lambda found: found[1].after.x0):
        if strips and gap.after.x0 - strips[-1].right <= GUTTER_ALIGN * gap.size:
            strips[-1].left = max(strips[-1].left, gap.before.x1)
            insort(strips[-1].rows, row)
        else:
            strips.append(_Strip(gap.before.x1, gap.after.x0, [row]))
    return strips


def _far_apart(before: Word, word: Word) -> bool:
    """Whether the gap between two words of a row parts it whatever the lines near it have."""
    return word.x0 - before.x1 > COLUMN_GAP * max(before.size, word.size)


def _wide_gaps(row: list[Word]) -> list[_Gap]:
    """The gaps between the row's words, left to right, wide enough to be part of a gutter, each
    with the text on its sides: as far as the next gap that parts the row whatever, or its end."""
    parted = [_far_apart(before, word) for before, word in pairwise(row)]  # behind each word but the last
    firsts = [0]  # of each word, the first word of its part
    for index, apart in enumerate(parted, start=1):
        firsts.append(index if apart else firsts[-1])
    lasts = [len(row) - 1]  # of each word, from the last, the last word of its part
    for index in reversed(range(len(parted))):
        lasts.append(index if parted[index] else lasts[-1])
    lasts.reverse()
    return [
        _Gap(before, word, row[firsts[index]], row[lasts[index + 1]], index)
        for index, (before, word) in enumerate(pairwise(row))
        if word.x0 - before.x1 >= GUTTER_GAP * max(before.size, word.size)
    ]


def _shared(gap: _Gap, gaps: list[_Gap]) -> bool:
    """Whether one of ``gaps`` lies in the same strip of the page as ``gap``, across, the part behind
    both begins at one place, and text stands on either side of it: justified text, wide spaces and
    all, wanders from line to line, a column begins where it begins - and the text of a list behind
    its marks begins at one place too."""
    return any(
        other.between_text
        and _across(gap, other)
        and abs(gap.after.x0 - other.after.x0) <= GUTTER_ALIGN * max(gap.size, other.size)
        for other in gaps
    )


def _across(gap: _Gap, other: _Gap) -> bool:
    """Whether the two gaps share a strip of the page, across."""
    return min(gap.after.x0, other.after.x0) > max(gap.before.x1, other.before.x1)
