"""The job extract.repair: X6, then X5 again (plan M1 8.6, 8b, F2-F6; konzept §13.2 "X6 Reparatur |
nur fehlerhafte Einheiten erneut | 0-2 | wie X4").

X6 asks the model again for the work packages whose statements X5 or the reading of the answer found
wrong (app/pipeline/x6_units.py) - each once a job, twice at most in all -, with X4's question behind the
same prefix and the defects named (prompts/x6.py), side by side as X4 asks, and writes each anew as soon
as it is answered (app/pipeline/x6_unit.py). An answer out of form leaves its package as it was: it is
counted as a repair, and its finding (``x6.unanswered``) asks for one more. A budget spent lets no
further package begin, as in X4. Then X5 checks the document again, its findings replacing the ones
before (app/pipeline/x5_stage.py) - also where the budget ended X6, before the job ends with it.

A document is repaired once X5 has checked it, every package done then; one not checked yet goes on
with extract.run (``document_not_checked``). With nothing to repair - the editors took it meanwhile -
no model is asked and nothing checked again. An attempt after a break goes on after the stages this
job's runs did: X6 done, X5 again; both done, nothing.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from app.conversion.base import Block
from app.db.conversions import all_blocks, printed_pages
from app.db.documents import Document, document_for_job
from app.db.findings import Finding, add_findings
from app.db.runs import RunStart, done_stages, finish_run, stage_result, stages_done_by, start_run
from app.db.units import count_repair
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, hold_lease
from app.llm.calls import StageAgent
from app.llm.metering import BudgetExhausted
from app.llm.raw import RawResponses
from app.pipeline.asking import Asking, Unanswered, ended, model_of
from app.pipeline.extraction import REPAIR_KIND as REPAIR_KIND
from app.pipeline.extraction import document_in
from app.pipeline.ground import ground_of
from app.pipeline.progress import report
from app.pipeline.prompts import x6
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x4_question import UnitQuestions, unit_questions
from app.pipeline.x4_read import WrongUnit, read_unit
from app.pipeline.x5_stage import run_x5
from app.pipeline.x6_unit import rewrite_unit
from app.pipeline.x6_units import RepairUnit, repairable_units

PROMPT_VERSION = x6.PROMPT_VERSION


async def repair_document(context: JobContext, job: Job) -> dict[str, Any]:
    """The handler of extract.repair: X6 of the document, then X5 again."""
    document = await _current(context, document_in(job.payload))
    async with context.pool.connection() as connection:
        # X5 runs once X4 has done every package (app/pipeline/x4_statements.py): none is open then
        if "X5" not in await done_stages(connection, document.id):
            raise PermanentError("document_not_checked", "the document's extraction has not come to X5")
        done = await stages_done_by(connection, job.id)
        blocks = await all_blocks(connection, document.conversion_id)
        printed = await printed_pages(connection, document.conversion_id)
    if "X6" not in done:
        try:
            made = await run_x6(context, job, document, blocks, printed)
        except PermanentError as ending:
            if ending.code == "budget_exhausted":  # what was repaired is checked all the same
                await run_x5(context, job, await _current(context, document.id), again=True)
            raise
        if made["units"] == 0:
            return {"document_id": str(document.id), "units": 0, "checked": False}
    if done[-1:] != ["X5"]:
        await run_x5(context, job, await _current(context, document.id), again=True)
    async with context.pool.connection() as connection:
        repaired = await stage_result(connection, document.id, "X6")
    return {"document_id": str(document.id), "units": (repaired or {}).get("units", 0), "checked": True}


async def run_x6(
    context: JobContext, job: Job, document: Document, blocks: Sequence[Block], printed: Sequence[str | None]
) -> dict[str, Any]:
    """X6 of the document of these blocks (all of its conversion's, in order); the run's result, or
    ``{"units": 0}`` without a run where nothing is to be repaired."""
    model, model_name = model_of(context)
    assert context.llm is not None  # noqa: S101 - the stage has its model (model_of)
    async with context.pool.connection() as connection:
        units = await repairable_units(connection, document.id)
        if not units:
            return {"units": 0}
        await report(connection, job, "repair_units", done=0, total=len(units))
    async with context.pool.connection() as connection:
        ground = await ground_of(connection, document)
        questions = await unit_questions(
            connection, context.llm, document, blocks, printed, ground, model, stage="x6"
        )
    await questions.check([unit.package for unit in units])
    async with context.pool.connection() as connection:
        start = RunStart(
            document.id,
            job.id,
            job.attempts,
            "X6",
            model_name,
            PROMPT_VERSION,
            ground.profile,
            ground.release,
        )
        run_id = await start_run(connection, start)
    keeper = RawResponses(context.storage.sync, run_id, "x6")
    asking = Asking(context, job, document, run_id, model, model_name, keeper)
    return await ended(context, run_id, "X6", _Repairs(asking, questions, len(units)).run(units))


@dataclass
class _Repairs:
    """One run's packages being asked again and written anew."""

    asking: Asking
    questions: UnitQuestions
    total: int
    done: int = 0
    written: int = 0
    dropped: int = 0
    spent: BudgetExhausted | None = None  # once set, no further package begins
    unanswered: list[str] = field(default_factory=list)

    async def run(self, units: Sequence[RepairUnit]) -> dict[str, Any]:
        settings = self.asking.context.settings
        stage = self.asking.agent(x6.SCHEMA, x6.SCHEMA_NAME, x6.INSTRUCTIONS)
        # each package asking holds one connection at a time; the worker's own work needs another
        gate = asyncio.Semaphore(max(1, min(settings.extract_concurrency, settings.db_pool_max_size - 1)))
        failed: Exception | None = None
        try:
            async with asyncio.TaskGroup() as group:
                for unit in units:
                    group.create_task(self._unit(unit, gate, stage))
        except ExceptionGroup as broken:  # the first error ended the others: it is the run's
            failed = broken.exceptions[0]
        if failed is not None:
            raise failed
        return await self._end()

    async def _unit(self, unit: RepairUnit, gate: asyncio.Semaphore, stage: StageAgent) -> None:
        async with gate:
            if self.spent is not None:
                return

            def task(package: WorkPackage, node: str, excerpt: str) -> str:
                return x6.repair_task(package, node, excerpt, unit.defects, unit.kept)

            question = await self.questions.question(unit.package, task)
            try:
                answer = await self.asking.answer(stage, "x6.unit", question.prompt)
                read = read_unit(answer, self.questions.statements, unit.package)
            except BudgetExhausted as spent:
                self.spent = spent
                return
            except (Unanswered, WrongUnit):
                await self._unanswered(unit.package.key)
                return
            key = unit.package.key
            named = [replace(found, details={**found.details, "unit": key}) for found in read.findings]
            read = replace(read, findings=[*question.findings, *named])
            context, job, document = self.asking.context, self.asking.job, self.asking.document
            async with context.pool.connection() as connection:
                made = await rewrite_unit(connection, job, document, unit, read, run_id=self.asking.run_id)
                self.written += made.statements
                self.dropped += made.dropped
                self.done += 1
                await report(connection, job, "repair_units", done=self.done, total=self.total)

    async def _unanswered(self, key: str) -> None:
        """The package stays as it was; its repair is counted (it was paid for) and named."""
        context, job, document = self.asking.context, self.asking.job, self.asking.document
        self.unanswered.append(key)
        message = "the model's answer never took the form of the unit, or answered for another"
        finding = Finding("x6.unanswered", "warning", document.id, message, None, {"unit": key})
        async with context.pool.connection() as connection:
            async with connection.transaction():
                await hold_lease(connection, job)
                await count_repair(connection, document.id, key)
                await add_findings(connection, document.id, self.asking.run_id, [finding])
            self.done += 1
            await report(connection, job, "repair_units", done=self.done, total=self.total)

    async def _end(self) -> dict[str, Any]:
        if self.spent is not None:
            raise self.spent
        context, job, run_id = self.asking.context, self.asking.job, self.asking.run_id
        result = {
            "units": self.total,
            "statements": self.written,
            "dropped": self.dropped,
            "unanswered": sorted(self.unanswered, key=lambda key: int(key[1:])),
        }
        async with context.pool.connection() as connection, connection.transaction():
            await hold_lease(connection, job)
            await finish_run(connection, run_id, "done", result)
        return result


async def _current(context: JobContext, document_id: Any) -> Document:
    """The document as it stands; ``document_gone`` where it does not."""
    async with context.pool.connection() as connection:
        current = None if document_id is None else await document_for_job(connection, document_id)
    if current is None:
        raise PermanentError("document_gone", "the document to repair is gone")
    return current
