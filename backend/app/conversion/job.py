"""The job source.convert: a register file's conversion into blocks (plan M1, 3.5).

The job takes the file from the store, checks that it is a PDF, and converts it in a child process
(app/conversion/runners.py) within CONVERT_TIMEOUT_S; the child refuses a file it cannot serve
(app/conversion/convert.py). Done, the blocks, the Markdown and the pages go in one transaction,
the pages booked once (app/db/conversions.py). A failure another attempt cannot cure - the file's
own, a crash of the conversion on it, the deadline, a child the kernel killed - ends the
conversion with its reason, for good; one that may pass (a child gone without a word, the
database) is tried again by the worker. The child logs as the service does, under the job's
request (app/conversion/runners.py).

A cancel or a lost lease cancels the job's task, which ends the child (runners.py). A job whose
conversion no longer waits for it - asked again after it counted as failed, or done by its own
attempt before - records nothing and counts nothing (app/db/conversions.py).
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
from app.conversion.runners import (
    ChildLog,
    ConversionCrashed,
    ConversionDied,
    Convert,
    convert_in_child,
    convert_with_engine,
)
from app.core.logging import current_request_id
from app.core.metrics import observe_conversion
from app.core.storage import ObjectNotFound
from app.db.conversions import FailureCode, conversion_target, record_conversion, record_failure
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, report_progress
from app.sources.filetype import PDF_SIGNATURE

log = logging.getLogger(__name__)
KIND = "source.convert"
MESSAGES: dict[FailureCode, str] = {
    "unreadable": "The file cannot be read as a PDF.",
    "too_many_pages": "The PDF has more pages than the service converts.",
    "too_dense": "A page of the PDF holds more text than any page does.",
    "needs_ocr": "Too few pages carry a text layer; the file needs OCR.",
    "empty": "The conversion found no text beyond running heads and feet.",
    "timed_out": "The conversion took longer than it may.",
    "died": "The conversion's process was ended, most likely for its memory.",
    "crashed": "The conversion failed on this file.",
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
        await _fail(context, job, conversion_id, engine, "file_gone")
    if not data.startswith(PDF_SIGNATURE):
        await _fail(context, job, conversion_id, engine, "not_pdf")
    async with context.pool.connection() as connection:
        await report_progress(connection, job, "converting", {})
    settings = context.settings
    told = ChildLog(level=settings.log_level, format=settings.log_format, request_id=current_request_id())
    # one mkdir, made here: in a thread, a cancel meanwhile would leave the folder behind
    folder = Path(tempfile.mkdtemp(prefix="source-"))
    try:
        path = folder / "source.pdf"
        await asyncio.to_thread(path.write_bytes, data)
        del data  # the child reads the file; the worker need not hold it for the conversion's length
        try:
            async with asyncio.timeout(settings.convert_timeout_s):
                conversion = await convert_in_child(
                    path, engine=engine, max_pages=settings.max_pdf_pages, convert=convert, log=told
                )
        except TimeoutError:
            await _fail(context, job, conversion_id, engine, "timed_out")
        except ConversionRefused as refused:
            await _fail(context, job, conversion_id, engine, refused.code)
        except ConversionCrashed:
            await _fail(context, job, conversion_id, engine, "crashed")
        except ConversionDied:
            await _fail(context, job, conversion_id, engine, "died")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    markdown = await asyncio.to_thread(markdown_of, conversion)  # a long document's text: off the loop
    async with context.pool.connection() as connection:
        # pdfplumber, the one engine so far, costs nothing; an engine that bills comes with its quota
        recorded = await record_conversion(
            connection, conversion_id, job.id, conversion, markdown, billable=False
        )
    if recorded:
        observe_conversion(engine, "done", conversion.pages)
    else:
        log.info("conversion %s no longer waits for job %s: its result goes", conversion_id, job.id)
    return {"conversion_id": str(conversion_id), "pages": conversion.pages, "blocks": len(conversion.blocks)}


async def _fail(
    context: JobContext, job: Job, conversion_id: UUID, engine: str, code: FailureCode
) -> NoReturn:
    async with context.pool.connection() as connection:
        recorded = await record_failure(connection, conversion_id, job.id, code)
    if recorded:
        observe_conversion(engine, code)
    raise PermanentError(code, MESSAGES[code])
