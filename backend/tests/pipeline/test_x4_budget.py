"""A budget spent amid X4 (plan M1 7b, 7.4; F11): no unit begins after the one whose request the
budget no longer holds, the units done stay, the run ends as budget_exhausted and the job with it;
a new job with budget asks only the units still open. A model stands in (FunctionModel)."""

from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.jobs.outcome import PermanentError
from app.pipeline.run import extract_document
from app.usage.ledger import usage_of
from tests.pipeline.test_run import Model, a_document, a_job, context_of, setup
from tests.pipeline.test_x3_frame import prompt_of
from tests.pipeline.test_x4_statements import FIELDS, units_done, with_concurrency, x4_runs

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run


async def test_a_budget_spent_amid_x4_keeps_the_units_done_and_a_new_job_asks_the_rest(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===" in prompt_of(messages) and not model.units:
            # the budget holds what is spent and held now: this request, answered, leaves too little
            usage = await usage_of(connection, document.owner_id)
            await connection.execute(
                "UPDATE quota SET token_limit = %s WHERE account_id = %s",
                (usage.tokens_spent + usage.tokens_held, document.owner_id),
            )
        return model(messages, info)

    context = with_concurrency(context_of(pool, tmp_path, answer, database_url), database_url, 1)
    with pytest.raises(PermanentError) as ended:
        await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert ended.value.code == "budget_exhausted"
    assert model.units == ["E2"]
    assert [key for key, _, _ in await units_done(connection, document)] == ["E2"]
    assert [outcome for outcome, _ in await x4_runs(connection, document)] == ["budget_exhausted"]

    await connection.execute(
        "UPDATE quota SET token_limit = NULL WHERE account_id = %s", (document.owner_id,)
    )
    await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert model.asked == ["profile", "outline", "frame"]  # X1 and X3 are not asked again
    assert model.units == ["E2", "E3", "E4"]  # nor the unit done
    assert [key for key, _, _ in await units_done(connection, document)] == ["E2", "E3", "E4"]
    assert [outcome for outcome, _ in await x4_runs(connection, document)] == ["budget_exhausted", "done"]


async def test_the_units_asked_when_the_budget_is_spent_are_written_and_no_other_begins(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # two at a time: the second's request is refused while the first is answered; the first is written
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===" in prompt_of(messages) and not model.units:
            # what is held now is booked as answered; nothing beyond what is spent is left
            usage = await usage_of(connection, document.owner_id)
            await connection.execute(
                "UPDATE quota SET token_limit = %s WHERE account_id = %s",
                (usage.tokens_spent, document.owner_id),
            )
        return model(messages, info)

    context = with_concurrency(context_of(pool, tmp_path, answer, database_url), database_url, 2)
    with pytest.raises(PermanentError) as ended:
        await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert ended.value.code == "budget_exhausted"
    # whether the second reserved before the limit fell or not: what was answered is written, and no
    # unit begun after the budget was spent reached the model
    done = [key for key, _, _ in await units_done(connection, document)]
    assert done == sorted(model.units) and "E4" not in model.units
