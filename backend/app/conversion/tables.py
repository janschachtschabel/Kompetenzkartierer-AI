"""Tables as pdfplumber finds them, and tables continued over a page break (plan M1, 3.2).

pdfplumber finds a table by its ruling lines; a table without them reads as text. A cell's text
is its words, the cell's own line breaks and control signs aside. The first row with text - an
empty one above it is dropped - is the table's header where every sign in it is bold; the old app
took any first row for one.

A table that ends a page - reaches lowest of its text and tables, running heads and feet aside,
however far down a note beside it begins - and one that begins the next - stands highest on it,
however a note in its margin is read - with as many columns are one table where the second has no
header row, or repeats the first one's: the repeated header
goes. The rows join the first part, each cell keeping the page it stands on; the second part's
block goes. A table may run on over many pages so; a page between without text or a table - an
empty one, a picture - ends it.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.conversion.layout import Box, RawBlock, RawCell, RawPage, clean_text, style_of

_BODY = ("text", "table")  # what is no running head or foot


@dataclass(frozen=True)
class FoundTable:
    """A table as pdfplumber read it: each row's texts and the boxes of its cells, None where a
    spanning cell covers the place, and the table's box."""

    texts: Sequence[Sequence[str | None]]
    boxes: Sequence[Sequence[Box | None]]
    bbox: Box


def table_block(table: FoundTable, chars: Sequence[Mapping[str, Any]], page: int) -> RawBlock | None:
    """The block of a ``table`` on ``page`` among the page's ``chars`` (pdfplumber's: x0, x1, top,
    bottom, text, fontname): rows of cells, empty rows dropped; None where no row is left - ruling
    lines around nothing."""
    rows: list[tuple[RawCell | None, ...]] = []
    for found, places in zip(table.texts, table.boxes, strict=True):
        cells = [None if cell is None else " ".join(clean_text(cell).split()) for cell in found]
        if not any(cells):
            continue
        header = not rows and _bold(chars, [place for place in places if place is not None])
        rows.append(
            tuple(None if cell is None else RawCell(text=cell, header=header, page=page) for cell in cells)
        )
    if not rows:
        return None
    return RawBlock(page, "table", "", table.bbox, None, False, False, tuple(rows))


def _bold(chars: Sequence[Mapping[str, Any]], places: Iterable[Box]) -> bool:
    """Whether every sign within these cells is set bold - and there is one."""
    signs = [
        char
        for x0, top, x1, bottom in places
        for char in chars
        if x0 <= (char["x0"] + char["x1"]) / 2 <= x1
        and top <= (char["top"] + char["bottom"]) / 2 <= bottom
        and char["text"].strip()
    ]
    return bool(signs) and all(style_of(char["fontname"])[0] for char in signs)


def merge_across_pages(pages: list[RawPage]) -> None:
    """Join each table continued on the next page to the part it continues, in place."""
    open_part: tuple[RawPage, int] | None = None  # the table that ends the pages read so far
    for page in pages:
        body = [index for index, block in enumerate(page.blocks) if block.kind in _BODY]
        if not body:
            open_part = None  # an empty page, or a picture's: what follows continues nothing
            continue
        if open_part is not None:
            holder, at = open_part
            # what begins highest on the page continues it, however a note in the margin is read
            first = min(body, key=lambda index: page.blocks[index].bbox[1])
            joined = _joined(holder.blocks[at], page.blocks[first])
            if joined is not None:
                holder.blocks[at] = joined
                foot = page.blocks[first].bbox[3]
                del page.blocks[first]
                body = [index for index, block in enumerate(page.blocks) if block.kind in _BODY]
                # the part ends the page where nothing left on it ends lower: the table may run on
                if all(page.blocks[index].bbox[3] <= foot for index in body):
                    continue
        last = max(body, key=lambda index: page.blocks[index].bbox[3])
        open_part = (page, last) if page.blocks[last].kind == "table" else None


def _joined(part: RawBlock, next_part: RawBlock) -> RawBlock | None:
    """The table ``part`` with the rows of ``next_part``, or None where that does not continue it."""
    if next_part.kind != "table" or len(next_part.rows[0]) != len(part.rows[0]):
        return None
    rows = next_part.rows
    if _is_header(rows[0]):
        if not _is_header(part.rows[0]) or _texts(rows[0]) != _texts(part.rows[0]):
            return None
        rows = rows[1:]
    return RawBlock(
        part.page, "table", part.text, part.bbox, part.font_size, part.bold, part.italic, part.rows + rows
    )


def _is_header(row: tuple[RawCell | None, ...]) -> bool:
    return any(cell is not None and cell.header for cell in row)


def _texts(row: tuple[RawCell | None, ...]) -> list[str]:
    return [cell.text if cell else "" for cell in row]
