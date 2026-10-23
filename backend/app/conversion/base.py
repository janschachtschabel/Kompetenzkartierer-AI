"""What a conversion (X0) makes of a document: blocks with stable IDs (plan M1, 3.1; konzept §13.2).

A block is a run of text set alike, or a table, on one page of the PDF. Its ID ``p<page>-b<n>``
(cur-shapes.ttl) is what the stages after X0 answer with instead of inventing pages: the page is
the physical one, from 1, and ``n`` counts the page's blocks in reading order, from 1. A table's
cells are ``T<n>:r<i>c<j>`` (cur:tableCell, "T4:r3c2"): the table counted across the document in
reading order, its row and column, all from 1. A table continued over a page break is one block on
the page it begins; each cell keeps the page it stands on.

Headers and footers are marked (``page_header``, ``page_footer``), not dropped; the printed page
number goes beside the physical page. What the conversion noticed about the text - symbols it
could not map, a text layer that looks broken, signs it dropped since no reader reads them where
they stand - goes with it as findings.

The models travel as JSON from the child process that converts (app/conversion/runners.py).
The engines are named here and imported only when asked for: the API never loads a PDF library.
"""

import importlib
import re
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.domain.blocks import BLOCK_ID, CELL_ID

_UNSTORABLE = re.compile(f"[{chr(0)}{chr(0xD800)}-{chr(0xDFFF)}]")
BlockKind = Literal["text", "table", "page_header", "page_footer"]
EngineName = Literal["pdfplumber"]  # the engines offered, for the API's schema (a test compares)
FindingCode = Literal["unmapped_symbol", "encoding_suspect", "text_dropped"]
# Why an engine dropped a sign, the signs counted (text_dropped), in the order the findings say
# them: set upwards or turned, outside the page, smaller than a reader reads, at no finite point
DropReason = Literal["vertical", "off_page", "tiny", "unplaced"]
# Each engine by the class that converts with it, imported when first asked for
_ENGINES = {"pdfplumber": "app.conversion.pdfplumber_blocks:PdfplumberEngine"}


def block_id(page: int, number: int) -> str:
    if page < 1 or number < 1:
        raise ValueError(f"pages and blocks count from 1, not page {page}, block {number}")
    return f"p{page}-b{number}"


def cell_id(table: int, row: int, column: int) -> str:
    if min(table, row, column) < 1:
        raise ValueError(f"tables, rows and columns count from 1, not T{table}:r{row}c{column}")
    return f"T{table}:r{row}c{column}"


def _storable(text: str) -> str:
    """The engines clean their text (app/conversion/layout.py, clean_text); a sign left that no
    store keeps is a fault of one, which fails here, in the converting child, not in the database."""
    if _UNSTORABLE.search(text):
        raise ValueError("a text holds a NUL or a lone surrogate, which PostgreSQL does not store")
    return text


StorableText = Annotated[str, AfterValidator(_storable)]


# The numbers of a block are finite: JSON has no NaN, and an engine drops what it cannot place
# (DropReason "unplaced"), so one here is a fault, which fails in the converting child
_PLACED = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Cell(BaseModel):
    model_config = _PLACED

    id: str
    page: int = Field(ge=1)
    row: int = Field(ge=1)
    column: int = Field(ge=1)
    text: StorableText
    header: bool

    @model_validator(mode="after")
    def _named_by_its_place(self) -> Self:
        """Named as cell_id names it - no zero, no leading one - by its row and column."""
        found = CELL_ID.fullmatch(self.id)
        numbers = (0, 0, 0) if found is None else tuple(int(number) for number in found.groups())
        if min(numbers) < 1 or self.id != cell_id(*numbers) or numbers[1:] != (self.row, self.column):
            raise ValueError(f"cell {self.id} is not that of row {self.row}, column {self.column}")
        return self


class Block(BaseModel):
    model_config = _PLACED

    id: str
    page: int = Field(ge=1)
    kind: BlockKind
    text: StorableText
    bbox: tuple[float, float, float, float]  # x0, top, x1, bottom in PDF points
    font_size: float | None
    bold: bool
    italic: bool
    cells: tuple[Cell, ...] = ()

    @model_validator(mode="after")
    def _named_by_its_page(self) -> Self:
        """Named as block_id names it - the shapes' pattern lets "p01-b1" and "p1-b0" through,
        which would name a block twice or none - by its page."""
        named, number = (0, 0)
        if BLOCK_ID.fullmatch(self.id) is not None:
            named, number = (int(part) for part in self.id[1:].split("-b"))
        if min(named, number) < 1 or self.id != block_id(named, number):
            raise ValueError(f"block {self.id} is not named p<page>-b<block>, each counted from 1")
        if named != self.page:
            raise ValueError(f"block {self.id} names page {named} but stands on page {self.page}")
        if (self.kind == "table") != bool(self.cells):
            raise ValueError(f"block {self.id}: a table holds cells, and only a table does")
        return self


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FindingCode
    params: dict[str, Any]


class Conversion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: str
    engine_version: str
    pages: int = Field(ge=0)
    printed_pages: tuple[str | None, ...]  # the number printed on each page, where one is
    blocks: tuple[Block, ...]
    findings: tuple[Finding, ...] = ()

    @model_validator(mode="after")
    def _blocks_of_its_pages(self) -> Self:
        if len(self.printed_pages) != self.pages:
            raise ValueError(f"{len(self.printed_pages)} printed pages said for {self.pages} pages")
        named: set[str] = set()
        for block in self.blocks:
            if block.id in named:
                raise ValueError(f"block {block.id} is named twice")
            if block.page > self.pages:
                raise ValueError(f"block {block.id} stands on page {block.page} of {self.pages}")
            named.add(block.id)
        return self


class Engine(Protocol):
    name: str
    version: str

    def convert(self, path: Path, *, pages: int, max_signs: int = ...) -> Conversion:
        """The conversion of ``path``, whose text layer counted ``pages``; UnreadablePdf where
        the engine reads the file otherwise - the limit on pages holds for those - and TooDense
        where it reads a page of more than ``max_signs`` signs (by default the service's)."""
        ...


class UnknownEngine(ValueError):
    """No engine of this name is offered."""


def offered_engines() -> tuple[str, ...]:
    return tuple(_ENGINES)


def engine(name: str) -> Engine:
    """The engine ``name``, its library imported now."""
    if name not in _ENGINES:
        raise UnknownEngine(f"no engine {name!r}; offered: {', '.join(offered_engines())}")
    module, _, cls = _ENGINES[name].partition(":")
    made: Engine = getattr(importlib.import_module(module), cls)()
    return made
