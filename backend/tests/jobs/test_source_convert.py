"""The job source.convert: a register file's conversion into blocks (plan M1, 3.5).

The store is a folder, the database real, the conversion runs in its child process as in the
service - on the fixtures of tests/conversion.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from prometheus_client import REGISTRY
from psycopg_pool import AsyncConnectionPool

from app.conversion.job import KIND, convert_source
from app.core.ids import new_id
from app.core.storage import FileSystemStorage
from app.core.storage_async import AsyncStorage
from app.db.conversions import blocks_on_page, conversion_for, lock_conversion, start_conversion
from app.db.migrate import migrate
from app.jobs.context import JobContext
from app.jobs.handlers import make_handlers
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, claim, enqueue
from tests.conversion import standins
from tests.support import make_settings

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

FIXTURES = Path(__file__).resolve().parents[1] / "conversion" / "fixtures"


@pytest.fixture
async def context(database_url: str, tmp_path: Path) -> AsyncIterator[JobContext]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as pool:
        storage = AsyncStorage(FileSystemStorage(tmp_path / "store"))
        settings = make_settings(database_url=database_url, max_pdf_pages=10, convert_timeout_s=60)
        yield JobContext(pool=pool, storage=storage, settings=settings)


def settled(context: JobContext, database_url: str, **settings: Any) -> JobContext:
    """The context with other settings."""
    return JobContext(context.pool, context.storage, make_settings(database_url=database_url, **settings))


async def a_conversion(context: JobContext, data: bytes | None) -> tuple[UUID, UUID, Job]:
    """A register file holding ``data`` (none in the store where None), its conversion asked
    for, and the job claimed: (file, conversion, job)."""
    file_id, conversion_id = new_id(), new_id()
    key = f"sources/{file_id.hex}"
    if data is not None:
        await context.storage.put(key, data)
    async with context.pool.connection() as connection, connection.transaction():
        await connection.execute(
            "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, %s, %s)",
            (file_id, new_id().bytes * 2, len(data or b""), key),
        )
        await lock_conversion(connection, file_id, "pdfplumber")
        job_id = await enqueue(connection, KIND, "test", {"conversion_id": str(conversion_id)})
        await start_conversion(
            connection,
            conversion_id,
            source_file_id=file_id,
            engine="pdfplumber",
            account_id=None,
            job_id=job_id,
        )
    async with context.pool.connection() as connection:
        job = await claim(connection, "w1", [KIND], 60)
    assert job is not None and job.id == job_id
    return file_id, conversion_id, job


async def state(context: JobContext, file_id: UUID) -> Any:
    async with context.pool.connection() as connection:
        return await conversion_for(connection, file_id, "pdfplumber")


def counted(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_a_pdf_in_the_store_becomes_blocks_markdown_and_booked_pages(context: JobContext) -> None:
    file_id, conversion_id, job = await a_conversion(context, (FIXTURES / "prose.pdf").read_bytes())
    done_before = counted("kka_conversions_total", engine="pdfplumber", outcome="done")
    pages_before = counted("kka_conversion_pages_total", engine="pdfplumber")

    result = await convert_source(context, job)

    found = await state(context, file_id)
    assert (found.status, found.pages, found.engine_version) == ("done", 2, "0.11.10")
    assert result == {"conversion_id": str(conversion_id), "pages": 2, "blocks": 7}
    async with context.pool.connection() as connection:
        blocks = await blocks_on_page(connection, conversion_id, 1)
        cursor = await connection.execute("SELECT markdown FROM conversion WHERE id = %s", (conversion_id,))
        (markdown,) = await cursor.fetchone() or ("",)
        cursor = await connection.execute("SELECT progress FROM job WHERE id = %s", (job.id,))
        (progress,) = await cursor.fetchone() or (None,)
    assert blocks[0].bold and blocks[0].text == "1 Lernfeld Steuerungstechnik"
    assert markdown.startswith("<!-- p1-b1 -->\n1 Lernfeld Steuerungstechnik\n")
    assert progress == {"code": "converting", "params": {}}
    assert counted("kka_conversions_total", engine="pdfplumber", outcome="done") == done_before + 1
    assert counted("kka_conversion_pages_total", engine="pdfplumber") == pages_before + 2


async def test_a_conversion_run_again_books_its_pages_once(context: JobContext) -> None:
    _, conversion_id, job = await a_conversion(context, (FIXTURES / "prose.pdf").read_bytes())

    await convert_source(context, job)
    await convert_source(context, job)

    async with context.pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT count(*) FROM conversion_usage WHERE conversion_id = %s", (conversion_id,)
        )
        assert await cursor.fetchone() == (1,)


@pytest.mark.parametrize(
    ("data", "max_pages", "code"),
    [
        ((FIXTURES / "scan.pdf").read_bytes(), 10, "needs_ocr"),
        ((FIXTURES / "edges.pdf").read_bytes(), 4, "too_many_pages"),  # 5 pages
        (b"PK\x03\x04 a docx", 10, "not_pdf"),
        (b"%PDF-1.7\nno document\n", 10, "unreadable"),
        (None, 10, "file_gone"),
    ],
    ids=["scan", "too-many-pages", "docx", "broken", "gone"],
)
async def test_a_file_that_cannot_be_converted_fails_with_its_reason_for_good(
    context: JobContext, database_url: str, data: bytes | None, max_pages: int, code: str
) -> None:
    context = settled(context, database_url, max_pdf_pages=max_pages)
    file_id, _, job = await a_conversion(context, data)
    before = counted("kka_conversions_total", engine="pdfplumber", outcome=code)

    with pytest.raises(PermanentError) as failed:
        await convert_source(context, job)

    assert failed.value.code == code
    found = await state(context, file_id)
    assert (found.status, found.error_code) == ("failed", code)
    assert counted("kka_conversions_total", engine="pdfplumber", outcome=code) == before + 1


async def test_a_conversion_past_its_deadline_ends_its_process_and_fails_for_good(
    context: JobContext, database_url: str
) -> None:
    quick = settled(context, database_url, convert_timeout_s=1)
    file_id, _, job = await a_conversion(quick, (FIXTURES / "prose.pdf").read_bytes())

    with pytest.raises(PermanentError) as failed:
        await convert_source(quick, job, convert=standins.working)

    assert failed.value.code == "timed_out"
    assert (await state(quick, file_id)).error_code == "timed_out"


async def test_the_worker_knows_the_conversion(context: JobContext) -> None:
    assert KIND == "source.convert"
    assert KIND in make_handlers(context)
