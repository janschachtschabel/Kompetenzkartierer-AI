"""The units of X4 done (app/db/units.py, plan M1 7b): marked in the transaction that writes a unit's
statements; a unit marked already - by another run, or beside this one - is taken, and the
transaction gives way with what it wrote."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest

from app.db.migrate import migrate
from app.db.units import UnitTaken, done_units, mark_unit
from tests.db.l1 import CV, add_conversion, add_document, add_node, add_run, seed_vocabulary
from tests.support import waiting_on_a_lock

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def connect(database_url: str) -> AsyncIterator[Any]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as setup:
        seed_vocabulary(setup)
    opened: list[psycopg.AsyncConnection] = []

    async def make(autocommit: bool = True) -> psycopg.AsyncConnection:
        connection = await psycopg.AsyncConnection.connect(database_url, autocommit=autocommit)
        opened.append(connection)
        return connection

    yield make
    for connection in opened:
        await connection.close()


@pytest.fixture
def made(database_url: str, connect: Any) -> dict[str, Any]:
    with psycopg.connect(database_url, autocommit=True) as setup:
        document = add_document(setup, add_conversion(setup))
        return {"document": document, "run": add_run(setup, document), "node": add_node(setup, document)}


async def test_a_unit_marked_is_done_with_what_it_made(connect: Any, made: dict[str, Any]) -> None:
    db = await connect()

    await mark_unit(
        db,
        made["document"],
        "E2",
        run_id=made["run"],
        node_id=made["node"],
        statements=4,
        checked_absent=[CV + "dock_level"],
    )
    await mark_unit(
        db, made["document"], "E1", run_id=made["run"], node_id=None, statements=0, checked_absent=[]
    )

    done = await done_units(db, made["document"])
    assert sorted(done) == ["E1", "E2"]
    unit = done["E2"]
    assert (unit.key, unit.run_id, unit.node_id, unit.statements, unit.checked_absent) == (
        "E2",
        made["run"],
        made["node"],
        4,
        (CV + "dock_level",),
    )
    assert done["E1"].node_id is None


async def test_a_document_without_units_done_has_none(
    connect: Any, made: dict[str, Any], database_url: str
) -> None:
    with psycopg.connect(database_url, autocommit=True) as setup:  # another document's unit is not its
        other = add_document(setup, add_conversion(setup, b"\x02" * 32))
        other_run = add_run(setup, other)
    db = await connect()
    await mark_unit(db, other, "E1", run_id=other_run, node_id=None, statements=1, checked_absent=[])

    assert await done_units(db, made["document"]) == {}


async def test_a_unit_marked_already_is_taken_and_its_transaction_gives_way(
    connect: Any, made: dict[str, Any]
) -> None:
    db = await connect()
    await mark_unit(
        db, made["document"], "E1", run_id=made["run"], node_id=None, statements=1, checked_absent=[]
    )

    with pytest.raises(UnitTaken):
        async with db.transaction():
            await db.execute(
                "UPDATE document SET title = 'written beside' WHERE id = %s", (made["document"],)
            )
            await mark_unit(
                db, made["document"], "E1", run_id=made["run"], node_id=None, statements=9, checked_absent=[]
            )

    cursor = await db.execute("SELECT title FROM document WHERE id = %s", (made["document"],))
    assert await cursor.fetchone() == (None,)
    assert (await done_units(db, made["document"]))["E1"].statements == 1


@pytest.mark.parametrize("first_commits", [True, False], ids=["committed", "rolled-back"])
async def test_of_two_writers_of_one_unit_side_by_side_one_marks_it(
    connect: Any, made: dict[str, Any], first_commits: bool
) -> None:
    first, second = await connect(autocommit=False), await connect(autocommit=False)
    await mark_unit(
        first, made["document"], "E1", run_id=made["run"], node_id=None, statements=1, checked_absent=[]
    )

    async def second_writer() -> Any:
        try:
            await mark_unit(
                second,
                made["document"],
                "E1",
                run_id=made["run"],
                node_id=None,
                statements=2,
                checked_absent=[],
            )
        except UnitTaken as taken:
            await second.rollback()
            return taken
        await second.commit()
        return "marked"

    writing = asyncio.create_task(second_writer())
    await waiting_on_a_lock(await connect(), second.info.backend_pid)
    await (first.commit() if first_commits else first.rollback())
    outcome = await asyncio.wait_for(writing, 10)

    statements = (await done_units(await connect(), made["document"]))["E1"].statements
    if first_commits:
        assert isinstance(outcome, UnitTaken) and statements == 1
    else:
        assert outcome == "marked" and statements == 2
