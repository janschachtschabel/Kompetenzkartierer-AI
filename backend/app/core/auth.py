"""Who is asking: an account with its roles, or nobody (a visitor without a token)."""

import unicodedata
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

Role = Literal["admin", "redaktion", "nutzer"]
# The longest account name and key label, in the one spelling the database keeps
MAX_NAME_SIGNS = 200
# Control and format signs (NUL, zero-width space, right-to-left override), line separators,
# and code points not assigned yet, which Unicode asks to be drawn invisibly
_HIDDEN = frozenset({"Cc", "Cf", "Zl", "Zp", "Cn"})
# Signs that show nothing and are neither: the combining grapheme joiner, the Hangul fillers, the
# blank braille pattern, the variation selectors (Unicode's default-ignorable code points)
_INVISIBLE = frozenset(
    {0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0}
    | set(range(0x180B, 0x1810))
    | set(range(0xFE00, 0xFE10))
    | set(range(0xE0100, 0xE01F0))
)


def one_spelling(value: object) -> object:
    """``value`` in NFC where it is text: one name has one spelling for its unique index. Before
    any length is counted - NFC can lengthen a text (U+FB2C is three signs in it)."""
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


def shows_whole(value: str) -> str:
    """``value``, or ValueError if a part of it shows nothing: a control or format sign, a line
    separator, a space other than the plain one, or another invisible sign. No name or key label
    then hides a part from the admin who reads the list."""
    for sign in value:
        category = unicodedata.category(sign)
        if category in _HIDDEN or (category == "Zs" and sign != " ") or ord(sign) in _INVISIBLE:
            raise ValueError("must not hold control, invisible or unusual space signs")
    return value


def visible_only(value: str) -> str:
    """``value`` in one spelling without the signs ``shows_whole`` refuses, for a name a sender's
    system chose (a file's) that is cleaned rather than refused; an unusual space becomes a plain one."""
    kept = []
    for sign in unicodedata.normalize("NFC", value):
        category = unicodedata.category(sign)
        if category == "Zs":
            kept.append(" ")
        elif category not in _HIDDEN and ord(sign) not in _INVISIBLE:
            kept.append(sign)
    return "".join(kept)


def plain_text(value: str) -> str:
    """``value`` in one spelling, showing whole (see both); ValueError otherwise."""
    return shows_whole(str(one_spelling(value)))


@dataclass(frozen=True)
class Principal:
    account_id: UUID | None
    name: str
    roles: frozenset[str]

    @property
    def anonymous(self) -> bool:
        return self.account_id is None


ANONYMOUS = Principal(account_id=None, name="", roles=frozenset())
