"""The conversions of register files and their blocks (migration 0011; plan M1, 3.5).

A conversion is asked for in the caller's transaction, under a lock on its file and engine
(lock_conversion): the caller reads what is there (conversion_for), enqueues the job and starts
the conversion with it (start_conversion) - a new one, or a failed one asked again under its
name; one done stays done. The job records the outcome: the blocks, Markdown and pages in one
transaction, booked once (record_conversion), or the reason (record_failure). A conversion still
pending whose job ended without it - failed, cancelled - shows as failed, with the job's code.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.conversion.base import Block, Cell, Conversion

ConversionStatus = Literal["pending", "done", "failed"]
# Why a conversion failed: a refusal of the file (app/conversion/convert.py) or what ended the job
FailureCode = Literal[
    "unreadable",
    "too_many_pages",
    "too_dense",
    "needs_ocr",
    "empty",
    "timed_out",
    "died",
    "crashed",
    "not_pdf",
    "file_gone",
]

_STATE = """
    SELECT c.id, c.source_file_id, c.engine, c.engine_version, c.status, c.error_code, c.account_id,
        c.job_id, j.status AS job_status, j.error ->> 'code' AS job_error, c.pages, c.printed_pages,
        c.findings, c.created_at, c.finished_at
    FROM conversion c LEFT JOIN job j ON j.id = c.job_id
    WHERE c.source_file_id = %s AND c.engine = %s
"""
_START = """
    INSERT INTO conversion (id, source_file_id, engine, account_id, job_id)
    VALUES (%(id)s, %(file)s, %(engine)s, %(account)s, %(job)s)
    ON CONFLICT (source_file_id, engine) DO UPDATE SET status = 'pending', error_code = NULL,
        finished_at = NULL, account_id = EXCLUDED.account_id, job_id = EXCLUDED.job_id
    WHERE conversion.status <> 'done'
"""
_BLOCK = """
    INSERT INTO document_block (conversion_id, block_id, page, seq, kind, text, x0, top, x1, bottom,
        font_size, bold, italic, cells)
    VALUES (%(conversion)s, %(id)s, %(page)s, %(seq)s, %(kind)s, %(text)s, %(x0)s, %(top)s, %(x1)s,
        %(bottom)s, %(font_size)s, %(bold)s, %(italic)s, %(cells)s)
"""
_DONE = """
    UPDATE conversion SET status = 'done', error_code = NULL, engine_version = %(version)s,
        pages = %(pages)s, printed_pages = %(printed)s, findings = %(findings)s, markdown = %(markdown)s,
        finished_at = now()
    WHERE id = %(id)s
"""
_BOOK = """
    INSERT INTO conversion_usage (conversion_id, account_id, engine, pages, billable)
    SELECT id, account_id, engine, %(pages)s, %(billable)s FROM conversion WHERE id = %(id)s
    ON CONFLICT (conversion_id) DO NOTHING
"""
_BLOCKS = """
    SELECT block_id, page, kind, text, x0, top, x1, bottom, font_size, bold, italic, cells
    FROM document_block WHERE conversion_id = %s AND page = %s ORDER BY seq
