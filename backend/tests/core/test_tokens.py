"""API tokens: random, recognisable, stored only as an HMAC with the server's pepper."""

import re

import pytest

from app.core.tokens import TOKEN_PREFIX, looks_like_token, new_token, token_hash

PEPPER = "invented-pepper-for-tests-0123456789abcdef"


def test_a_token_is_long_random_and_recognisable() -> None:
    token = new_token()

    assert token.startswith(TOKEN_PREFIX)
    assert re.fullmatch(r"kka_[A-Za-z0-9_-]{43}", token)
    assert new_token() != token


def test_the_hash_is_fixed_for_a_token_and_a_pepper() -> None:
    token = new_token()

    assert token_hash(token, PEPPER) == token_hash(token, PEPPER)
    assert len(token_hash(token, PEPPER)) == 32
    assert token_hash(token, PEPPER) != token_hash(token, PEPPER + "x")
    assert token_hash(token, PEPPER) != token_hash(new_token(), PEPPER)


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "kka_",
        "kka_" + "a" * 42,
        "kka_" + "a" * 44,
        "xyz_" + "a" * 43,
        "kka_" + "a" * 42 + "!",
        "kka_" + "ä" * 43,
    ],
)
def test_what_is_no_token_is_known_without_hashing(candidate: str) -> None:
    assert looks_like_token(candidate) is False


def test_a_new_token_looks_like_one() -> None:
    assert looks_like_token(new_token()) is True
