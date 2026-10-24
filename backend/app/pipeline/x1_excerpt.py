"""What X1 reads of a document for its profile (plan M1 6.2, konzept §13.2): the title pages and the
opening of the text - blocks from the first up to OPENING_SIGNS, the first however long - its table
of contents wherever it stands, and the passages that say when and for whom it holds ("tritt … in
Kraft", "gilt für", transitions), each with the blocks beside it, in the document's order up to
VALIDITY_SIGNS beside the rest. Written as the prefix writes blocks (app/pipeline/prefix.py): each
line led by its block id, the pages marked, what lies between marked left out.
"""

import re
from collections.abc import Sequence

from app.conversion.base import Block
from app.pipeline.prefix import render_positions
from app.pipeline.toc import OUTSIDE, Contents

OPENING_SIGNS = 8_000
VALIDITY_SIGNS = 4_000
_VALIDITY = re.compile(r"in Kraft|Inkrafttreten|außer Kraft|gilt für|gelten für|Übergang", re.IGNORECASE)


def profile_excerpt(blocks: Sequence[Block], printed_pages: Sequence[str | None], contents: Contents) -> str:
    """The excerpt of the blocks (all of a conversion's, in order) X1 asks about."""
    order = [position for position, block in enumerate(blocks) if block.kind not in OUTSIDE]
    chosen: set[int] = set()
    signs = 0
    for position in order:
        if chosen and signs + len(blocks[position].text) > OPENING_SIGNS:
            break
        chosen.add(position)
        signs += len(blocks[position].text)
    chosen |= contents.positions
    passages = 0
    for at, position in enumerate(order):
        if _VALIDITY.search(blocks[position].text) is None:
            continue
        passage = {order[near] for near in range(max(at - 1, 0), min(at + 2, len(order)))} - chosen
        more = sum(len(blocks[near].text) for near in passage)
        if passages + more > VALIDITY_SIGNS:
            break
        chosen |= passage
        passages += more
    return render_positions(blocks, sorted(chosen), printed_pages)
