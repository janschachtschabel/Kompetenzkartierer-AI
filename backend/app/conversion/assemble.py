"""The pages as an engine read them become a conversion (plan M1, 3.2).

Each page's blocks in reading order - top down, at one height left to right; running heads and
feet marked and the printed page numbers read (app/conversion/page_edges.py); tables continued
over a page joined to their first part (app/conversion/tables.py); the signs of symbol fonts
mapped and a broken text layer noticed (app/conversion/symbols.py, encoding.py), both as findings,
and so the words the engine dropped: a finding for each reason, with the words and their pages;
then the names: ``p<page>-b<n>`` for each page's blocks, the tables counted across the document,
a cell ``T<n>:r<i>c<j>`` by its row and column in the joined table. A place a spanning cell covers
has no cell. A table's text is its rows, line by line, its cells parted by " | " (a bar within a
cell escaped).
"""

from typing import get_args

from app.conversion.base import Block, Cell, Conversion, DropReason, Finding, block_id, cell_id
from app.conversion.encoding import encoding_findings
from app.conversion.layout import RawBlock, RawPage
from app.conversion.page_edges import mark_edges
from app.conversion.symbols import map_symbols
from app.conversion.tables import merge_across_pages


def assemble(pages: list[RawPage], *, engine: str, version: str) -> Conversion:
    for page in pages:
        page.blocks.sort(key=lambda block: (block.bbox[1], block.bbox[0]))
    printed = mark_edges(pages)  # before the joining: running heads and feet do not part a table
    merge_across_pages(pages)
    findings = [*map_symbols(pages), *encoding_findings(pages), *_dropped(pages)]
    blocks: list[Block] = []
    tables = 0
    for page in pages:
        for number, raw in enumerate(page.blocks, start=1):
            cells: tuple[Cell, ...] = ()
            if raw.kind == "table":
                tables += 1
                cells = _cells(raw, tables)
            blocks.append(
                Block(
                    id=block_id(page.number, number),
                    page=page.number,
                    kind=raw.kind,
                    text=_table_text(raw) if raw.kind == "table" else raw.text,
                    bbox=raw.bbox,
                    font_size=raw.font_size,
                    bold=raw.bold,
                    italic=raw.italic,
                    cells=cells,
                )
            )
    return Conversion(
        engine=engine,
        engine_version=version,
        pages=len(pages),
        printed_pages=printed,
        blocks=tuple(blocks),
        findings=tuple(findings),
    )


def _dropped(pages: list[RawPage]) -> list[Finding]:
    return [
        Finding(
            code="text_dropped",
            params={
                "reason": reason,
                "count": sum(page.dropped[reason] for page in pages),
                "pages": sorted(page.number for page in pages if page.dropped[reason]),
            },
        )
        for reason in get_args(DropReason)
        if any(page.dropped[reason] for page in pages)
    ]


def _cells(table: RawBlock, number: int) -> tuple[Cell, ...]:
    return tuple(
        Cell(
            id=cell_id(number, row, column),
            page=cell.page,
            row=row,
            column=column,
            text=cell.text,
            header=cell.header,
        )
        for row, cells in enumerate(table.rows, start=1)
        for column, cell in enumerate(cells, start=1)
        if cell is not None
    )


def _table_text(table: RawBlock) -> str:
    return "\n".join(
        " | ".join("" if cell is None else cell.text.replace("|", "\\|") for cell in row)
        for row in table.rows
    )
