"""A document of the first layer over blocks of the test's own, made as the app makes one: an account's
uploaded source, its file converted (a job asked for it, the conversion recorded with the blocks),
the document created of that conversion."""

from collections.abc import Sequence

import psycopg

from app.conversion.base import Block, Conversion
from app.core.ids import new_id
from app.db.conversions import record_conversion, start_conversion
from app.db.documents import Document, create_document
from app.db.source_queries import Reader
from app.jobs.queue import enqueue


async def document_of(
    connection: psycopg.AsyncConnection,
    blocks: Sequence[Block],
    *,
    sector: str = "school",
    regions: Sequence[str] = ("DE-NW",),
    printed_pages: Sequence[str | None] | None = None,
) -> Document:
    owner, file_id, source, conversion_id = new_id(), new_id(), new_id(), new_id()
    await connection.execute(
        "INSERT INTO account (id, name) VALUES (%s, %s)", (owner, f"konto-{owner.hex[-12:]}")
    )
    await connection.execute(
        "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 1, %s)",
        (file_id, new_id().bytes * 2, f"sources/{file_id.hex}"),
    )
    await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (source,))
    await connection.execute(
        "INSERT INTO source (id, owner_id, provenance, register_status, file_id, file_name, mime)"
        " VALUES (%s, %s, 'upload', 'acquired', %s, 'plan.pdf', 'application/pdf')",
        (source, owner, file_id),
    )
    job_id = await enqueue(connection, "source.convert", "test", {"conversion_id": str(conversion_id)})
    await start_conversion(
        connection,
        conversion_id,
        source_file_id=file_id,
        engine="pdfplumber",
        account_id=owner,
        job_id=job_id,
    )
    pages = max(block.page for block in blocks)
    conversion = Conversion(
        engine="pdfplumber",
        engine_version="0.11.10",
        pages=pages,
        printed_pages=tuple(printed_pages if printed_pages is not None else [None] * pages),
        blocks=tuple(blocks),
        findings=(),
    )
    assert await record_conversion(connection, conversion_id, job_id, conversion, "", billable=False)
    return await create_document(
        connection,
        Reader(owner, sees_all=False),
        third_party_content=False,
        source_id=source,
        conversion_id=conversion_id,
        sector=sector,
        regions=regions,
    )
