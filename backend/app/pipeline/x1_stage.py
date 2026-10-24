"""X1 of an extraction run (plan M1 6.2-6.4; Festlegungen 1, 10, 11): the document's profile asked
of the model, its skeleton built by the profile's document type, the headings the skeleton left
untyped asked, and all of it written at once, with the run's end, under the attempt's lease.

The stage writes onto a document X1 has not written: one with a tree no run of X1 wrote ends the
job (``document_has_tree``), found at the start or under the document's lock at the write. Where
another job's run wrote X1 since this job looked, the stage is passed over; while this one asked,
the write finds it under the lock, writes nothing and ends its run as failed. Each request is
charged to the document's account (its owner's; the start, plan M1 7.5, decides who may run one)
and kept as it came under the run (``runs/<run>/x1``). A budget spent ends the run as
``budget_exhausted`` and the job with it; an answer that never took its schema's form ends the
run as failed (``model_unanswered``). Either way nothing of the stage is written: what X1 asked
is asked again by the next job - cheaper than a second way of writing (the profile is some 3k
tokens). The findings of the reading go with the run: unknown keys and blocks, headings left out,
patterns that took too long, a work of the same title and region.
"""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import psycopg

from app.conversion.base import Block
from app.db.documents import Document
from app.db.findings import Finding, add_findings
from app.db.nodes import write_subtree
from app.db.profile import lock_for_x1, suggest_work, write_profile, x1_state
from app.db.runs import RunStart, finish_run, start_run
from app.domain.lexicon import active_cues
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, hold_lease
from app.llm.raw import RawResponses
from app.pipeline.asking import Asking, Superseded, ended, model_of
from app.pipeline.ground import Ground, ground_of
from app.pipeline.progress import report
from app.pipeline.prompts import x1_outline, x1_profile
from app.pipeline.skeleton import Skeleton, build_skeleton
from app.pipeline.x1_outline import build_tree, decide
from app.pipeline.x1_profile import Profile, read_profile
from app.pipeline.x1_question import outline_questions, profile_question

PROMPT_VERSION = f"{x1_profile.PROMPT_VERSION}+{x1_outline.PROMPT_VERSION}"
_TREE = "nodes or specifications stand on the document that no extraction wrote"


async def run_x1(
    context: JobContext, job: Job, document: Document, blocks: Sequence[Block], printed: Sequence[str | None]
) -> dict[str, Any]:
    """X1 of the document of these blocks (all of its conversion's, in order); the run's result."""
    model, model_name = model_of(context)
    async with context.pool.connection() as connection:
        state = await x1_state(connection, document.id)
        if state == "tree":
            raise PermanentError("document_has_tree", _TREE)
        if state == "done":  # by another job's run since this one looked (app/pipeline/run.py)
            return {"done_before": True}
        await report(connection, job, "extract_profile")
        ground = await ground_of(connection, document)
        start = RunStart(
            document.id,
            job.id,
            job.attempts,
            "X1",
            model_name,
            PROMPT_VERSION,
            ground.profile,
            ground.release,
        )
        run_id = await start_run(connection, start)
    asking = Asking(
        context, job, document, run_id, model, model_name, RawResponses(context.storage.sync, run_id, "x1")
    )
    return await ended(context, run_id, "X1", _stage(asking, blocks, printed, ground))


async def _stage(
    asking: Asking, blocks: Sequence[Block], printed: Sequence[str | None], ground: Ground
) -> dict[str, Any]:
    context, job, document = asking.context, asking.job, asking.document
    found = active_cues(ground.cues, ground.regions, None, None, wider_regions=ground.wider)
    first = await asyncio.to_thread(build_skeleton, blocks, found, ground.node_types)
    async with context.pool.connection() as connection:
        question = await profile_question(connection, document, blocks, printed, first.contents, found)
    stage = asking.agent(x1_profile.SCHEMA, x1_profile.SCHEMA_NAME, x1_profile.INSTRUCTIONS)
    profile = read_profile(await asking.answer(stage, "x1.profile", question.prompt), question.context)
    # a type the editors set stays the document's (write_profile): the headings are read by it
    document_type = document.document_type_iri or profile.document_type
    typed = active_cues(ground.cues, ground.regions, document_type, None, wider_regions=ground.wider)
    skeleton = await asyncio.to_thread(build_skeleton, blocks, typed, ground.node_types)
    specifications = [(item.key, item.title) for item in profile.specifications]
    async with context.pool.connection() as connection:
        questions = await outline_questions(connection, document, skeleton, blocks, specifications)
        await report(connection, job, "extract_outline", headings=len(questions.asked))
    stage = asking.agent(x1_outline.SCHEMA, x1_outline.SCHEMA_NAME, x1_outline.INSTRUCTIONS)
    answers: list[Mapping[str, Any]] = []
    for prompt in questions.prompts:
        answers.extend((await asking.answer(stage, "x1.outline", prompt))["headings"])
    decisions, outline_findings = decide(skeleton, questions.asked, answers, questions.context)
    async with context.pool.connection() as connection, connection.transaction():
        await hold_lease(connection, job)
        state = await lock_for_x1(connection, document.id)
        if state == "done":
            raise Superseded
        if state == "tree":
            raise PermanentError("document_has_tree", _TREE)
        keys, notes = await write_profile(connection, document.id, profile)
        findings = [*profile.findings, *notes, *outline_findings, *_slow_patterns(skeleton, document.id)]
        findings += await _work_suggested(connection, document, profile)
        await add_findings(connection, document.id, asking.run_id, findings)
        for root in build_tree(skeleton, decisions, keys):
            await write_subtree(connection, document.id, root, run_id=asking.run_id)
        result = {
            "said": dict(profile.said),
            "headings": len(skeleton.headings),
            "asked": len(questions.asked),
            "specifications": sorted(keys),
        }
        await finish_run(connection, asking.run_id, "done", result)
    return result


def _slow_patterns(skeleton: Skeleton, document_id: UUID) -> list[Finding]:
    return [
        Finding(
            "x1.pattern_timeout", "warning", document_id, "a cue's pattern took too long", None, {"cue": cue}
        )
        for cue in sorted(skeleton.timeouts)
    ]


async def _work_suggested(
    connection: psycopg.AsyncConnection, document: Document, profile: Profile
) -> list[Finding]:
    if profile.title is None or document.work_id is not None:
        return []
    work = await suggest_work(connection, profile.title, document.regions)
    if work is None:
        return []
    message = "a work of the same title and region: the editors may set it"
    return [Finding("x1.work_suggestion", "info", document.id, message, None, {"work_id": str(work)})]
