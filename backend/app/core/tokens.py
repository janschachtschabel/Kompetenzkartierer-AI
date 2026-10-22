"""API tokens an admin hands out: ``kka_`` and 32 random bytes in base64url.

The server keeps only HMAC-SHA-256 of a token under its pepper (API_KEY_PEPPER), never the
token: a leaked table yields no usable token, and without the pepper not even a guessable one.
A token is looked up by its hash, so the comparison is the index's, not a timed loop over
secrets. The prefix makes a leaked token recognisable to secret scanners.
"""

import hashlib
import hmac
import re
import secrets

TOKEN_PREFIX = "kka_"  # noqa: S105 - a prefix, no secret
_TOKEN = re.compile(r"kka_[A-Za-z0-9_-]{43}")


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def token_hash(token: str, pepper: str) -> bytes:
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).digest()


def looks_like_token(candidate: str) -> bool:
    """Whether ``candidate`` has a token's form; anything else is refused before any lookup."""
    return _TOKEN.fullmatch(candidate) is not None
