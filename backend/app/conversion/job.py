"""The job source.convert: a register file's conversion into blocks (plan M1, 3.5).

The job takes the file from the store, checks that it is a PDF, and converts it in a child process
(app/conversion/runners.py) within CONVERT_TIMEOUT_S; the child refuses a file it cannot serve
(app/conversion/convert.py). Done, the blocks, the Markdown and the pages go in one transaction,
the pages booked once (app/db/conversions.py). A failure another attempt cannot cure - the file's
own, the deadline, a child the kernel killed - ends the conversion with its reason, for good; one
that may pass (a crash in the conversion, the database) is tried again by the worker.

A cancel or a lost lease cancels the job's task, which ends the child (runners.py).
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

from app.conversion.convert import ConversionRefused
from app.conversion.markdown import markdown_of
from app.conversion.runners import ConversionDied, Convert, convert_in_child, convert_with_engine
from app.core.metrics import observe_conversion
from app.core.storage import ObjectNotFound
from app.db.conversions import FailureCode, conversion_target, record_conversion, record_failure
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, report_progress

log = logging.getLogger(__name__)
KIND = "source.convert"
_PDF = b"%PDF-"
MESSAGES: dict[FailureCode, str] = {
    "unreadable": "The file cannot be read as a PDF.",
    "too_many_pages": "The PDF has more pages than the service converts.",
    "needs_ocr": "Too few pages carry a text layer; the file needs OCR.",
    "empty": "The conversion found no text beyond running heads and feet.",
    "timed_out": "The conversion took longer than it may.",
    "died": "The conversion's process was ended, most likely for its memory.",
    "not_pdf": "The file is no PDF.",
    "file_gone": "The file is missing from the store.",
}


async def convert_source(
    context: JobContext, job: Job, *, convert: Convert = convert_with_engine
) -> dict[str, Any]:
    """``convert`` stands in for the conversion in tests (runners.convert_in_child)."""
    conversion_id = UUID(job.payload["conversion_id"])
    async with context.pool.connection() as connection:
        target = await conversion_target(connection, conversion_id)
    if target is None:
        raise PermanentError("conversion_gone", "The conversion is no longer in the register.")
    key, engine = target
    try:
        data = await context.storage.get(key)
    except ObjectNotFound:
        log.warning("the file of conversion %s is not in the store: %s", conversion_id, key)
        await _fail(context, conversion_id, engine, "file_gone")
    if not data.startswith(_PDF):
        await _fail(context, conversion_id, engine, "not_pdf")
    async with context.pool.connection() as connection:
        await report_progress(connection, job, "converting", {})
    folder = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="source-"))
    try:
        path = folder / "source.pdf"
        await asyncio.to_thread(path.write_bytes, data)
        settings = context.settings
        try:
            async with asyncio.timeout(settings.convert_timeout_s):
                conversion = await convert_in_child(
                    path, engine=engine, max_pages=settings.max_pdf_pages, convert=convert
                )
        except TimeoutError:
            await _fail(context, conversion_id, engine, "timed_out")
        except ConversionRefused as refused:
            await _fail(context, conversion_id, engine, refused.code)
        except ConversionDied:
            await _fail(context, conversion_id, engine, "died")
    finally:
        shutil.rmtree(folder, ignore_errors=True)  # one file: no wait worth a thread, even cancelled
    async with context.pool.connection() as connection:
        # pdfplumber, the one engine so far, costs nothing; an engine that bills comes with its quota
        await record_conversion(
            connection, conversion_id, conversion, markdown_of(conversion), billable=False
        )
    observe_conversion(engine, "done", conversion.pages)
    return {"conversion_id": str(conversion_id), "pages": conversion.pages, "blocks": len(conversion.blocks)}


async def _fail(context: JobContext, conversion_id: UUID, engine: str, code: FailureCode) -> NoReturn:
    async with context.pool.connection() as connection:
        await record_failure(connection, conversion_id, code)
    observe_conversion(engine, code)
    raise PermanentError(code, MESSAGES[code])
