"""Tables as pdfplumber finds them, and tables continued over a page break (plan M1, 3.2).

pdfplumber finds a table by its ruling lines; a table without them reads as text. A cell's text
is its words, the cell's own line breaks aside. The first row is the table's header where every
sign in it is bold - the old app took any first row for one.

A table that ends a page - running heads and feet aside - and one that begins the next with as
many columns are one table where the second has no header row, or repeats the first one's: the
repeated header goes. The rows join the first part, each cell keeping the page it stands on;
the second part's block goes. A table may run on over many pages so.
"""

from collections.abc import Iterable
from typing import Any

from app.conversion.layout import RawBlock, RawCell, RawPage, style_of

_BODY = ("text", "table")  # what is no running head or foot


def table_block(table: Any, page: Any) -> RawBlock | None:
    """The block of a pdfplumber ``table`` on its ``page``: rows of cells, empty rows dropped;
    None where no row is left - ruling lines around nothing."""
    number = page.page_number
    texts = table.extract()
    boxes = [row.cells for row in table.rows]
    rows: list[tuple[RawCell | None, ...]] = []
    for index, (cells, places) in enumerate(zip(texts, boxes, strict=True)):
        if all(not (cell or "").strip() for cell in cells):
            continue
        header = index == 0 and _bold(page, [place for place in places if place is not None])
        rows.append(
            tuple(
                None if cell is None else RawCell(text=" ".join(cell.split()), header=header, page=number)
                for cell in cells
            )
        )
    if not rows:
        return None
    return RawBlock(number, "table", "", tuple(table.bbox), None, False, False, tuple(rows))


def _bold(page: Any, places: Iterable[tuple[float, float, float, float]]) -> bool:
    """Whether every sign within these cells is set bold - and there is one."""
    signs = [
        char
        for x0, top, x1, bottom in places
        for char in page.chars
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
        if open_part is not None and body:
            holder, at = open_part
            first = page.blocks[body[0]]
            joined = _joined(holder.blocks[at], first)
            if joined is not None:
                holder.blocks[at] = joined
                del page.blocks[body[0]]
                body = [index for index, block in enumerate(page.blocks) if block.kind in _BODY]
                if not body:
                    continue  # the whole page was the table: it may run on
        if body and page.blocks[body[-1]].kind == "table":
            open_part = (page, body[-1])
        elif body:
            open_part = None


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
