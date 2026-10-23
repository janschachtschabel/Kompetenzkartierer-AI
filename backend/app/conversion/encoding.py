"""A text layer that looks broken (plan M1, 3.3).

Three things in a text layer say its signs were not read right: the replacement sign U+FFFD; a
glyph pdfminer could not map, which it writes "(cid:31)"; and UTF-8 read twice, as Latin-1 or as
Windows-1252, which turns "ü" into "Ã¼", "ß" into "ÃŸ" and a quotation mark into "â€…". Where
they make 1 % of the signs and at least 20, the conversion carries a finding with their share,
count and the first five kinds of them: a quote taken from such a text does not match the
document a reader sees.
"""

import re

from app.conversion.base import Finding
from app.conversion.layout import RawPage

SUSPECT_SHARE = 0.01
MIN_SUSPECT = 20
EXAMPLES = 5
# The second byte of a Latin-1 letter's UTF-8, 0x80-0xBF, as Latin-1 reads it and as Windows-1252
# does, which makes "ß" "Ã" and "Ÿ", "Ä" "Ã" and a low quotation mark
_SECOND_BYTE = chr(0x80) + "-" + chr(0xBF) + re.escape(bytes(range(0x80, 0xA0)).decode("cp1252", "ignore"))
_SUSPECT = re.compile(
    "|".join(
        [
            re.escape(chr(0xFFFD)),
            r"\(cid:[0-9]+\)",
            chr(0xC3) + "[" + _SECOND_BYTE + "]",  # a Latin-1 letter's UTF-8 read twice
            # the start of a quotation mark or dash read twice, as Windows-1252 and as Latin-1 reads it
            re.escape(chr(0xE2) + chr(0x20AC)),
            re.escape(chr(0xE2) + chr(0x80)),
        ]
    )
)


def encoding_findings(pages: list[RawPage]) -> list[Finding]:
    signs = 0
    found: list[str] = []
    for page in pages:
        for block in page.blocks:
            for text in [block.text, *(cell.text for row in block.rows for cell in row if cell)]:
                signs += len(text)
                found += _SUSPECT.findall(text)
    if len(found) < MIN_SUSPECT or len(found) < SUSPECT_SHARE * signs:
        return []
    return [
        Finding(
            code="encoding_suspect",
            params={
                "share": round(len(found) / signs, 4),
                "count": len(found),
                "examples": list(dict.fromkeys(found))[:EXAMPLES],
            },
        )
    ]
