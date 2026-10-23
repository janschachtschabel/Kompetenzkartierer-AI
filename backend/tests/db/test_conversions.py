"""A register file's conversion as the job and the API keep it (plan M1, 3.5)."""

from collections.abc import AsyncIterator
from uuid import UUID

import psycopg
import pytest

from app.conversion.base import Block, Cell, Conversion, Finding
from app.core.ids import new_id
from app.db.conversions import (
    blocks_on_page,
    conversion_for,
    conversion_target,
    lock_conversion,
    record_conversion,
    record_failure,
    start_conversion,
)
from app.db.migrate import migrate
from app.jobs.queue import enqueue

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


async def a_file(connection: psycopg.AsyncConnection) -> UUID:
    file_id = new_id()
    await connection.execute(
        "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 4, %s)",
        (file_id, new_id().bytes * 2, f"sources/{file_id.hex}"),
    )
    return file_id


async def started(connection: psycopg.AsyncConnection, file_id: UUID) -> tuple[UUID, UUID]:
    """A conversion asked for, with its job: (conversion, job)."""
    async with connection.transaction():
        await lock_conversion(connection, file_id, "pdfplumber")
        there = await conversion_for(connection, file_id, "pdfplumber")
        conversion_id = there.id if there else new_id()
        job_id = await enqueue(connection, "source.convert", "test", {"conversion_id": str(conversion_id)})
        await start_conversion(
            connection,
            conversion_id,
            source_file_id=file_id,
            engine="pdfplumber",
            account_id=None,
            job_id=job_id,
        )
    return conversion_id, job_id


def converted() -> Conversion:
    table_cells = (
        Cell(id="T1:r1c1", page=1, row=1, column=1, text="Nr.", header=True),
        Cell(id="T1:r2c1", page=2, row=2, column=1, text="1", header=False),
    )
    blocks = (
        Block(id="p1-b1", page=1, kind="text", text="Lernfeld 1", bbox=(56, 70, 300, 82),
              font_size=14, bold=True, italic=False),
        Block(id="p1-b2", page=1, kind="table", text="Nr.\n1", bbox=(56, 600, 500, 800),
              font_size=None, bold=False, italic=False, cells=table_cells),
        Block(id="p2-b1", page=2, kind="page_footer", text="- 2 -", bbox=(280, 810, 320, 820),
              font_size=9, bold=False, italic=False),
    )  # fmt: skip
    return Conversion(
        engine="pdfplumber",
        engine_version="0.11.10",
        pages=2,
        printed_pages=(None, "2"),
        blocks=blocks,
        findings=(Finding(code="unmapped_symbol", params={"codepoint": "U+F0B7", "count": 1, "pages": [1]}),),
    )


async def test_a_conversion_asked_for_waits_with_its_job(connection: psycopg.AsyncConnection) -> None:
    file_id = await a_file(connection)

    conversion_id, job_id = await started(connection, file_id)

    state = await conversion_for(connection, file_id, "pdfplumber")
    assert state is not None
    assert (state.id, state.status, state.job_id, state.job_status) == (
        conversion_id,
        "pending",
        job_id,
        "queued",
    )
    assert await conversion_target(connection, conversion_id) == (f"sources/{file_id.hex}", "pdfplumber")


async def test_a_conversion_done_keeps_its_blocks_text_and_pages_and_books_them_once(
    connection: psycopg.AsyncConnection,
) -> None:
    file_id = await a_file(connection)
    conversion_id, job_id = await started(connection, file_id)

    recorded = await record_conversion(
        connection, conversion_id, job_id, converted(), "<!-- p1-b1 -->\nLernfeld 1\n", billable=False
    )
    # the job tried again after its result was in: the conversion done stays as it was
    again = converted().model_copy(update={"engine_version": "9.9"})
    recorded_again = await record_conversion(connection, conversion_id, job_id, again, "", billable=False)

    assert (recorded, recorded_again) == (True, False)
    state = await conversion_for(connection, file_id, "pdfplumber")
    assert state is not None
    assert (state.status, state.pages, state.printed_pages, state.engine_version) == (
        "done",
        2,
        [None, "2"],
        "0.11.10",
    )
    assert state.findings == [
        {"code": "unmapped_symbol", "params": {"codepoint": "U+F0B7", "count": 1, "pages": [1]}}
    ]
    assert await blocks_on_page(connection, conversion_id, 1) == list(converted().blocks[:2])
    assert [block.id for block in await blocks_on_page(connection, conversion_id, 2)] == ["p2-b1"]
    cursor = await connection.execute(
        "SELECT pages, billable FROM conversion_usage WHERE conversion_id = %s", (conversion_id,)
    )
    assert await cursor.fetchall() == [(2, False)]


