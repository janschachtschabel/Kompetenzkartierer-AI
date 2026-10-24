"""What a stage finds on a document, written with its run (plan M1 6.2, app/db/findings.py): a profile
value outside the profile, a block nobody showed, a work it may be an edition of - findings, not
failures of the run."""

from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest

from app.db.findings import MOST_MESSAGE_SIGNS, Finding, add_findings
from app.db.migrate import migrate
from app.db.runs import RunStart, start_run
from tests.db.l1 import add_conversion, add_document, seed_vocabulary

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as setup:
        seed_vocabulary(setup)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


@pytest.fixture
def made(database_url: str, connection: psycopg.AsyncConnection) -> dict[str, Any]:
    with psycopg.connect(database_url, autocommit=True) as setup:
        made = add_conversion(setup)
        made["document"] = add_document(setup, made)
    return made


async def test_a_stage_s_findings_are_kept_with_its_run(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    document = made["document"]
    run = await start_run(
        connection,
        RunStart(document, None, None, "X1", None, None, None, None),
    )

    await add_findings(
        connection,
        document,
        run,
        [
            Finding(
                "x1.not_in_profile",
                "warning",
                document,
                "Dokumenttyp nicht im Profil",
                path="documentType",
                details={"value": "D9"},
            ),
            Finding("x1.work_suggestion", "info", document, "x" * (MOST_MESSAGE_SIGNS + 50)),
        ],
    )

    cursor = await connection.execute(
        "SELECT rule, severity, focus_id, path, details, length(message), run_id FROM validation_finding"
        " ORDER BY rule"
    )
    assert await cursor.fetchall() == [
        ("x1.not_in_profile", "warning", document, "documentType", {"value": "D9"}, 27, run),
        ("x1.work_suggestion", "info", document, None, {}, MOST_MESSAGE_SIGNS, run),
    ]


async def test_no_findings_write_nothing(connection: psycopg.AsyncConnection, made: dict[str, Any]) -> None:
    await add_findings(connection, made["document"], None, [])

    cursor = await connection.execute("SELECT count(*) FROM validation_finding")
    assert await cursor.fetchone() == (0,)
