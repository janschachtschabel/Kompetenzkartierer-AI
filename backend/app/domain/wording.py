"""A statement's wording as the core compares it: ``cur:textHash`` (konzept §11, cur-kern.ttl).

Two wordings are one where they differ only in how they were set: composed or decomposed
letters, case, a word parted at a line's end or by a soft hyphen, the kind of dash, the space
between words, and the numbering before them ("1.", "1.2.3", "(a)", "b)", "IV.", a bullet). A
hyphen within a line stays ("E-Mail"), and so does a number alone before a word ("3 Aufgaben"):
it may be what the statement says.
"""

import hashlib
import re
import unicodedata

_SOFT_HYPHEN = "\N{SOFT HYPHEN}"
# a word parted at the end of a line: the hyphen and the break between two letters
_PARTED = re.compile(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)")
_DASHES = re.compile("[\N{HYPHEN}-\N{HORIZONTAL BAR}\N{MINUS SIGN}]")
_ROMAN = r"(?=[ivx])x{0,3}(?:ix|iv|v?i{0,3})"
_BULLETS = "\N{BULLET}\N{BLACK SMALL SQUARE}\N{WHITE BULLET}\N{TRIANGULAR BULLET}\N{MIDDLE DOT}*-"
_NUMBERING = re.compile(
    rf"\s*(?:\(\s*(?:\d+|[a-z]|{_ROMAN})\s*\)|\d+(?:\.\d+)+\.?|\d+[.)]|[a-z][.)]|{_ROMAN}[.)]|[{_BULLETS}])\s+"
)
_SPACE = re.compile(r"\s+")


def normalized(verbatim: str) -> str:
    """The wording as its hash takes it."""
    text = unicodedata.normalize("NFC", verbatim).replace(_SOFT_HYPHEN, "")
    text = _DASHES.sub("-", _PARTED.sub("", text))
    text = unicodedata.normalize("NFC", text.casefold())
    if (numbering := _NUMBERING.match(text)) is not None:
        text = text[numbering.end() :]
    return _SPACE.sub(" ", text).strip()


def text_hash(verbatim: str) -> str:
    """The SHA-256 of the normalized wording, as 64 hex digits."""
    return hashlib.sha256(normalized(verbatim).encode("utf-8")).hexdigest()
