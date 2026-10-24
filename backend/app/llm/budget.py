"""Counting tokens as the models the app speaks to do: o200k_base, the encoding of gpt-4o, gpt-5
and gpt-6, for every provider (plan M1, costs - a gateway's own tokenizer may differ, which the
reservation's margin covers).

The encoding is read from the file beside this module, checked against its SHA-256, and never
fetched: tiktoken's own loader, missing or doubting its cached copy, downloads it again in the
middle of a job and writes a copy into the temporary folder. Built once and kept, as the old app
learnt (extraction/budget.py): tiktoken holds the interpreter while it builds, 170 ms of a still
event loop at the first count after a start, so the start builds it.
"""

import base64
import hashlib
from functools import cache
from pathlib import Path

import tiktoken

ENCODING_FILE = Path(__file__).with_name("o200k_base.tiktoken")
# as tiktoken 0.14.0 expects the file it would fetch (tiktoken_ext/openai_public.py)
ENCODING_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
_PATTERN = "|".join(
    [
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""\p{N}{1,3}""",
        r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""",
        r"""\s*[\r\n]+""",
        r"""\s+(?!\S)""",
        r"""\s+""",
    ]
)
_SPECIAL_TOKENS = {"<|endoftext|>": 199999, "<|endofprompt|>": 200018}

# What a request holds beside the document, and the room its answer needs, in tokens - measured
# in the old app with o200k on its profiles (2026-10-03): the prompt around the document at its
# largest (4,305), instructions and output schema (375), an answer of sixty children (5,866) and
# one retry replaying it (5,938), rounded up. A window of no more leaves a document no room.
RESERVE_TOKENS = 17_000


class TokenizerMissing(RuntimeError):
    """The encoding's file is not there, or not the file tiktoken names: the start stops."""


@cache
def encoding() -> tiktoken.Encoding:
    """o200k_base, from the file beside this module; TokenizerMissing where it is not that file."""
    try:
        data = ENCODING_FILE.read_bytes()
    except OSError as error:
        raise TokenizerMissing(f"{ENCODING_FILE} cannot be read: {error.strerror}") from error
    if hashlib.sha256(data).hexdigest() != ENCODING_SHA256:
        raise TokenizerMissing(f"{ENCODING_FILE} is not o200k_base: its SHA-256 differs")
    ranks = {
        base64.b64decode(token): int(rank)
        for token, rank in (line.split() for line in data.splitlines() if line)
    }
    return tiktoken.Encoding(
        name="o200k_base", pat_str=_PATTERN, mergeable_ranks=ranks, special_tokens=_SPECIAL_TOKENS
    )


def load_tokenizer() -> None:
    """Build the encoding now, at the start: TokenizerMissing stops a start that could not count."""
    encoding()


def count_tokens(text: str) -> int:
    """The tokens of ``text``; a special token in it ("<|endoftext|>") is text like any other."""
    return len(encoding().encode_ordinary(text))


def check_context_window(tokens: int, *, max_output_tokens: int) -> None:
    """ValueError where a window of ``tokens`` leaves a document no room beside the rest of a
    request (``RESERVE_TOKENS``) - a window given in thousands, 128 for 128,000, is the likely
    slip - or where the answer's cap leaves the request none: a provider refuses a request
    whose input and cap pass the window. The model's own cap on its answers is not known here."""
    if tokens <= RESERVE_TOKENS:
        raise ValueError(
            f"LLM_CONTEXT_TOKENS={tokens}: a request needs {RESERVE_TOKENS} tokens beside the document; "
            "give the model's whole context window in tokens, 128000 for 128k"
        )
    if max_output_tokens >= tokens - RESERVE_TOKENS:
        raise ValueError(
            f"LLM_MAX_OUTPUT_TOKENS={max_output_tokens}: an answer up to it leaves a request no room in a "
            f"context window of {tokens} beside the {RESERVE_TOKENS} tokens it needs; lower it"
        )
