"""What a request is reckoned to cost before it is sent (plan M1, costs): its input counted with
tiktoken and a tenth beside, for providers whose tokenizer counts more."""

import json

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.llm.budget import count_tokens
from app.llm.metering import MARGIN, Spent, estimate_input

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
REQUEST = ModelRequest(parts=[UserPromptPart("Lies das Dokument und nenne seinen Titel.")])


def test_a_request_is_reckoned_at_its_tokens_with_a_tenth_beside_and_never_below() -> None:
    estimate = estimate_input([], REQUEST, instructions="Antworte knapp.", schema=SCHEMA)

    counted = count_tokens(json.dumps(SCHEMA)) + count_tokens("Antworte knapp.")
    assert MARGIN == 1.1
    assert estimate >= (counted + count_tokens("Lies das Dokument und nenne seinen Titel.")) * MARGIN


def test_what_a_retry_replays_is_reckoned_with_it() -> None:
    history: list[ModelMessage] = [REQUEST, ModelResponse(parts=[TextPart("Ein langer Titel " * 50)])]

    first = estimate_input([], REQUEST, instructions=None, schema=SCHEMA)
    again = estimate_input(history, REQUEST, instructions=None, schema=SCHEMA)

    assert again > first + count_tokens("Ein langer Titel " * 50)


def test_spent_adds_up_and_tells_an_estimate() -> None:
    total = Spent(input_tokens=10, cached_input_tokens=4, output_tokens=3, requests=1) + Spent(
        input_tokens=5, output_tokens=2, unanswered_requests=1, estimated=True
    )

    assert total == Spent(15, 4, 5, 1, 1, estimated=True)
    assert total.tokens == 20
