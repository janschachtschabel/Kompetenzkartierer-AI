"""A unit of X4 written (plan M1 7b, F4, F10): in one transaction under the attempt's lease - its
statements at its node from where its part of the node begins, its findings, its mark -, or nothing
of it; a unit of no node (a document without headings) gets a node of its own; a unit marked by
another writer gives way."""

import asyncio
from dataclasses import replace
from typing import Any
from uuid import UUID

import psycopg
import pytest

from app.db.findings import Finding
from app.db.nodes import write_subtree
from app.db.runs import RunStart, start_run
from app.db.units import UnitTaken, done_units, mark_unit
from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft
from app.jobs.queue import LeaseLost
from app.pipeline.statement_read import ReadStatement
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x4_read import UnitReading
from app.pipeline.x4_unit import first_position, write_unit
from tests.pipeline.test_run import CV, a_document, a_job, rows, setup
from tests.support import waiting_on_a_lock

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run


def package(key: str, node: UUID | None, first: str = "p2-b2", last: str = "p2-b2") -> WorkPackage:
    return WorkPackage(key, node, 3, 3, first, last, (2, 2), ("Kompetenzen",), "full", "statements")


def statement(
    verbatim: str, kind: str = "kind_learningOutcome", targets: tuple[int, ...] = ()
) -> ReadStatement:
    draft = StatementDraft(
        verbatim=verbatim,
        kind=CV + kind,
        addressees=(CV + "addr_learner",),
        anchors=(AnchorDraft(("p2-b2",), page_start=2),),
        origin=CV + "orig_model",
        review_status=CV + "rev_proposed",
    )
    return ReadStatement(draft, 3, targets)


def read(
    *statements: ReadStatement, absent: tuple[str, ...] = (), findings: tuple[Finding, ...] = ()
) -> UnitReading:
    return UnitReading(list(statements), absent, list(findings))


async def ready(connection: psycopg.AsyncConnection) -> tuple[Any, Any, UUID, UUID]:
    """A document with a node at its heading p2-b1, a job claimed, a run of X4."""
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    root = NodeDraft(
        function=CV + "fn_area",
        origin=CV + "orig_model",
        review_status=CV + "rev_proposed",
        original_title="Kompetenzen",
        anchors=(AnchorDraft(("p2-b1",), page_start=2),),
    )
    node = await write_subtree(connection, document.id, root)
    run = await start_run(connection, RunStart(document.id, job.id, 1, "X4", None, None, None, None))
    return document, job, node, run


async def statements_of(connection: psycopg.AsyncConnection, document: Any) -> list[tuple[Any, ...]]:
    return await rows(
        connection,
        "SELECT node_id, position, verbatim, details FROM statement WHERE document_id = %s ORDER BY position",
        document.id,
    )


def test_a_unit_s_statements_begin_where_its_part_of_its_node_does() -> None:
    node, other = UUID(int=1), UUID(int=2)
    packages = [package("E1", other), package("E2", node), package("E3", node), package("E4", node)]

    assert [first_position(item, packages) for item in packages] == [1, 1, 10_001, 20_001]


async def test_a_unit_is_written_at_its_node_with_its_findings_and_its_mark(setup: Any) -> None:
    _, connection = setup
    document, job, node, run = await ready(connection)
    finding = Finding("x4.value_from_surroundings", "info", document.id, "inherited", "$.statements")

    written = await write_unit(
        connection,
        job,
        document,
        package("E2", node),
        read(
            statement("erklären", targets=(1,)),
            statement("Licht", kind="kind_content"),
            absent=(CV + "dock_level",),
            findings=(finding,),
        ),
        first=10_001,
        run_id=run,
    )

    assert written == 2
    assert await statements_of(connection, document) == [
        (node, 10_001, "erklären", {"targetsContent": [10_002]}),
        (node, 10_002, "Licht", {}),
    ]
    assert await rows(connection, "SELECT rule, run_id FROM validation_finding") == [
        ("x4.value_from_surroundings", run)
    ]
    done = (await done_units(connection, document.id))["E2"]
    assert (done.run_id, done.node_id, done.statements, done.checked_absent) == (
        run, node, 2, (CV + "dock_level",),
    )  # fmt: skip


