"""The ledger's meter (plan M1 5.5): a stage's call reserves and books on its account's ledger, and
workers side by side never spend more than the account's limit."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from app.core.ids import new_id
from app.db.accounts import create_account
from app.db.migrate import migrate
from app.jobs.queue import account_lane, enqueue
from app.llm.calls import StageAgent, ask, build_agent
from app.llm.metering import BudgetExhausted
from app.usage.ledger import Charge, usage_of
from app.usage.meter import LedgerMeter
from tests.llm.test_calls import SCHEMA, Ledger

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

CAP = 2_000
CONTENT = "Das Dokument."


@dataclass
class Reports:
    """What the model reports each answer cost; ``asked`` counts its requests."""

    input_tokens: int = 100
    output_tokens: int = 20
    asked: int = 0


def a_stage(reports: Reports) -> StageAgent:
    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        reports.asked += 1
        usage = RequestUsage(input_tokens=reports.input_tokens, output_tokens=reports.output_tokens)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, '{"title": "Zahlen"}')], usage=usage
        )

    return build_agent(
        FunctionModel(answer), schema=SCHEMA, name="titel", instructions="Nenne den Titel.", output_tokens=CAP
    )


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


async def an_account(connection: psycopg.AsyncConnection, token_limit: int) -> UUID:
    account = await create_account(connection, f"konto-{new_id().hex[-12:]}", ["nutzer"])
    await connection.execute(
        "INSERT INTO quota (account_id, token_limit) VALUES (%s, %s)", (account, token_limit)
    )
    return account


async def a_charge(connection: psycopg.AsyncConnection, account: UUID, run_id: UUID | None = None) -> Charge:
    job = await enqueue(connection, "extraction.x1", account_lane(account))
    return Charge(account_id=account, job_id=job, purpose="x1", model="gpt-6-luna", run_id=run_id)


async def held_for_one_call() -> int:
    """What one call of the stage reserves: its input as reckoned and the cap."""
    ledger = Ledger()
    await ask(a_stage(Reports()), CONTENT, meter=ledger)
    [(estimate, cap)] = ledger.reserved
    return estimate + cap


async def test_a_call_through_the_ledger_books_what_its_answer_reports(
    connection: psycopg.AsyncConnection, database_url: str
) -> None:
    account = await an_account(connection, token_limit=100_000)
    run = new_id()
    charge = await a_charge(connection, account, run_id=run)

    async with AsyncConnectionPool(database_url, min_size=1, max_size=2, open=False) as pool:
        answer = await ask(a_stage(Reports()), CONTENT, meter=LedgerMeter(pool, charge))

    assert answer.output == {"title": "Zahlen"}
    cursor = await connection.execute(
        "SELECT job_id, run_id, purpose, model, input_tokens, output_tokens, requests, estimated"
        " FROM llm_usage"
    )
    assert await cursor.fetchall() == [(charge.job_id, run, "x1", "gpt-6-luna", 100, 20, 1, False)]
    usage = await usage_of(connection, account)
    assert (usage.tokens_spent, usage.tokens_held) == (120, 0)


async def test_a_call_its_budget_does_not_hold_is_never_sent(
    connection: psycopg.AsyncConnection, database_url: str
) -> None:
    held = await held_for_one_call()
    account = await an_account(connection, token_limit=held - 1)
    charge = await a_charge(connection, account)
    reports = Reports()

    async with AsyncConnectionPool(database_url, min_size=1, max_size=2, open=False) as pool:
        with pytest.raises(BudgetExhausted):
            await ask(a_stage(reports), CONTENT, meter=LedgerMeter(pool, charge))

    assert reports.asked == 0
    assert (await usage_of(connection, account)).tokens_spent == 0


@pytest.mark.parametrize("share", [1.0, 0.5], ids=["all-it-held", "half-it-held"])
async def test_workers_side_by_side_never_spend_more_than_the_limit(
    connection: psycopg.AsyncConnection, database_url: str, share: float
) -> None:
    # 40 jobs of one call each, workers with their own connections, a limit for 12 calls: whatever
    # their order, the limit holds, and what is left unspent is less than one call's room and what
    # the other workers held beyond what their calls cost - spending all it held, exactly 12 calls.
    # Two workers seldom meet at the limit; eight do, should the quota's lock be missing
    workers = 8
    held = await held_for_one_call()
    limit = 12 * held
    account = await an_account(connection, token_limit=limit)
    charges = [await a_charge(connection, account) for _ in range(40)]
    reports = Reports(input_tokens=round(share * (held - CAP)), output_tokens=round(share * CAP))
    costs = reports.input_tokens + reports.output_tokens
    stage = a_stage(reports)
    waiting = list(charges)
    refused: list[Charge] = []

    async def worker() -> None:
        async with AsyncConnectionPool(database_url, min_size=1, max_size=1, open=False) as pool:
            while waiting:
                charge = waiting.pop()
                try:
                    await ask(stage, CONTENT, meter=LedgerMeter(pool, charge))
                except BudgetExhausted:
                    refused.append(charge)

    await asyncio.gather(*(worker() for _ in range(workers)))

    cursor = await connection.execute("SELECT job_id FROM llm_usage WHERE account_id = %s", (account,))
    booked = {job for (job,) in await cursor.fetchall()}
    assert booked.isdisjoint(charge.job_id for charge in refused)
    assert len(booked) + len(refused) == 40
    usage = await usage_of(connection, account)
    assert usage.tokens_held == 0
    assert usage.tokens_spent == len(booked) * costs
    assert limit - held - (workers - 1) * (held - costs) < usage.tokens_spent <= limit