"""


@dataclass(frozen=True)
class ConversionState:
    id: UUID
    source_file_id: UUID
    engine: str
    engine_version: str | None
    status: ConversionStatus
    error_code: str | None  # a FailureCode, or the code of the job that ended without it
    account_id: UUID | None
    job_id: UUID | None
    job_status: str | None
    pages: int | None
    printed_pages: list[str | None] | None
    findings: list[dict[str, Any]]
    created_at: datetime
    finished_at: datetime | None


async def lock_conversion(connection: psycopg.AsyncConnection, source_file_id: UUID, engine: str) -> None:
    """Hold off another asking for the same conversion until the transaction ends."""
    await connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"conversion:{source_file_id}:{engine}",)
    )


async def conversion_for(
    connection: psycopg.AsyncConnection, source_file_id: UUID, engine: str
) -> ConversionState | None:
    cursor = connection.cursor(row_factory=dict_row)
    await cursor.execute(_STATE, (source_file_id, engine))
    row = await cursor.fetchone()
    if row is None:
        return None
    job_status, job_error = row.pop("job_status"), row.pop("job_error")
    if row["status"] == "pending" and job_status in ("failed", "cancelled"):
        row["status"], row["error_code"] = "failed", job_error or job_status
    return ConversionState(**row, job_status=job_status)


async def start_conversion(
    connection: psycopg.AsyncConnection,
    conversion_id: UUID,
    *,
    source_file_id: UUID,
    engine: str,
    account_id: UUID | None,
    job_id: UUID,
) -> None:
    """The conversion pending with ``job_id``: new under ``conversion_id``, or asked again."""
    await connection.execute(
        "INSERT INTO entity (id, kind) VALUES (%s, 'conversion') ON CONFLICT DO NOTHING", (conversion_id,)
    )
    await connection.execute(
        _START,
        {"id": conversion_id, "file": source_file_id, "engine": engine, "account": account_id, "job": job_id},
    )


async def conversion_target(
    connection: psycopg.AsyncConnection, conversion_id: UUID
) -> tuple[str, str] | None:
    """The store's key of the file to convert, and the engine."""
    cursor = await connection.execute(
        "SELECT f.storage_key, c.engine FROM conversion c JOIN source_file f ON f.id = c.source_file_id"
        " WHERE c.id = %s",
        (conversion_id,),
    )
    found = await cursor.fetchone()
    return None if found is None else (found[0], found[1])


async def record_conversion(
    connection: psycopg.AsyncConnection,
    conversion_id: UUID,
    conversion: Conversion,
    markdown: str,
    *,
    billable: bool,
) -> None:
    async with connection.transaction():
        await connection.execute("DELETE FROM document_block WHERE conversion_id = %s", (conversion_id,))
        async with connection.cursor() as cursor:
            await cursor.executemany(
                _BLOCK,
                [_block_row(conversion_id, seq, block) for seq, block in enumerate(conversion.blocks, 1)],
            )
        await connection.execute(
            _DONE,
            {
                "id": conversion_id,
                "version": conversion.engine_version,
                "pages": conversion.pages,
                "printed": Jsonb(list(conversion.printed_pages)),
                "findings": Jsonb([finding.model_dump() for finding in conversion.findings]),
                "markdown": markdown,
            },
        )
        await connection.execute(
            _BOOK, {"id": conversion_id, "pages": conversion.pages, "billable": billable}
        )


async def record_failure(connection: psycopg.AsyncConnection, conversion_id: UUID, code: FailureCode) -> None:
    await connection.execute(
        "UPDATE conversion SET status = 'failed', error_code = %s, finished_at = now()"
        " WHERE id = %s AND status = 'pending'",
        (code, conversion_id),
    )


async def blocks_on_page(connection: psycopg.AsyncConnection, conversion_id: UUID, page: int) -> list[Block]:
    cursor = connection.cursor(row_factory=dict_row)
    await cursor.execute(_BLOCKS, (conversion_id, page))
    return [
        Block(
            id=row["block_id"],
            page=row["page"],
            kind=row["kind"],
            text=row["text"],
            bbox=(row["x0"], row["top"], row["x1"], row["bottom"]),
            font_size=row["font_size"],
            bold=row["bold"],
            italic=row["italic"],
            cells=tuple(Cell.model_validate(cell) for cell in row["cells"] or ()),
        )
        for row in await cursor.fetchall()
    ]


def _block_row(conversion_id: UUID, seq: int, block: Block) -> dict[str, Any]:
    x0, top, x1, bottom = block.bbox
    return {
        "conversion": conversion_id,
        "id": block.id,
        "page": block.page,
        "seq": seq,
        "kind": block.kind,
        "text": block.text,
        "x0": x0,
        "top": top,
        "x1": x1,
        "bottom": bottom,
        "font_size": block.font_size,
        "bold": block.bold,
        "italic": block.italic,
        "cells": Jsonb([cell.model_dump() for cell in block.cells]) if block.kind == "table" else None,
    }
