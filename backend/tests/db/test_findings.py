"""What a stage finds on a document, written with its run (plan M1 6.2, app/db/findings.py): a profile
value outside the profile, a block nobody showed, a work it may be an edition of - findings, not
failures of the run."""

from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest

from app.db.findings import (
    MOST_MESSAGE_SIGNS,
    Finding,
    FindingRow,
    add_findings,
    drop_stage_findings,
    findings_of,
)
from app.db.migrate import migrate
from app.db.runs import RunStart, start_run
from tests.db.l1 import add_conversion, add_document, add_node, add_run, add_statement, seed_vocabulary

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


def a_tree(
    database_url: str, made: dict[str, Any], verbatim: str = "Die Lernenden beschreiben Licht."
) -> Any:
    """The document's node "Optik" with one statement, and runs of X4 and X5."""
    with psycopg.connect(database_url, autocommit=True) as setup:
        node = add_node(setup, made["document"], original_title="Optik")
        statement = add_statement(setup, made["document"], node, verbatim=verbatim)
        return (
            node,
            statement,
            add_run(setup, made["document"], "stage_X4"),
            add_run(setup, made["document"], "stage_X5"),
        )


async def test_a_document_s_findings_are_read_gravest_first_each_with_the_row_it_is_about(
    connection: psycopg.AsyncConnection, made: dict[str, Any], database_url: str
) -> None:
    document = made["document"]
    node, statement, x4, x5 = a_tree(database_url, made)
    await add_findings(connection, document, x5, [
        Finding("x5.unit_without_statements", "info", document, "a unit read whole holds no statement",
                details={"unit": "E3"}),
        Finding("x5.retired_value", "warning", node, "a value the vocabularies have retired",
                path="cur:nodeType"),
        Finding("x5.wording_not_found", "violation", statement, "the wording is not in the blocks"),
        Finding("shacl.StatementPlausibilityShape", "warning", statement, "Fundstelle unscharf gefunden."),
    ])  # fmt: skip
    await add_findings(connection, document, x4, [
        Finding("x4.unknown_block", "warning", document, "a block id nobody showed", path="statements[0]",
                details={"unit": "E2"}),
    ])  # fmt: skip
    with psycopg.connect(database_url, autocommit=True) as setup:
        other = add_document(setup, made)
    await add_findings(
        connection, other, None, [Finding("x1.unknown_value", "violation", other, "elsewhere")]
    )

    page = await findings_of(connection, document)

    assert page.rows == [
        FindingRow("x5.wording_not_found", "violation", "X5", "statement", statement,
                   "Die Lernenden beschreiben Licht.", None, "the wording is not in the blocks", None),
        FindingRow("x4.unknown_block", "warning", "X4", "document", document, None, "statements[0]",
                   "a block id nobody showed", "E2"),  # an earlier stage first, whatever its rule
        FindingRow("shacl.StatementPlausibilityShape", "warning", "X5", "statement", statement,
                   "Die Lernenden beschreiben Licht.", None, "Fundstelle unscharf gefunden.", None),
        FindingRow("x5.retired_value", "warning", "X5", "node", node, "Optik", "cur:nodeType",
                   "a value the vocabularies have retired", None),
        FindingRow("x5.unit_without_statements", "info", "X5", "document", document, None, None,
                   "a unit read whole holds no statement", "E3"),
    ]  # fmt: skip
    assert (page.counts, page.truncated) == ({"violation": 1, "warning": 3, "info": 1}, False)


async def test_the_findings_read_stop_at_the_most_asked_and_say_so(
    connection: psycopg.AsyncConnection, made: dict[str, Any], database_url: str
) -> None:
    document = made["document"]
    *_, x5 = a_tree(database_url, made)
    await add_findings(
        connection, document, x5, [Finding(f"x5.rule_{at}", "info", document, "found") for at in range(3)]
    )

    page = await findings_of(connection, document, most=2)

    assert ([row.rule for row in page.rows], page.counts, page.truncated) == (
        ["x5.rule_0", "x5.rule_1"],
        {"violation": 0, "warning": 0, "info": 3},
        True,
    )


async def test_a_finding_s_label_is_cut_to_what_a_list_shows(
    connection: psycopg.AsyncConnection, made: dict[str, Any], database_url: str
) -> None:
    _, statement, _, x5 = a_tree(database_url, made, verbatim="Licht " * 60)
    await add_findings(connection, made["document"], x5, [Finding("x5.rule", "warning", statement, "found")])

    [row] = (await findings_of(connection, made["document"])).rows

    assert row.focus_label == ("Licht " * 60)[:160]


async def test_a_stage_s_earlier_findings_are_dropped_and_every_other_kept(
    connection: psycopg.AsyncConnection, made: dict[str, Any], database_url: str
) -> None:
    document = made["document"]
    _, _, x4, earlier = a_tree(database_url, made)
    with psycopg.connect(database_url, autocommit=True) as setup:
        later = add_run(setup, document, "stage_X5")
        other = add_document(setup, made)
        elsewhere = add_run(setup, other, "stage_X5")
    for run, owner in ((earlier, document), (later, document), (x4, document), (elsewhere, other)):
        await add_findings(connection, owner, run, [Finding("x5.rule", "warning", owner, str(run))])

    dropped = await drop_stage_findings(connection, document, "X5", keep_run=later)

    cursor = await connection.execute("SELECT run_id FROM validation_finding ORDER BY message")
    assert (dropped, sorted(run for (run,) in await cursor.fetchall())) == (1, sorted([later, x4, elsewhere]))
