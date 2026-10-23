"""A statement's wording as the core compares it: ``cur:textHash`` (konzept §11, cur-kern.ttl).

Two wordings are one where they differ only in how they were set: composed or decomposed
letters, case, signs that set a text without saying anything (a zero width space, a byte order
mark), a word parted at a line's end or by a soft hyphen, the kind of dash, the space between
words, and up to three numberings before them ("1.", "2.1.3.4", "(a)", "b)", "IV.", a bullet).

A word is parted at a line's end where a hyphen and the break stand between a letter and a small
one ("Kompe-" / "tenzen"); before a capital or between digits the hyphen is the word's own and
stays, the break goes ("E-" / "Mail" is "E-Mail", "5-" / "6" is "5-6"). A hyphen within a line
stays too ("E-Mail"), and a dash at a line's end parts no word. A numbering is a number of one
or two digits, of five parts at most, so "1.000" and "100." are none; a letter with a point is
an abbreviation ("z. B.", "d. h."), not a numbering, and a number alone before a word ("3
Aufgaben") may be what the statement says. What looks like both stays
ambiguous: "3. Klasse", "1.5 Stunden" and "i. d. R." lose their first part, and "Ein-" / "und
Ausgabe" across a line is read as one word. Folding case joins what German tells apart only by
"ß": "Maße" and "Masse" are one.
"""

import hashlib
import re
import unicodedata

import regex

_SOFT_HYPHEN = "\N{SOFT HYPHEN}"
_DASHES = regex.compile("[\N{HYPHEN}-\N{HORIZONTAL BAR}\N{MINUS SIGN}]")
# format signs (Cf) but the soft hyphen, which first shows where a word was parted
_FORMAT = regex.compile("(?!\N{SOFT HYPHEN})\\p{Cf}")
# a word parted by a hyphen - not by a dash, which at a line's end parts sentences; a hyphen or a
# dash before a line's break that parts no word stays, and the break goes ("5-" / "6" is "5-6")
_PARTED = regex.compile(
    "(?<=\\p{L})[-\N{HYPHEN}\N{NON-BREAKING HYPHEN}\N{SOFT HYPHEN}]\\h*\\R\\h*(?=\\p{Ll})"
)
_BROKEN = regex.compile(
    "(?<=[\\p{L}\\p{N}])[-\N{HYPHEN}-\N{HORIZONTAL BAR}\N{MINUS SIGN}]\\h*\\R\\h*(?=[\\p{L}\\p{N}])"
)
_ROMAN = r"(?=[ivx])x{0,3}(?:ix|iv|v?i{0,3})"
_NUMBER = r"\d{1,2}(?!\d)"
_BULLETS = "\N{BULLET}\N{BLACK SMALL SQUARE}\N{WHITE BULLET}\N{TRIANGULAR BULLET}\N{MIDDLE DOT}*-"
_ONE_NUMBERING = (
    rf"\(\s*(?:{_NUMBER}|[a-z]|{_ROMAN})\s*\)|{_NUMBER}(?:\.{_NUMBER}){{1,4}}\.?|{_NUMBER}[.)]"
    rf"|[a-z]\)|{_ROMAN}[.)]|[{_BULLETS}]"
)
_NUMBERING = re.compile(rf"(?:\s*(?:{_ONE_NUMBERING})\s+){{1,3}}")
_SPACE = re.compile(r"\s+")


def normalized(verbatim: str) -> str:
    """The wording as its hash takes it."""
    text: str = _FORMAT.sub("", unicodedata.normalize("NFC", verbatim))  # regex is untyped
    text = _DASHES.sub("-", _BROKEN.sub("-", _PARTED.sub("", text)).replace(_SOFT_HYPHEN, ""))
    text = unicodedata.normalize("NFC", text.casefold())
    if (numbering := _NUMBERING.match(text)) is not None:
        text = text[numbering.end() :]
    return _SPACE.sub(" ", text).strip()


def text_hash(verbatim: str) -> str:
    """The SHA-256 of the normalized wording, as 64 hex digits."""
    return hashlib.sha256(normalized(verbatim).encode("utf-8")).hexdigest()
