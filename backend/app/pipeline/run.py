"""The job ``extract.run`` (plan M1 6.6, 7b, 8): a document's stages one after the other - X1
(profile, skeleton, outline; app/pipeline/x1_stage.py), X2 (work packages), X3 (the frame;
app/pipeline/x3_stage.py), X4 (the units' statements; app/pipeline/x4_statements.py), X5 (the checks,
no model; app/pipeline/x5_stage.py) - each stage of each attempt a run of its own
(``extraction_run``), written at once with its run's end under the attempt's lease; X4's units each
written whole on their own, so a unit done stays done.
A job goes on from the last stage done on the document - an attempt after a break (a worker gone,
an error asked again), or a new job after one that ended for good (its attempts spent, its budget
spent); a stage cut off midway left nothing but X4's finished units and the anchors X5 checked. A
document done is neither asked about nor written again - but checked again where X5 owes a check
(app/db/runs.py, x5_owed): a repair (extract.repair, app/pipeline/x6_repair.py) ended before its check
of what it wrote, or an editor changed the tree since. X3 and X4 read the document as X1 left it, its
type among it; X5 checks what the stages wrote (app/pipeline/x5_stage.py).

Payload: ``{"document_id": "<uuid>"}``; what it ends with: the document, its stages, the number of
X2's packages (which X2's run holds, plan M1 6, Festlegung 3).
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.conversion.base import Block
from app.db.conversions import all_blocks, printed_pages
from app.db.documents import Document, document_for_job
from app.db.runs import RunStart, done_stages, finish_run, stage_result, start_run, x5_owed
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, hold_lease
from app.pipeline.extraction import KIND as KIND
from app.pipeline.extraction import document_in
from app.pipeline.progress import report
from app.pipeline.x1_stage import run_x1
from app.pipeline.x2_segments import work_packages
from app.pipeline.x3_stage import run_x3
from app.pipeline.x4_statements import run_x4
from app.pipeline.x5_stage import run_x5
from app.vocab.lookup import current_release

STAGES = ("X1", "X2", "X3", "X4", "X5")


async def extract_document(context: JobContext, job: Job) -> dict[str, Any]:
    document_id = document_in(job.payload)
    async with context.pool.connection() as connection:
        document = None if document_id is None else await document_for_job(connection, document_id)
        if document is None:
            raise PermanentError("document_gone", "the document to extract is gone")
        done = await done_stages(connection, document.id)
        owed = await x5_owed(connection, document.id)  # a repair ended before its check, an edit since
        blocks = await all_blocks(connection, document.conversion_id)
        printed = await printed_pages(connection, document.conversion_id)
    if "X1" not in done:
        await run_x1(context, job, document, blocks, printed)
    if "X2" not in done:
        packages = await _run_x2(context, job, document.id, blocks)
    else:  # done before: by the attempt before, or by an earlier job
        async with context.pool.connection() as connection:
            made = await stage_result(connection, document.id, "X2")
        packages = len((made or {}).get("packages", []))
    if "X3" not in done:
        await run_x3(context, job, await _current(context, document.id), blocks, printed)
    if "X4" not in done:
        await run_x4(context, job, await _current(context, document.id), blocks, printed)
    if "X5" not in done:
        await run_x5(context, job, await _current(context, document.id))
    elif owed:
        await run_x5(context, job, await _current(context, document.id), again=True)
    return {"document_id": str(document.id), "stages": list(STAGES), "packages": packages}


async def _run_x2(context: JobContext, job: Job, document_id: UUID, blocks: Sequence[Block]) -> int:
    """X2 of the document: its work packages, written as its run's result; how many."""
    async with context.pool.connection() as connection:
        found = await work_packages(connection, document_id, blocks)
        # the lease first: an attempt that lost it starts no run that would never end
        await report(connection, job, "extract_segments", units=len(found))
        start = RunStart(
            document_id, job.id, job.attempts, "X2", None, None, None, await current_release(connection)
        )
        run_id = await start_run(connection, start)
    try:
        async with context.pool.connection() as connection, connection.transaction():
            await hold_lease(connection, job)
            await finish_run(connection, run_id, "done", {"packages": [item.as_result() for item in found]})
    except Exception as error:  # the attempt is asked again: its run ends here, by what broke it
        async with context.pool.connection() as connection:
            await finish_run(connection, run_id, "failed", {"failure": type(error).__name__})
        raise
    return len(found)


async def _current(context: JobContext, document_id: UUID) -> Document:
    """The document as the stages before left it: X1 wrote its title and type."""
    async with context.pool.connection() as connection:
        current = await document_for_job(connection, document_id)
    if current is None:
        raise PermanentError("document_gone", "the document to extract is gone")
    return current
