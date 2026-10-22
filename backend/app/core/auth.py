"""Who is asking: an account with its roles, or nobody (a visitor without a token)."""

import unicodedata
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

Role = Literal["admin", "redaktion", "nutzer"]
# Control and format signs (NUL, zero-width space, right-to-left override) and line separators
_HIDDEN = frozenset({"Cc", "Cf", "Zl", "Zp"})


def plain_text(value: str) -> str:
    """``value`` in NFC, or ValueError if it holds a control, format or line-separator sign.

    An account name then has one spelling for its unique index, and no name or key label hides
    a part from the admin who reads the list.
    """
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(sign) in _HIDDEN for sign in value):
        raise ValueError("must not hold control or invisible formatting signs")
    return value


@dataclass(frozen=True)
class Principal:
    account_id: UUID | None
    name: str
    roles: frozenset[str]

    @property
    def anonymous(self) -> bool:
        return self.account_id is None


ANONYMOUS = Principal(account_id=None, name="", roles=frozenset())
