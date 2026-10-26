"""A work package written anew by X6 (plan M1 8b, Festlegung F4): in one transaction under the attempt's
lease and, first, the tree's lock, the statements the model wrote and nobody touched since go, the new
ones come after every position the package used - but none the editors hold already, changed,
confirmed or rejected -, the reading's old findings of the package make way for the new, and its mark
names the repair; or nothing of it is written."""

import asyncio
from typing import Any
from uuid import UUID

import psycopg
import pytest

from app.db.findings import Finding, add_findings
from app.db.nodes import lock_tree
from app.db.runs import RunStart, start_run
from app.db.units import done_units
from app.jobs.queue import LeaseLost
from app.pipeline.x4_unit import PART, write_unit
from app.pipeline.x6_unit import EmptyAnswer, Rewritten, rewrite_unit
from app.pipeline.x6_units import RepairUnit
from tests.pipeline.test_run import CV, rows, setup
from tests.pipeline.test_x4_unit import package, read, ready, statement, statements_of
from tests.support import waiting_on_a_lock

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run


async def written(connection: psycopg.AsyncConnection) -> tuple[Any, Any, UUID, UUID, RepairUnit]:
    """The ready document's package E2 at its node written by X4 - "Aussage alt", "Erklären alt",
    "Licht alt" at 1 to 3 -, a run of X6, and the package as a repair takes it."""
    document, job, node, x4 = await ready(connection)
    unit = package("E2", node)
    old = read(
        statement("Aussage alt"), statement("Erklären alt"), statement("Licht alt", kind="kind_content")
    )
    await write_unit(connection, job, document, unit, old, first=1, run_id=x4)
    x6 = await start_run(connection, RunStart(document.id, job.id, 1, "X6", None, None, None, None))
    return document, job, node, x6, RepairUnit(unit, node, 1, (), ())


async def test_a_package_written_anew_has_its_new_statements_after_all_it_used(setup: Any) -> None:
    _, connection = setup
    document, job, node, x6, unit = await written(connection)

    made = await rewrite_unit(
        connection, job, document, unit,
        read(statement("Neu erklären", targets=(1,)), statement("Neues Licht", kind="kind_content"),
             absent=(CV + "dock_time",)),
        run_id=x6,
    )  # fmt: skip

    assert made == Rewritten(statements=2, dropped=0)
    assert [
        (at, verbatim, details) for _, at, verbatim, details in await statements_of(connection, document)
    ] == [
        (4, "Neu erklären", {"targetsContent": [5]}),
        (5, "Neues Licht", {}),
    ]
    done = (await done_units(connection, document.id))["E2"]
    assert (done.run_id, done.node_id, done.statements, done.checked_absent, done.repairs) == (
        x6, node, 2, (CV + "dock_time",), 1,
    )  # fmt: skip


async def test_the_statements_the_editors_hold_stay_and_are_not_written_twice(setup: Any) -> None:
    _, connection = setup
    document, job, _, x6, unit = await written(connection)
    await connection.execute(
        "UPDATE statement SET revision = 2 WHERE verbatim = 'Aussage alt' AND document_id = %s",
        (document.id,),
    )
    await connection.execute(
        "UPDATE statement SET review_status_iri = %s WHERE verbatim = 'Erklären alt' AND document_id = %s",
        (CV + "rev_rejected", document.id),
    )

    made = await rewrite_unit(
        connection, job, document, unit,
        read(statement("Aussage alt"), statement("Erklären alt"), statement("Neu", targets=(1, 3)),
             statement("Neues Licht", kind="kind_content")),
        run_id=x6,
    )  # fmt: skip

    assert made == Rewritten(statements=2, dropped=2)
    assert [
        (at, verbatim, details) for _, at, verbatim, details in await statements_of(connection, document)
    ] == [
        (1, "Aussage alt", {}),
        (2, "Erklären alt", {}),
        (4, "Neu", {"targetsContent": [5]}),  # not to the one left out; the other's place moved up
        (5, "Neues Licht", {}),
    ]
    assert (await done_units(connection, document.id))["E2"].statements == 4


async def test_a_new_statement_points_to_the_content_the_editors_hold_in_its_place(setup: Any) -> None:
    # the answer's content statement is left out for the confirmed one of its wording: the pointer
    # to it goes to that one; to a rejected one it goes nowhere (above)
    _, connection = setup
    document, job, _, x6, unit = await written(connection)
    await connection.execute(
        "UPDATE statement SET review_status_iri = %s WHERE verbatim = 'Licht alt' AND document_id = %s",
        (CV + "rev_confirmed", document.id),
    )

    made = await rewrite_unit(
        connection, job, document, unit,
        read(statement("Licht alt", kind="kind_content"), statement("Neu erklären", targets=(0,))),
        run_id=x6,
    )  # fmt: skip

    assert made == Rewritten(statements=1, dropped=1)
    assert [
        (at, verbatim, details) for _, at, verbatim, details in await statements_of(connection, document)
    ] == [
        (3, "Licht alt", {}),
        (4, "Neu erklären", {"targetsContent": [3]}),
    ]


async def test_an_answer_of_no_statement_leaves_a_package_that_had_some_as_it_was(setup: Any) -> None:
    # the model was asked for all of them: none at all is an answer that lost them, not a package
    # without statements (the repair is counted by the caller, app/pipeline/x6_repair.py)
    _, connection = setup
    document, job, _, x6, unit = await written(connection)
    before = await statements_of(connection, document)

    with pytest.raises(EmptyAnswer):
        await rewrite_unit(connection, job, document, unit, read(), run_id=x6)

    assert await statements_of(connection, document) == before
    assert (await done_units(connection, document.id))["E2"].repairs == 0


