"""The page as an engine reads it, before blocks get their names (plan M1, 3.2).

An engine hands over words with their place and font, and tables with their rows; what follows -
lines, blocks, headers and footers, tables continued over a page, names - works on these alone,
so another engine (Docling, 3b) can hand over the same and get the same treatment.
"""

import re
from dataclasses import dataclass, field

from app.conversion.base import BlockKind

Box = tuple[float, float, float, float]  # x0, top, x1, bottom in PDF points

# The style's words, and Adobe's short ones as a word of their own ("HelveticaNeueLTStd-BdIt",
# "MinionPro-It"): capitalised, no small letter after them
_BOLD = re.compile(r"(?i:bold|black|heavy|demi)|(?:Bd|Blk|Hv|Sb|Smbd)(?![a-z])")
_ITALIC = re.compile(r"(?i:italic|oblique)|(?:It|Obl)(?![a-z])")


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
    # a table's rows, its header row first where it has one; None where a spanning cell covers
    # the place, so each cell keeps its column
    rows: tuple[tuple[RawCell | None, ...], ...] = ()


@dataclass
class RawPage:
    number: int  # from 1
    height: float
    blocks: list[RawBlock] = field(default_factory=list)


def style_of(font: str) -> tuple[bool, bool]:
    """Bold and italic as the font's name says them, its subset prefix ("ABCDEF+") aside: in the
    style behind the family's name where one follows it, since a family may hold the words
    ("Academica-Regular", "Blackletter-Regular"); in the whole name where none does ("ArialBold")."""
    name = font.rpartition("+")[2]
    _family, separator, style = _parts(name)
    said = style if separator else name
    return bool(_BOLD.search(said)), bool(_ITALIC.search(said))


def _parts(name: str) -> tuple[str, str, str]:
    """The family, the separator and the style of a font's name: "Arial", ",", "Bold"."""
    for separator in ("-", ","):
        family, found, style = name.partition(separator)
        if found:
            return family, found, style
    return name, "", ""
