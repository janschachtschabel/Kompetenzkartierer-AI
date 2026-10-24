"""The job ``extract.run`` (plan M1 6.6): a document's stages one after the other - X1 (profile,
skeleton, outline; app/pipeline/x1_stage.py), then X2 (work packages) - each stage of each attempt a
run of its own (``extraction_run``), written at once with its run's end under the attempt's lease.
An attempt after a break - a worker gone, an error asked again - goes on from the last stage this
job finished; a stage cut off midway left nothing, its run open. Paket 7 and 8 hang X3 to X5 on.

Payload: ``{"document_id": "<uuid>"}``; what it ends with: the document, its stages, the number of
X2's packages (which X2's run holds, plan M1 6, Festlegung 3).
"""

from typing import Any
from uuid import UUID

from app.db.conversions import all_blocks, printed_pages
from app.db.documents import document_for_job
from app.db.runs import RunStart, done_stages, finish_run, stage_result, start_run
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, hold_lease
from app.pipeline.progress import report
from app.pipeline.x1_stage import run_x1
from app.pipeline.x2_segments import work_packages
from app.vocab.lookup import current_release

KIND = "extract.run"
STAGES = ("X1", "X2")


async def extract_document(context: JobContext, job: Job) -> dict[str, Any]:
    document_id = _document_id(job.payload)
    async with context.pool.connection() as connection:
        document = None if document_id is None else await document_for_job(connection, document_id)
        if document is None:
            raise PermanentError("document_gone", "the document to extract is gone")
        done = await done_stages(connection, document.id, job.id)
        blocks = await all_blocks(connection, document.conversion_id)
        printed = await printed_pages(connection, document.conversion_id)
    if "X1" not in done:
        await run_x1(context, job, document, blocks, printed)
    packages = 0
    if "X2" not in done:
        async with context.pool.connection() as connection:
            start = RunStart(
                document.id, job.id, job.attempts, "X2", None, None, None, await current_release(connection)
            )
            run_id = await start_run(connection, start)
        async with context.pool.connection() as connection:
            found = await work_packages(connection, document.id, blocks)
            await report(connection, job, "extract_segments", units=len(found))
        async with context.pool.connection() as connection, connection.transaction():
            await hold_lease(connection, job)
            await finish_run(connection, run_id, "done", {"packages": [item.as_result() for item in found]})
        packages = len(found)
    else:  # the attempt before ended its last stage, not its job
        async with context.pool.connection() as connection:
            made = await stage_result(connection, document.id, job.id, "X2")
        packages = len((made or {}).get("packages", []))
    return {"document_id": str(document.id), "stages": list(STAGES), "packages": packages}


def _document_id(payload: dict[str, Any]) -> UUID | None:
    try:
        return UUID(str(payload["document_id"]))
    except (KeyError, ValueError):
        return None