async def test_an_answer_of_no_statement_is_written_where_the_editors_hold_them_all(setup: Any) -> None:
    _, connection = setup
    document, job, _, x6, unit = await written(connection)
    await connection.execute("UPDATE statement SET revision = 2 WHERE document_id = %s", (document.id,))

    made = await rewrite_unit(connection, job, document, unit, read(), run_id=x6)

    assert made == Rewritten(statements=0, dropped=0)
    assert len(await statements_of(connection, document)) == 3
    assert (await done_units(connection, document.id))["E2"].repairs == 1


async def test_a_part_of_a_parted_node_is_written_anew_without_the_other(setup: Any) -> None:
    # E2 and E3 share a node, each in its part of the positions (app/pipeline/x4_unit.py)
    _, connection = setup
    document, job, node, x4 = await ready(connection)
    first, second = package("E2", node), package("E3", node)
    await write_unit(connection, job, document, first, read(statement("Erster Teil")), first=1, run_id=x4)
    await write_unit(
        connection, job, document, second, read(statement("Zweiter Teil")), first=PART + 1, run_id=x4
    )
    x6 = await start_run(connection, RunStart(document.id, job.id, 1, "X6", None, None, None, None))

    await rewrite_unit(
        connection, job, document, RepairUnit(second, node, PART + 1, (), ()), read(statement("Zweiter neu")),
        run_id=x6,
    )  # fmt: skip
    await rewrite_unit(
        connection, job, document, RepairUnit(first, node, 1, (), ()), read(statement("Erster neu")),
        run_id=x6,
    )  # fmt: skip

    assert [(at, verbatim) for _, at, verbatim, _ in await statements_of(connection, document)] == [
        (2, "Erster neu"),
        (PART + 2, "Zweiter neu"),
    ]


async def test_a_package_of_a_node_of_its_own_is_written_anew_whole(setup: Any) -> None:
    # under no heading X4 gave it a node of its own: every position there is the package's
    _, connection = setup
    document, job, _, x4 = await ready(connection)
    alone = package("E1", None, first="p2-b1", last="p2-b1")
    await write_unit(connection, job, document, alone, read(statement("Allein")), first=1, run_id=x4)
    own = (await done_units(connection, document.id))["E1"].node_id
    assert own is not None
    await connection.execute(
        "UPDATE statement SET position = %s WHERE node_id = %s", (3 * PART, own)
    )  # however far it lies
    x6 = await start_run(connection, RunStart(document.id, job.id, 1, "X6", None, None, None, None))

    await rewrite_unit(
        connection, job, document, RepairUnit(alone, own, 1, (), ()), read(statement("Allein neu")), run_id=x6
    )

    assert [(node, verbatim) for node, _, verbatim, _ in await statements_of(connection, document)] == [
        (own, "Allein neu"),
    ]


async def test_the_package_s_old_reading_findings_make_way_for_the_new(setup: Any) -> None:
    _, connection = setup
    document, job, _, x6, unit = await written(connection)
    [(x4,)] = await rows(connection, "SELECT run_id FROM extraction_unit WHERE unit_key = 'E2'")
    earlier = await start_run(connection, RunStart(document.id, job.id, 1, "X6", None, None, None, None))
    await add_findings(connection, document.id, earlier, [
        Finding("x6.unknown_block", "warning", document.id, "an earlier repair's", details={"unit": "E2"}),
    ])  # fmt: skip
    await add_findings(connection, document.id, x4, [
        Finding("x4.unknown_block", "warning", document.id, "old", details={"unit": "E2"}),
        Finding("x4.unknown_block", "warning", document.id, "another package's", details={"unit": "E3"}),
    ])  # fmt: skip
    new = Finding("x6.value_cut", "info", document.id, "new", details={"unit": "E2"})

    await rewrite_unit(connection, job, document, unit, read(statement("Neu"), findings=(new,)), run_id=x6)

    found = await rows(connection, "SELECT message, run_id FROM validation_finding ORDER BY message")
    assert found == [("another package's", x4), ("new", x6)]


async def test_a_package_whose_attempt_lost_its_lease_is_left_as_it_was(setup: Any) -> None:
    _, connection = setup
    document, job, _, x6, unit = await written(connection)
    before = await statements_of(connection, document)
    await connection.execute(
        "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
    )

    with pytest.raises(LeaseLost):
        await rewrite_unit(connection, job, document, unit, read(statement("Neu")), run_id=x6)

    assert await statements_of(connection, document) == before
    assert (await done_units(connection, document.id))["E2"].repairs == 0


async def test_a_package_written_anew_waits_for_the_tree_before_it_reads_its_statements(
    setup: Any, database_url: str
) -> None:
    # whoever changes a tree takes its lock first (plan M1, Paket 4): an editor's change of the package's
    # statements is in, or not begun, when the repair reads which of them it may take away
    _, connection = setup
    document, job, _, x6, unit = await written(connection)
    editor = await psycopg.AsyncConnection.connect(database_url)
    writer = await psycopg.AsyncConnection.connect(database_url, autocommit=True)
    try:
        async with editor.transaction():
            await lock_tree(editor, document.id)
            rewriting = asyncio.create_task(
                rewrite_unit(writer, job, document, unit, read(statement("Neu")), run_id=x6)
            )
            await waiting_on_a_lock(connection, writer.info.backend_pid)
            await editor.execute(
                "UPDATE statement SET revision = 2 WHERE verbatim = 'Licht alt' AND document_id = %s",
                (document.id,),
            )
        await asyncio.wait_for(rewriting, 10)
    finally:
        await editor.close()
        await writer.close()

    assert [verbatim for _, _, verbatim, _ in await statements_of(connection, document)] == [
        "Licht alt",
        "Neu",
    ]
