"""The gutters of a page: where its lines part into columns (plan M1, 3.2).

No line runs across the gutter between two columns or into a note beside the text. A gap of three
sizes parts a line always; a gutter is narrower - 12 points or 8 mm at 10 points - so a gap of
0.8 sizes parts it too where 2 of the 3 lines above and below have one in the same strip, behind
which the next column begins at the same place. Justified text spreads its spaces as wide where
it is not hyphenated, but they wander from line to line; a single wide space parts nothing.
"""

from dataclasses import dataclass
from itertools import pairwise

from app.conversion.layout import Word

COLUMN_GAP = 3.0  # times the size: a wider gap between two words parts a line
GUTTER_GAP = 0.8  # times the size: a gap this wide parts a line where lines near it share it
GUTTER_WINDOW = 3  # lines above and below: those that count as near
GUTTER_SUPPORT = 2  # of the lines near: as many share a gap that is a gutter
GUTTER_ALIGN = 0.1  # times the size: the columns behind a gutter begin this close in each line


@dataclass(frozen=True)
class _Gap:
    before: Word
    after: Word  # the word that begins the part behind the gap

    @property
    def size(self) -> float:
        return max(self.before.size, self.after.size)


def parts_of(rows: list[list[Word]]) -> list[list[list[Word]]]:
    """The parts of each row, its words left to right, that wide gaps and gutters part it into;
    the rows in order, top down."""
    gaps = [_wide_gaps(row) for row in rows]
    parted: list[list[list[Word]]] = []
    for index, row in enumerate(rows):
        near = [*gaps[max(0, index - GUTTER_WINDOW) : index], *gaps[index + 1 : index + GUTTER_WINDOW + 1]]
        # the words behind a gutter, by identity: a word printed twice over, to look bold, has a twin
        behind = {
            id(gap.after)
            for gap in gaps[index]
            if sum(_shared(gap, other) for other in near) >= GUTTER_SUPPORT
        }
        parts: list[list[Word]] = [[]]
        for word in row:
            if parts[-1] and (
                word.x0 - parts[-1][-1].x1 > COLUMN_GAP * max(word.size, parts[-1][-1].size)
                or id(word) in behind
            ):
                parts.append([])
            parts[-1].append(word)
        parted.append(parts)
    return parted


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