async def test_a_unit_of_no_node_gets_a_node_of_its_own(setup: Any) -> None:
    _, connection = setup
    document, job, _, run = await ready(connection)
    document = replace(document, title="Kernlehrplan Physik")

    await write_unit(
        connection,
        job,
        document,
        package("E1", None, "p1-b1", "p3-b2"),
        read(statement("Licht", kind="kind_content"), statement("erklären", targets=(0,))),
        first=10_001,  # its own node holds it alone: from 1 on whatever its part
        run_id=run,
    )

    [(node, title, function, origin, rule, made_by)] = await rows(
        connection,
        "SELECT id, original_title, replace(function_iri, %s, ''), replace(origin_iri, %s, ''), rule_id,"
        " run_id FROM node WHERE document_id = %s AND original_title <> 'Kompetenzen'",
        CV,
        CV,
        document.id,
    )
    assert (title, function, origin, rule, made_by) == (
        "Kernlehrplan Physik", "fn_unit", "orig_rule", "x4.unit_without_node", run,
    )  # fmt: skip
    assert await rows(
        connection,
        "SELECT b.block_id FROM anchor a JOIN anchor_block b ON b.anchor_id = a.id WHERE a.node_id = %s",
        node,
    ) == [("p1-b1",)]
    assert [
        (at, position, details) for at, position, _, details in await statements_of(connection, document)
    ] == [
        (node, 1, {}),
        (node, 2, {"targetsContent": [1]}),
    ]
    assert (await done_units(connection, document.id))["E1"].node_id == node


async def test_a_unit_of_no_node_in_a_document_of_no_title_is_named_the_document(setup: Any) -> None:
    _, connection = setup
    document, job, _, run = await ready(connection)

    await write_unit(
        connection, job, document, package("E1", None, "p1-b1", "p3-b2"), read(statement("erklären")),
        first=1, run_id=run,
    )  # fmt: skip

    assert await rows(
        connection, "SELECT original_title FROM node WHERE rule_id = 'x4.unit_without_node'"
    ) == [("Dokument",)]


async def test_of_two_writers_of_one_unit_side_by_side_the_second_waits_and_gives_way(
    setup: Any, database_url: str
) -> None:
    # two jobs on one document: its statements would meet the first one's at their positions, so the
    # mark is met first, and the second waits there
    _, connection = setup
    document, job, node, run = await ready(connection)
    other = await a_job(connection, document.id, document.owner_id)
    first = await psycopg.AsyncConnection.connect(database_url)
    second = await psycopg.AsyncConnection.connect(database_url, autocommit=True)
    try:
        async with first.transaction():
            await write_unit(
                first, job, document, package("E2", node), read(statement("erklären")), first=1, run_id=run
            )
            writing = asyncio.create_task(
                write_unit(
                    second,
                    other,
                    document,
                    package("E2", node),
                    read(statement("erklären")),
                    first=1,
                    run_id=run,
                )
            )
            await waiting_on_a_lock(connection, second.info.backend_pid)
        with pytest.raises(UnitTaken):
            await asyncio.wait_for(writing, 10)
    finally:
        await first.close()
        await second.close()

    assert [
        (position, verbatim) for _, position, verbatim, _ in await statements_of(connection, document)
    ] == [(1, "erklären")]


async def test_a_unit_marked_by_another_writer_gives_way_with_what_it_wrote(setup: Any) -> None:
    _, connection = setup
    document, job, node, run = await ready(connection)
    await mark_unit(connection, document.id, "E2", run_id=run, node_id=node, statements=0, checked_absent=[])

    with pytest.raises(UnitTaken):
        await write_unit(
            connection, job, document, package("E2", node), read(statement("erklären")), first=1, run_id=run
        )

    assert await statements_of(connection, document) == []


async def test_a_unit_whose_mark_is_refused_writes_nothing_of_it(setup: Any) -> None:
    # a unit of no node is marked after its node and statements: they are taken back with it
    _, connection = setup
    document, job, _, run = await ready(connection)
    no_docking_point = (CV + "addr_learner",)

    with pytest.raises(psycopg.errors.CheckViolation):
        refused = read(statement("erklären"), absent=no_docking_point)
        await write_unit(connection, job, document, package("E1", None), refused, first=1, run_id=run)

    assert await statements_of(connection, document) == []
    assert await rows(connection, "SELECT count(*) FROM node WHERE document_id = %s", document.id) == [(1,)]
    assert await done_units(connection, document.id) == {}


async def test_an_attempt_that_lost_its_lease_writes_nothing_of_the_unit(setup: Any) -> None:
    _, connection = setup
    document, job, node, run = await ready(connection)
    await connection.execute(
        "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
    )

    with pytest.raises(LeaseLost):
        await write_unit(
            connection, job, document, package("E2", node), read(statement("erklären")), first=1, run_id=run
        )

    assert (await statements_of(connection, document), await done_units(connection, document.id)) == ([], {})
