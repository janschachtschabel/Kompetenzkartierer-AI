"""X3 of an extraction run (plan M1 7b, F2): the document's frame asked of the model once - its models,
operators, legend and rules wherever it declares them, the statements of its frame ranges - behind
the prefix every request about its units shares (app/pipeline/unit_question.py), and written at once
with the run's end under the attempt's lease and the document's lock.

The frame ranges are X2's packages read typed (``job`` frame), the title pages among them. Where a
run of X3 is done on the document - another job's since this one looked - the stage is passed over;
one done while this one asked is found under the lock at the write: nothing is written and the run
ends as failed. The request is charged to the document's account and kept under the run
(``runs/<run>/x3``); a budget spent or an answer never in form ends the run as X1's do
(app/pipeline/asking.py). Findings go with the run: what the reading could not keep, patterns of the
lexicon that took too long.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from pydantic_ai.messages import UserContent
from pydantic_ai.models import Model

from app.conversion.base import Block
from app.db.documents import Document
from app.db.findings import Finding, add_findings
from app.db.frame_parts import write_frame_parts
from app.db.nodes import append_statements
from app.db.runs import RunStart, done_stages, finish_run, lock_for_stage, stage_result, start_run
from app.domain.lexicon import active_cues
from app.jobs.context import JobContext
from app.jobs.queue import Job, hold_lease
from app.llm.calls import cached_up_to
from app.llm.raw import RawResponses
from app.pipeline.asking import Asking, Superseded, ended, model_of
from app.pipeline.ground import Ground, ground_of
from app.pipeline.lexicon_excerpt import lexicon_excerpt
from app.pipeline.progress import report
from app.pipeline.prompts import x3
from app.pipeline.statement_read import StatementContext
from app.pipeline.toc import OUTSIDE
from app.pipeline.unit_question import prefix_at, prefix_plan, statement_lists
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x3_read import FrameContext, read_frame

PROMPT_VERSION = x3.PROMPT_VERSION


@dataclass(frozen=True)
class FrameQuestion:
    prompt: str | list[UserContent]
    context: FrameContext
    findings: list[Finding]  # of building it


async def run_x3(
    context: JobContext, job: Job, document: Document, blocks: Sequence[Block], printed: Sequence[str | None]
) -> dict[str, Any]:
    """X3 of the document of these blocks (all of its conversion's, in order) - as the store holds
    it after X2 -; the run's result."""
    model, model_name = model_of(context)
    async with context.pool.connection() as connection:
        if "X3" in await done_stages(connection, document.id):  # another job's since this one looked
            return {"done_before": True}
        await report(connection, job, "extract_frame")
        ground = await ground_of(connection, document)
        question = await frame_question(connection, context, document, blocks, printed, ground, model)
        start = RunStart(
            document.id,
            job.id,
            job.attempts,
            "X3",
            model_name,
            PROMPT_VERSION,
            ground.profile,
            ground.release,
        )
        run_id = await start_run(connection, start)
    keeper = RawResponses(context.storage.sync, run_id, "x3")
    asking = Asking(context, job, document, run_id, model, model_name, keeper)
    return await ended(context, run_id, "X3", _stage(asking, question))


async def frame_question(
    connection: psycopg.AsyncConnection,
    context: JobContext,
    document: Document,
    blocks: Sequence[Block],
    printed: Sequence[str | None],
    ground: Ground,
    model: Model,
) -> FrameQuestion:
    """X3's question for the document - X2 done on it - and what its answer is read against."""
    assert context.llm is not None  # noqa: S101 - the stage has its model (model_of)
    kept = await stage_result(connection, document.id, "X2")
    ranges = [
        item for item in map(WorkPackage.from_result, (kept or {}).get("packages", [])) if item.job == "frame"
    ]
    plan = await prefix_plan(connection, context.llm, document.id, blocks, printed, lists="")
    # every window keeps the title pages and the frame parts (app/pipeline/prefix.py): any will do
    prefix = await asyncio.to_thread(prefix_at, plan, 0)
    lists = await statement_lists(connection, ground.sector)
    cues = active_cues(
        ground.cues, ground.regions, document.document_type_iri, None, wider_regions=ground.wider
    )
    texts = [
        blocks[at].text
        for item in ranges
        for at in range(item.first, item.last + 1)
        if blocks[at].kind not in OUTSIDE
    ]
    excerpt = await asyncio.to_thread(lexicon_excerpt, cues, texts, lists.names)
    task = x3.frame_task(ranges, lists.text, excerpt.text)
    statements = StatementContext("x3", document.id, blocks, printed, lists.keys, lists.refines, lists.codes)
    findings = [
        Finding(
            "x3.pattern_timeout", "warning", document.id, "a cue's pattern took too long", None, {"cue": cue}
        )
        for cue in sorted(excerpt.timeouts)
    ]
    return FrameQuestion(cached_up_to(prefix.text, task, model), FrameContext(statements, ranges), findings)


async def _stage(asking: Asking, question: FrameQuestion) -> dict[str, Any]:
    context, job, document = asking.context, asking.job, asking.document
    stage = asking.agent(x3.SCHEMA, x3.SCHEMA_NAME, x3.INSTRUCTIONS)
    read = read_frame(await asking.answer(stage, "x3.frame", question.prompt), question.context)
    async with context.pool.connection() as connection, connection.transaction():
        await hold_lease(connection, job)
        if await lock_for_stage(connection, document.id, "X3"):
            raise Superseded
        await write_frame_parts(
            connection, document.id, document.conversion_id, read.parts, run_id=asking.run_id
        )
        for node, drafts in read.statements.items():
            await append_statements(
                connection, document.id, node, drafts, first_position=1, run_id=asking.run_id
            )
        await add_findings(connection, document.id, asking.run_id, [*question.findings, *read.findings])
        result = {
            "parts": read.counts,
            "statements": sum(len(drafts) for drafts in read.statements.values()),
            "checkedAbsent": list(read.checked_absent),
        }
        await finish_run(connection, asking.run_id, "done", result)
    return result
