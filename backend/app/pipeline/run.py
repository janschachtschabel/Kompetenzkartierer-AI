"""The job ``extract.run`` (plan M1 6.6, 7b): a document's stages one after the other - X1 (profile,
skeleton, outline; app/pipeline/x1_stage.py), X2 (work packages), X3 (the frame;
app/pipeline/x3_stage.py) - each stage of each attempt a run of its own (``extraction_run``),
written at once with its run's end under the attempt's lease.
A job goes on from the last stage done on the document - an attempt after a break (a worker gone,
an error asked again), or a new job after one that ended for good (its attempts spent, its budget
spent); a stage cut off midway left nothing. A document done is neither asked about nor written
again. X3 reads the document as X1 left it, its type among it. Paket 7 and 8 hang X4 and X5 on.

Payload: ``{"document_id": "<uuid>"}``; what it ends with: the document, its stages, the number of
X2's packages (which X2's run holds, plan M1 6, Festlegung 3).
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.conversion.base import Block
from app.db.conversions import all_blocks, printed_pages
from app.db.documents import document_for_job
from app.db.runs import RunStart, done_stages, finish_run, stage_result, start_run
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, hold_lease
from app.pipeline.extraction import KIND as KIND
from app.pipeline.progress import report
from app.pipeline.x1_stage import run_x1
from app.pipeline.x2_segments import work_packages
from app.pipeline.x3_stage import run_x3
from app.vocab.lookup import current_release

STAGES = ("X1", "X2", "X3")


async def extract_document(context: JobContext, job: Job) -> dict[str, Any]:
    document_id = _document_id(job.payload)
    async with context.pool.connection() as connection:
        document = None if document_id is None else await document_for_job(connection, document_id)
        if document is None:
            raise PermanentError("document_gone", "the document to extract is gone")
        done = await done_stages(connection, document.id)
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
        async with context.pool.connection() as connection:
            current = await document_for_job(connection, document.id)  # as X1 left it
        if current is None:
            raise PermanentError("document_gone", "the document to extract is gone")
        await run_x3(context, job, current, blocks, printed)
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


def _document_id(payload: dict[str, Any]) -> UUID | None:
    try:
        return UUID(str(payload["document_id"]))
    except (KeyError, ValueError):
        return None