async def test_a_conversion_refused_ends_with_its_reason(connection: psycopg.AsyncConnection) -> None:
    file_id = await a_file(connection)
    conversion_id, job_id = await started(connection, file_id)

    assert await record_failure(connection, conversion_id, job_id, "needs_ocr")

    state = await conversion_for(connection, file_id, "pdfplumber")
    assert state is not None and (state.status, state.error_code) == ("failed", "needs_ocr")
    assert state.finished_at is not None


@pytest.mark.parametrize(
    ("job_status", "error", "code"),
    [
        ("failed", '{"code": "handler_error"}', "handler_error"),
        ("cancelled", None, "cancelled"),
        # cancelled while waiting for another attempt: its last attempt's code is not why it ended
        ("cancelled", '{"code": "handler_error"}', "cancelled"),
    ],
)
async def test_a_conversion_whose_job_ended_without_it_shows_as_failed(
    connection: psycopg.AsyncConnection, job_status: str, error: str | None, code: str
) -> None:
    file_id = await a_file(connection)
    _, job_id = await started(connection, file_id)
    await connection.execute(
        "UPDATE job SET status = %s, error = %s::jsonb, finished_at = now() WHERE id = %s",
        (job_status, error, job_id),
    )

    state = await conversion_for(connection, file_id, "pdfplumber")

    assert state is not None and (state.status, state.error_code, state.job_status) == (
        "failed",
        code,
        job_status,
    )
    cursor = await connection.execute("SELECT finished_at FROM job WHERE id = %s", (job_id,))
    assert (state.finished_at,) == await cursor.fetchone()  # failed, as one recorded is: with its end


async def test_a_failed_conversion_asked_again_waits_anew_under_its_name(
    connection: psycopg.AsyncConnection,
) -> None:
    file_id = await a_file(connection)
    conversion_id, first_job = await started(connection, file_id)
    await record_failure(connection, conversion_id, first_job, "timed_out")

    again, second_job = await started(connection, file_id)

    state = await conversion_for(connection, file_id, "pdfplumber")
    assert again == conversion_id and second_job != first_job
    assert state is not None and (state.status, state.error_code, state.job_id) == (
        "pending",
        None,
        second_job,
    )


async def test_a_conversion_done_stays_done_whatever_asks_again(connection: psycopg.AsyncConnection) -> None:
    file_id = await a_file(connection)
    conversion_id, first_job = await started(connection, file_id)
    await record_conversion(connection, conversion_id, first_job, converted(), "", billable=False)

    await started(connection, file_id)
    assert not await record_failure(connection, conversion_id, first_job, "died")

    state = await conversion_for(connection, file_id, "pdfplumber")
    assert state is not None and (state.status, state.job_id, state.pages) == ("done", first_job, 2)


async def test_a_job_the_conversion_was_asked_again_without_records_nothing(
    connection: psycopg.AsyncConnection,
) -> None:
    # its lease lost, the job counted as failed, the conversion asked again: the old job, still
    # running somewhere, must not write over what the new one does
    file_id = await a_file(connection)
    conversion_id, old_job = await started(connection, file_id)
    _, new_job = await started(connection, file_id)

    assert not await record_conversion(connection, conversion_id, old_job, converted(), "", billable=False)
    assert not await record_failure(connection, conversion_id, old_job, "died")

    state = await conversion_for(connection, file_id, "pdfplumber")
    assert state is not None and (state.status, state.job_id) == ("pending", new_job)
    assert await blocks_on_page(connection, conversion_id, 1) == []
    cursor = await connection.execute(
        "SELECT count(*) FROM conversion_usage WHERE conversion_id = %s", (conversion_id,)
    )
    assert await cursor.fetchone() == (0,)
