"""The reading order of a page's blocks, text and tables (plan M1, 3.2): an XY cut.

A page is cut along a strip wider than a point that no block reaches into: first one down the
page - the gutter between two columns, which are read left to right - else one across it, between
bands read top down. Each part is cut again the same way, until a part has no such strip; its
blocks go top down, at one height left to right. A page of one column is read top down as it
always was; one of two columns a column after the other, a heading across both before them and a
foot below both after them.

Blocks side by side that a block below spans as well are read row by row; with nothing below
reaching across, the strip between them runs down the whole page, and they are columns.
"""

from collections.abc import Sequence

from app.conversion.layout import RawBlock

MIN_CUT = 1.0  # points: a narrower strip without a block cuts nothing
# Where a block's box starts along the cut's strip: x0 for one down the page, top for one across
_DOWN, _ACROSS = 0, 1


def reading_order(blocks: Sequence[RawBlock]) -> list[RawBlock]:
    """The blocks of a page in the order they are read. The parts still to cut wait on a stack of
    their own: a file may nest its blocks deeper than Python recurses."""
    ordered: list[RawBlock] = []
    waiting: list[Sequence[RawBlock]] = [blocks]
    while waiting:
        part = waiting.pop()
        for cut in (_DOWN, _ACROSS):
            parts = _parts(part, cut)
            if len(parts) > 1:
                waiting.extend(reversed(parts))  # the first part on top
                break
        else:
            ordered += sorted(part, key=lambda block: (block.bbox[1], block.bbox[0]))
    return ordered


def _parts(blocks: Sequence[RawBlock], cut: int) -> list[list[RawBlock]]:
    """The blocks in the parts the strips without a block part them into, by ``cut``, in order."""
    parts: list[list[RawBlock]] = []
    end = 0.0
    for block in sorted(blocks, key=lambda block: block.bbox[cut]):
        start, stop = block.bbox[cut], block.bbox[cut + 2]
        if not parts or start - end > MIN_CUT:
            parts.append([])
            end = stop
        parts[-1].append(block)
        end = max(end, stop)
    return parts
