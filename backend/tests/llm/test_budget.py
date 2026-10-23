"""Counting tokens as the models the app speaks to do (plan M1 5.2): with o200k_base, read from the
file the repository holds, never from the network - as the old app counted (extraction/budget.py)."""

import hashlib
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import tiktoken
import tiktoken.registry
import tiktoken_ext.openai_public

from app.llm import budget


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """A process without the network and without tiktoken's cached copy: what tiktoken lacks it
    fetches over requests, which opens a socket."""

    def refused(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("the network is off in this test")

    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "tiktoken-cache"))
    monkeypatch.setattr(tiktoken.registry, "ENCODINGS", {})
    budget.encoding.cache_clear()
    yield
    budget.encoding.cache_clear()


def test_the_repository_holds_the_encoding_tiktoken_names() -> None:
    data = budget.ENCODING_FILE.read_bytes()

    assert hashlib.sha256(data).hexdigest() == budget.ENCODING_SHA256
    # the hash tiktoken itself expects of the file it would fetch
    source = Path(tiktoken_ext.openai_public.__file__).read_text(encoding="utf-8")
    assert f'expected_hash="{budget.ENCODING_SHA256}"' in source


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("Die Lernenden planen ihre Arbeit.", 7),
        ("Übergänge für Schülerinnen und Schüler", 7),
        ("", 0),
        ("Kernlehrplan Mathematik für die Sekundarstufe I in Nordrhein-Westfalen", 17),
        ("1.2.3 Kompetenzerwartungen\n\n- Zahlen\n- Operationen", 17),
        ("Text <|endoftext|> mehr", 9),  # a special token in a document is text, not a refusal
    ],
)
def test_tokens_are_counted_as_tiktoken_counts_them_without_the_network(
    no_network: None, text: str, tokens: int
) -> None:
    # fixed values, counted with tiktoken's own o200k_base (0.14.0) as the old app counted
    assert budget.count_tokens(text) == tokens


def test_the_encoding_is_o200k_base_as_tiktoken_defines_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # tiktoken's definition, read without its ranks, which it would fetch
    monkeypatch.setattr(tiktoken_ext.openai_public, "load_tiktoken_bpe", lambda *_args, **_kwargs: {})
    defined = tiktoken_ext.openai_public.o200k_base()

    loaded = budget.encoding()

    assert (loaded.name, loaded._pat_str, loaded._special_tokens) == (
        defined["name"],
        defined["pat_str"],
        defined["special_tokens"],
    )
    assert loaded.n_vocab == 200_019


@pytest.mark.parametrize("content", [None, b"IQ== 0\n"], ids=["missing", "other-bytes"])
def test_a_missing_or_changed_encoding_stops_the_start_and_is_fetched_from_nowhere(
    no_network: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: bytes | None
) -> None:
    file = tmp_path / "o200k_base.tiktoken"
    if content is not None:
        file.write_bytes(content)
    monkeypatch.setattr(budget, "ENCODING_FILE", file)

    with pytest.raises(budget.TokenizerMissing, match=r"o200k_base\.tiktoken"):
        budget.load_tokenizer()


def test_a_context_window_without_room_beside_a_document_is_refused() -> None:
    budget.check_context_window(budget.RESERVE_TOKENS + 1)

    with pytest.raises(ValueError, match="LLM_CONTEXT_TOKENS=17000"):
        budget.check_context_window(budget.RESERVE_TOKENS)
