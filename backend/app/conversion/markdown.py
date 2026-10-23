"""The conversion as Markdown for a reader (plan M1, 3.5).

Each block, running heads and feet too, behind its name as a comment a Markdown viewer hides:
``<!-- p3-b2 -->``. Text keeps its lines; a table becomes a table, under its header row or an
empty one where it has none (Markdown wants one), a place a spanning cell covers an empty cell.
The stages after X0 read the blocks, not this.
"""

from app.conversion.base import Block, Conversion


def markdown_of(conversion: Conversion) -> str:
    return "\n".join(f"<!-- {block.id} -->\n{_body(block)}\n" for block in conversion.blocks)


def _body(block: Block) -> str:
    if block.kind != "table":
        return block.text
    columns = max(cell.column for cell in block.cells)
    rows: dict[int, list[str]] = {}
    for cell in block.cells:
        rows.setdefault(cell.row, [""] * columns)[cell.column - 1] = cell.text.replace("|", "\\|")
    ordered = [rows.get(number, [""] * columns) for number in range(1, max(rows) + 1)]
    header = any(cell.header for cell in block.cells if cell.row == 1)
    head, body = (ordered[0], ordered[1:]) if header else ([""] * columns, ordered)
    lines = [_row(head), _row(["---"] * columns), *(_row(row) for row in body)]
    return "\n".join(lines)


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"
