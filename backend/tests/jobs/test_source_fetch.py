"""The job source.fetch: a register entry's URL fetched, its file stored and the entry acquired.

The network is a mock transport, or the pinned one over no network at all; the database and the
store are real.
"""

import hashlib
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import httpcore2
import httpx2
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.ids import new_id
from app.core.storage import FileSystemStorage
from app.core.storage_async import AsyncStorage
from app.db.accounts import create_account
from app.db.migrate import migrate
from app.jobs.context import JobContext
from app.jobs.handlers import make_handlers
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, account_lane, claim, enqueue
from app.sources.fetch_job import fetch_source
from app.sources.url_fetch import DownloadError, PinnedBackend, pinned_transport
from tests.sources.compressed import MIB, arriving
from tests.support import make_settings

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

PDF = b"%PDF-1.7 " + b"Lehrplan " * 50
URL = "https://lehrplaene.example/medien/14629?dateiname=Physik.pdf"


@pytest.fixture
async def context(database_url: str, tmp_path: Path) -> AsyncIterator[JobContext]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as pool:
        storage = AsyncStorage(FileSystemStorage(tmp_path / "store"))
        yield JobContext(pool=pool, storage=storage, settings=make_settings(database_url=database_url))


async def add_source(context: JobContext, url: str = URL, title: str = "") -> tuple[UUID, Job]:
    async with context.pool.connection() as connection:
        owner = await create_account(connection, f"Lehrkraft {new_id()}", ["nutzer"])
        source_id = new_id()
        await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (source_id,))
        await connection.execute(
            "INSERT INTO source (id, owner_id, provenance, url, title) VALUES (%s, %s, 'url', %s, %s)",
            (source_id, owner, url, title),
        )
        await enqueue(connection, "source.fetch", account_lane(owner), {"source_id": str(source_id)})
        job = await claim(connection, "w1", ["source.fetch"], 60)
    assert job is not None
    return source_id, job


async def source_row(context: JobContext, source_id: UUID) -> dict[str, Any]:
    async with context.pool.connection() as connection:
        cursor = connection.cursor(row_factory=dict_row)
        await cursor.execute("SELECT * FROM source WHERE id = %s", (source_id,))
        found = await cursor.fetchone()
    assert found is not None
    return found


