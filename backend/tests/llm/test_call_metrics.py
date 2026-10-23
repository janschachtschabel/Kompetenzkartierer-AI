"""A stage's requests to the model, counted for the operators (plan M1 5.7): how each ended, and
the tokens it cost by kind - an estimate apart from what the provider reported."""

import httpx2
import pytest
from prometheus_client import REGISTRY
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from app.llm import calls
from app.llm.calls import ask
from app.llm.metering import BudgetExhausted
from tests.llm.test_calls import Ledger, completion, gateway

pytestmark = pytest.mark.anyio

REQUESTS = "kka_llm_requests_total"
TOKENS = "kka_llm_tokens_total"
OUTCOMES = ("answered", "refused", "unanswered", "unsent")
KINDS = ("input", "cached_input", "output", "estimated")


def counts() -> dict[str, float]:
    """Every series of the two counters, by outcome and kind."""
    found = {
        outcome: REGISTRY.get_sample_value(REQUESTS, {"outcome": outcome}) or 0.0 for outcome in OUTCOMES
    }
    found |= {kind: REGISTRY.get_sample_value(TOKENS, {"kind": kind}) or 0.0 for kind in KINDS}
    return found


def grown(before: dict[str, float]) -> dict[str, float]:
    return {name: value - before[name] for name, value in counts().items() if value != before[name]}


async def test_an_answered_request_counts_with_the_tokens_it_reports() -> None:
    before = counts()

    await ask(gateway(lambda _: httpx2.Response(200, json=completion("Zahlen"))), "Text", meter=Ledger())

    assert grown(before) == {"answered": 1, "input": 120, "cached_input": 100, "output": 30}


async def test_a_refused_request_counts_without_tokens() -> None:
    before = counts()
    refusal = {"error": {"message": "bad", "type": "invalid_request_error"}}

    with pytest.raises(ModelHTTPError):
        await ask(gateway(lambda _: httpx2.Response(400, json=refusal)), "Text", meter=Ledger())

    assert grown(before) == {"refused": 1}


async def test_a_request_never_answered_counts_its_reservation_as_estimated() -> None:
    before = counts()
    ledger = Ledger()

    def timed_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("no answer", request=request)

    with pytest.raises(ModelAPIError):
        await ask(gateway(timed_out), "Text", meter=ledger)

    [(estimate, cap)] = ledger.reserved
    assert grown(before) == {"unanswered": 1, "estimated": estimate + cap}


async def test_a_request_never_sent_is_not_counted() -> None:
    before = counts()

    with pytest.raises(BudgetExhausted):
        await ask(
            gateway(lambda _: httpx2.Response(200, json=completion("Zahlen"))), "Text", meter=Ledger(holds=0)
        )

    assert grown(before) == {}


async def test_a_request_that_never_went_out_counts_as_unsent_without_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_wait(seconds: float) -> None:
        pass

    monkeypatch.setattr(calls, "_sleep", no_wait)
    before = counts()

    def refused(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(ModelAPIError):
        await ask(gateway(refused), "Text", meter=Ledger())

    assert grown(before) == {"unsent": 3}


async def test_an_answer_that_reports_no_usage_counts_its_reservation_as_estimated() -> None:
    before = counts()
    ledger = Ledger()
    silent = completion("Zahlen")
    del silent["usage"]

    await ask(gateway(lambda _: httpx2.Response(200, json=silent)), "Text", meter=ledger)

    [(estimate, cap)] = ledger.reserved
    assert grown(before) == {"answered": 1, "estimated": estimate + cap}
