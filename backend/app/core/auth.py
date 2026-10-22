"""Who is asking: an account with its roles, or nobody (a visitor without a token)."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

Role = Literal["admin", "redaktion", "nutzer"]


@dataclass(frozen=True)
class Principal:
    account_id: UUID | None
    name: str
    roles: frozenset[str]

    @property
    def anonymous(self) -> bool:
        return self.account_id is None


ANONYMOUS = Principal(account_id=None, name="", roles=frozenset())