def serving(handler: Callable[[httpx2.Request], httpx2.Response]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


def pdf_answer(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, content=PDF, headers={"content-type": "application/pdf"})


async def test_a_fetched_file_is_stored_and_the_entry_acquired(context: JobContext) -> None:
    source_id, job = await add_source(context)
    digest = hashlib.sha256(PDF).hexdigest()

    result = await fetch_source(context, job, transport=serving(pdf_answer))

    row = await source_row(context, source_id)
    assert result == {"source_id": str(source_id), "sha256": digest, "size": len(PDF)}
    assert row["register_status"] == "acquired"
    assert row["file_name"] == "Physik.pdf"  # the name the query gave
    assert row["title"] == "Physik"
    assert await context.storage.get(f"sources/{digest}") == PDF


async def test_the_acquisition_keeps_the_way_the_file_came(context: JobContext) -> None:
    source_id, job = await add_source(context, url="https://lehrplaene.example/start")

    def redirecting(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/start":
            return httpx2.Response(302, headers={"location": "/files/lehrplan.pdf"})
        return pdf_answer(request)

    await fetch_source(context, job, transport=serving(redirecting))

    async with context.pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT method, chain, received_name FROM acquisition WHERE source_id = %s", (source_id,)
        )
        rows = await cursor.fetchall()
    assert rows == [
        (
            "url",
            ["https://lehrplaene.example/start", "https://lehrplaene.example/files/lehrplan.pdf"],
            "lehrplan.pdf",
        )
    ]


async def test_a_title_the_entry_has_is_kept(context: JobContext) -> None:
    source_id, job = await add_source(context, title="Kerncurriculum Physik")

    await fetch_source(context, job, transport=serving(pdf_answer))

    assert (await source_row(context, source_id))["title"] == "Kerncurriculum Physik"


async def test_a_refusing_server_makes_the_entry_unreachable(context: JobContext) -> None:
    source_id, job = await add_source(context)

    with pytest.raises(PermanentError) as failed:
        await fetch_source(context, job, transport=serving(lambda request: httpx2.Response(404)))

    assert failed.value.code == "download_refused"
    assert (await source_row(context, source_id))["register_status"] == "unreachable"


async def test_an_address_inside_the_network_is_never_fetched(context: JobContext) -> None:
    source_id, job = await add_source(context, url="http://intern.example/lehrplan.pdf")
    nowhere = pinned_transport(PinnedBackend(lambda host: ["10.0.0.7"], httpcore2.AsyncMockBackend([])))

    with pytest.raises(PermanentError) as failed:
        await fetch_source(context, job, transport=nowhere)

    assert failed.value.code == "url_not_allowed"
    assert (await source_row(context, source_id))["register_status"] == "unreachable"


async def test_a_file_of_no_type_a_conversion_reads_is_not_acquired(context: JobContext) -> None:
    source_id, job = await add_source(context, url="https://lehrplaene.example/seite")

    def html_page(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, content=b"\x89PNG\r\n not a document", headers={"content-type": "image/png"}
        )

    with pytest.raises(PermanentError) as failed:
        await fetch_source(context, job, transport=serving(html_page))

    row = await source_row(context, source_id)
    assert failed.value.code == "unsupported_type"
    assert row["register_status"] == "reachable"  # it answered; its file is of no use here
    assert row["file_id"] is None


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (lambda request: httpx2.Response(200, content=bytes(MIB + 1)), "file_too_large"),
        (lambda request: httpx2.Response(302, headers={"location": "/loop"}), "too_many_redirects"),
        (lambda request: httpx2.Response(302), "bad_answer"),
        (
            lambda request: httpx2.Response(200, content=arriving([PDF]), headers={"content-encoding": "br"}),
            "bad_answer",
        ),
        (
            lambda request: httpx2.Response(302, headers={"location": "https://lehrplaene.example:8o80/"}),
            "bad_answer",
        ),
    ],
    ids=["too-large", "redirect-loop", "redirect-without-address", "unknown-encoding", "unreadable-redirect"],
)
async def test_an_answer_no_attempt_can_use_ends_the_job_and_the_entry_is_reachable(
    context: JobContext, answer: Callable[[httpx2.Request], httpx2.Response], code: str
) -> None:
    # another attempt meets the same answer: three fetches of up to the limit each, for nothing
    source_id, job = await add_source(context)
    one_mib = replace(context, settings=context.settings.model_copy(update={"max_upload_mb": 1}))

    with pytest.raises(PermanentError) as failed:
        await fetch_source(one_mib, job, transport=serving(answer))

    assert failed.value.code == code
    assert (await source_row(context, source_id))["register_status"] == "reachable"


async def test_a_server_away_for_a_moment_is_tried_again(context: JobContext) -> None:
    # not a PermanentError: the queue gives the job another attempt
    source_id, job = await add_source(context)

    with pytest.raises(Exception) as failed:
        await fetch_source(context, job, transport=serving(lambda request: httpx2.Response(503)))

    assert not isinstance(failed.value, PermanentError)
    assert (await source_row(context, source_id))["register_status"] == "unchecked"


async def test_a_server_away_at_the_last_attempt_makes_the_entry_unreachable(context: JobContext) -> None:
    # no attempt is left: the entry must not stay unchecked once the job has failed
    source_id, job = await add_source(context)
    last = replace(job, attempts=job.max_attempts)

    with pytest.raises(DownloadError):
        await fetch_source(context, last, transport=serving(lambda request: httpx2.Response(503)))

    assert (await source_row(context, source_id))["register_status"] == "unreachable"


async def test_the_worker_runs_source_fetch(context: JobContext) -> None:
    assert "source.fetch" in make_handlers(context)


async def test_two_entries_with_the_same_file_share_it(context: JobContext) -> None:
    first, first_job = await add_source(context)
    await fetch_source(context, first_job, transport=serving(pdf_answer))
    second, second_job = await add_source(context)

    await fetch_source(context, second_job, transport=serving(pdf_answer))

    rows = [await source_row(context, first), await source_row(context, second)]
    assert rows[0]["file_id"] == rows[1]["file_id"] is not None
