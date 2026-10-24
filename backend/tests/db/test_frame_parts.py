"""Frame parts as X3 writes them (app/db/frame_parts.py, plan M1 7b): each with its content, how it
came, the run that made it and its anchor, in the caller's transaction; read back in the order
they were written."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import psycopg
import pytest

from app.db import anchors
from app.db.frame_parts import FramePartDraft, frame_parts_of, write_frame_parts
from app.db.migrate import migrate
from app.domain.l1 import AnchorDraft
from tests.db.l1 import CV, add_conversion, add_document, add_run, seed_vocabulary

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

MODEL, RULE, PROPOSED = CV + "orig_model", CV + "orig_rule", CV + "rev_proposed"


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
        made["run"] = add_run(setup, made["document"], "stage_X3")
    return made


def draft(
    kind: Any, content: dict[str, Any], origin: str = MODEL, rule_id: str | None = None
) -> FramePartDraft:
    anchor = AnchorDraft(block_ids=("p1-b1",), page_start=1)
    return FramePartDraft(kind, content, anchor, origin=origin, review_status=PROPOSED, rule_id=rule_id)


async def rows(connection: psycopg.AsyncConnection, query: str, *params: Any) -> list[tuple[Any, ...]]:
    cursor = await connection.execute(query, params)
    return await cursor.fetchall()


async def test_frame_parts_are_written_with_what_they_hold_and_where_they_stand(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    drafts = [
        draft("operators", {"lemma": "beschreiben", "definition": None, "taskDemandText": "I"}),
        draft("crossCuttingLegend", {"marker": "BNE", "label": "Bildung für nachhaltige Entwicklung"}),
    ]

    async with connection.transaction():
        ids = await write_frame_parts(
            connection, made["document"], made["conversion"], drafts, run_id=made["run"]
        )

    parts = await frame_parts_of(connection, made["document"])
    assert [(part.id, part.kind, part.content, part.run_id) for part in parts] == [
        (
            ids[0],
            "operators",
            {"lemma": "beschreiben", "definition": None, "taskDemandText": "I"},
            made["run"],
        ),
        (
            ids[1],
            "crossCuttingLegend",
            {"marker": "BNE", "label": "Bildung für nachhaltige Entwicklung"},
            made["run"],
        ),
    ]
    assert await rows(
        connection,
        "SELECT p.origin_iri, p.review_status_iri, a.page_start, b.block_id FROM frame_part p"
        " JOIN anchor a ON a.frame_part_id = p.id JOIN anchor_block b ON b.anchor_id = a.id"
        " WHERE p.document_id = %s ORDER BY p.id",
        made["document"],
    ) == [(MODEL, PROPOSED, 1, "p1-b1"), (MODEL, PROPOSED, 1, "p1-b1")]


async def test_frame_parts_are_read_in_the_order_written_whatever_their_ids(
    connection: psycopg.AsyncConnection, made: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # ids of one millisecond sort by their random bits (app/core/ids.py): here the later ones lower
    falling = iter(UUID(int=(1 << 100) - number) for number in range(1, 100))
    monkeypatch.setattr(anchors, "new_id", lambda: next(falling))
    drafts = [draft("operators", {"lemma": lemma}) for lemma in ("beschreiben", "erklären", "nennen")]

    async with connection.transaction():
        await write_frame_parts(connection, made["document"], made["conversion"], drafts, run_id=made["run"])

    parts = await frame_parts_of(connection, made["document"])
    assert [part.content["lemma"] for part in parts] == ["beschreiben", "erklären", "nennen"]


async def test_frame_parts_written_later_stand_after_those_there_are(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    for lemma in ("beschreiben", "erklären"):
        async with connection.transaction():
            await write_frame_parts(
                connection, made["document"], made["conversion"], [draft("operators", {"lemma": lemma})],
                run_id=made["run"],
            )  # fmt: skip

    assert await rows(
        connection, "SELECT position, content ->> 'lemma' FROM frame_part ORDER BY position"
    ) == [(1, "beschreiben"), (2, "erklären")]


async def test_a_frame_part_a_rule_gave_names_its_rule(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    async with connection.transaction():
        await write_frame_parts(
            connection,
            made["document"],
            made["conversion"],
            [draft("rules", {"verbatim": "Zwei der vier Fächer"}, RULE, "x3.example_rule")],
            run_id=made["run"],
        )

    assert await rows(connection, "SELECT origin_iri, rule_id FROM frame_part") == [(RULE, "x3.example_rule")]


async def test_frame_parts_are_written_in_the_caller_s_transaction(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    with pytest.raises(RuntimeError):
        async with connection.transaction():
            await write_frame_parts(
                connection,
                made["document"],
                made["conversion"],
                [draft("levelModels", {"title": "Niveaustufen"})],
                run_id=made["run"],
            )
            raise RuntimeError("the stage broke after it")

    assert await frame_parts_of(connection, made["document"]) == []
    assert await rows(connection, "SELECT count(*) FROM anchor") == [(0,)]


async def test_another_document_s_frame_parts_are_not_its(
    connection: psycopg.AsyncConnection, made: dict[str, Any], database_url: str
) -> None:
    with psycopg.connect(database_url, autocommit=True) as setup:
        other = add_document(setup, add_conversion(setup, b"\x02" * 32))
    async with connection.transaction():
        await write_frame_parts(
            connection,
            made["document"],
            made["conversion"],
            [draft("rules", {"verbatim": "x"})],
            run_id=made["run"],
        )

    assert await frame_parts_of(connection, other) == []
