"""The job extract.check (plan M1 9; Paket 9 G9): X5 again on a document its editors changed - its findings
in place of those before (app/pipeline/x5_stage.py). It asks no model, so it is no model job
(app/usage/admission.py). It shares the extraction's key: none runs beside an extraction or a repair, and
no editor changes the document beside it (app/db/editing.py). A document X5 has not checked yet goes on
with extract.run (``document_not_checked``); an attempt after this job's check was done checks not again.
"""

from typing import Any

from app.db.documents import document_for_job
from app.db.runs import done_stages, stages_done_by
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job
from app.pipeline.extraction import CHECK_KIND as CHECK_KIND
from app.pipeline.extraction import document_in
from app.pipeline.x5_stage import run_x5


async def check_document(context: JobContext, job: Job) -> dict[str, Any]:
    """The handler of extract.check: X5 of the document again."""
    document_id = document_in(job.payload)
    async with context.pool.connection() as connection:
        document = None if document_id is None else await document_for_job(connection, document_id)
        if document is None:
            raise PermanentError("document_gone", "the document to check is gone")
        # a draft copy takes no runs along (app/db/draft_copy.py): its first check is this one
        if document.copy_of is None and "X5" not in await done_stages(connection, document.id):
            raise PermanentError("document_not_checked", "the document's extraction has not come to X5")
        checked = "X5" in await stages_done_by(connection, job.id)
    if not checked:
        await run_x5(context, job, document, again=True)
    return {"document_id": str(document.id), "checked": True}
