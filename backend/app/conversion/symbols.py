"""Signs of symbol fonts in the text layer (plan M1, 3.3; konzept §13.2).

A symbol font (Wingdings, Symbol) draws its glyphs at the Private Use Area U+F0xx; the text layer
keeps those code points, which mean nothing in Unicode. Where a sign carries a layout signal the
stages after X0 read, it becomes the Unicode sign it shows: Saxony's Lehrpläne mark a reference
with U+F0DA (Wingdings 3, an arrow) and a cross-cutting theme with U+F0DE (a double arrow). Any
other sign of the Private Use Area stays as it is and is counted, by code point and pages, as a
finding: a rule for it can follow once a document shows what it means.
"""

from collections import Counter
from dataclasses import replace

from app.conversion.base import Finding
from app.conversion.layout import RawBlock, RawCell, RawPage

SYMBOLS = {
    chr(0xF0DA): chr(0x2794),  # Wingdings 3 arrow -> heavy wide-headed rightwards arrow: a reference
    chr(0xF0DE): chr(0x21D2),  # Wingdings 3 double arrow -> rightwards double arrow: a cross-cutting theme
}
_MAPPING = str.maketrans(SYMBOLS)
_PRIVATE_USE = range(0xE000, 0xF900)


def map_symbols(pages: list[RawPage]) -> list[Finding]:
    """Map the known signs in place; a finding for each other sign of the Private Use Area."""
    counts: Counter[str] = Counter()
    pages_of: dict[str, set[int]] = {}
    for page in pages:
        for index, block in enumerate(page.blocks):
            mapped = _mapped(block)
            page.blocks[index] = mapped
            for text in _texts(mapped):
                for sign in text:
                    if ord(sign) in _PRIVATE_USE:
                        counts[sign] += 1
                        pages_of.setdefault(sign, set()).add(page.number)
    return [
        Finding(
            code="unmapped_symbol",
            params={
                "codepoint": f"U+{ord(sign):04X}",
                "count": counts[sign],
                "pages": sorted(pages_of[sign]),
            },
        )
        for sign in sorted(counts)
    ]


def _mapped(block: RawBlock) -> RawBlock:
    rows = tuple(
        tuple(None if cell is None else replace(cell, text=cell.text.translate(_MAPPING)) for cell in row)
        for row in block.rows
    )
    return replace(block, text=block.text.translate(_MAPPING), rows=rows)


def _texts(block: RawBlock) -> list[str]:
    cells: list[RawCell] = [cell for row in block.rows for cell in row if cell is not None]
    return [block.text, *(cell.text for cell in cells)]
