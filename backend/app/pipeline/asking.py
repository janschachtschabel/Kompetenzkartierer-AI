"""How a stage of an extraction asks the model (plan M1 6.2, 7): each request charged to the
document's account (its owner's) under the job - an attempt whose job ended or that lost its lease
asks no more - and every answer kept as it came under the run; and how a stage's run ends by what
broke it. A budget spent ends the run as ``budget_exhausted`` and the job with it; an answer that
never took its schema's form ends the run as failed (``model_unanswered``); a run another run's
write came before ends as failed and passes the stage over; any other error ends the run as failed
and the attempt is asked again.
"""

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic_ai.messages import UserContent
from pydantic_ai.models import Model

from app.db.documents import Document
from app.db.runs import RunOutcome, finish_run
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job
from app.llm.calls import StageAgent, ask, build_agent
from app.llm.client import LLMNotConfigured
from app.llm.metering import BudgetExhausted
from app.llm.raw import RawResponses
from app.llm.schema import SCHEMA_DIR, load_schema
from app.pipeline.prefix import as_written
from app.usage.ledger import Charge
from app.usage.meter import LedgerMeter


class Unanswered(Exception):
    """No answer of a request took its schema's form, however often asked."""


class Superseded(Exception):
    """Another run wrote the stage of the document while this one asked."""


@dataclass(frozen=True)
class Asking:
    """One run's requests: its model, where they are charged and kept."""

    context: JobContext
    job: Job
    document: Document
    run_id: UUID
    model: Model
    model_name: str
    keeper: RawResponses

    async def answer(
        self, stage: StageAgent, purpose: str, prompt: str | Sequence[UserContent]
    ) -> dict[str, Any]:
        """The answer of ``stage`` to ``prompt`` (text, or text with a cache breakpoint), its texts
        as the document writes them (the raw answer is kept as it came); Unanswered where none took
        the schema's form."""
        charge = Charge(self.document.owner_id, self.job.id, purpose, self.model_name, self.run_id)
        # with the job: a handler left to unwind after it ended - cancelled, lost - asks no more
        meter = LedgerMeter(self.context.pool, charge, self.job)
        got = await ask(stage, prompt, meter=meter, raw=self.keeper)
        if got.output is None:
            raise Unanswered(got.failure or "no answer took the schema's form")
        return as_written(got.output)

    def agent(self, schema: str, name: str, instructions: str) -> StageAgent:
        loaded = load_schema(self.context.settings.ontology_dir / SCHEMA_DIR, schema)
        return build_agent(self.model, schema=loaded, name=name, instructions=instructions)


def model_of(context: JobContext) -> tuple[Model, str]:
    """The worker's model and its name; PermanentError where it has none."""
    if context.model is None or context.llm is None:
        raise PermanentError("model_not_configured", "the worker has no language model")
    try:
        return context.model(), context.llm.openai_model
    except LLMNotConfigured as error:
        raise PermanentError("model_not_configured", "no key for the language model is set") from error


async def end_run(context: JobContext, run_id: UUID, outcome: RunOutcome, result: dict[str, Any]) -> None:
    async with context.pool.connection() as connection:
        await finish_run(connection, run_id, outcome, result)


async def ended(
    context: JobContext, run_id: UUID, stage: str, work: Awaitable[dict[str, Any]]
) -> dict[str, Any]:
    """What ``work`` - the body of the run ``run_id`` of ``stage`` ("X3") - made; where it breaks,
    the run ended by what broke it, as the module says."""
    try:
        return await work
    except BudgetExhausted as spent:
        await end_run(context, run_id, "budget_exhausted", {})
        raise PermanentError("budget_exhausted", "the account's token budget is spent") from spent
    except Superseded:
        failure = f"{stage} of the document was written by another run meanwhile"
        await end_run(context, run_id, "failed", {"failure": failure})
        return {"superseded": True}
    except Unanswered as unanswered:
        await end_run(context, run_id, "failed", {"failure": str(unanswered)[:2000]})
        raise PermanentError(
            "model_unanswered", "the model's answer never took its schema's form"
        ) from unanswered
    except PermanentError as stopped:
        await end_run(context, run_id, "failed", {"failure": stopped.code})
        raise
    except Exception as error:  # the attempt is asked again: its run ends here, by what broke it
        await end_run(context, run_id, "failed", {"failure": type(error).__name__})
        raise
