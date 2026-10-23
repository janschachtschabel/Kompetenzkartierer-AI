"""The page as an engine reads it, before blocks get their names (plan M1, 3.2).

An engine hands over words with their place and font, and tables with their rows; what follows -
lines, blocks, headers and footers, tables continued over a page, names - works on these alone,
so another engine (Docling, 3b) can hand over the same and get the same treatment.
"""

import re
from dataclasses import dataclass, field

from app.conversion.base import BlockKind

Box = tuple[float, float, float, float]  # x0, top, x1, bottom in PDF points

_BOLD = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
_ITALIC = re.compile(r"italic|oblique", re.IGNORECASE)
# Adobe's short style names: "MinionPro-It", "MyriadPro-BoldIt"
_IT = re.compile(r"it$", re.IGNORECASE)


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    font: str


@dataclass(frozen=True)
class RawCell:
    text: str
    header: bool
    page: int


@dataclass(frozen=True)
class RawBlock:
    page: int
    kind: BlockKind
    text: str
    bbox: Box
    font_size: float | None
    bold: bool
    italic: bool
    rows: tuple[tuple[RawCell, ...], ...] = ()  # a table's, its header row first where it has one


@dataclass
class RawPage:
    number: int  # from 1
    height: float
    blocks: list[RawBlock] = field(default_factory=list)


def style_of(font: str) -> tuple[bool, bool]:
    """Bold and italic as the font's name says them, its subset prefix ("ABCDEF+") aside."""
    name = font.rpartition("+")[2]
    _family, separator, style = _parts(name)
    bold = bool(_BOLD.search(name))
    italic = bool(_ITALIC.search(name) or (separator and _IT.search(style)))
    return bold, italic


def _parts(name: str) -> tuple[str, str, str]:
    """The family, the separator and the style of a font's name: "Arial", ",", "Bold"."""
    for separator in ("-", ","):
        family, found, style = name.partition(separator)
        if found:
            return family, found, style
    return name, "", ""
