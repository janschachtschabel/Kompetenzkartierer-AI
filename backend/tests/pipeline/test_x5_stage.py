"""X5 in the job extract.run (plan M1 8.5): after X4, no model asked - each anchor's wording checked
against its blocks and its match kind written, the plausibility checks, the document's Kern graph
against the shapes in a child - its findings rows of the document, each on the row it is about, written
with the run's end under the lease. A model stands in for X1 to X4."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.db.anchors import CheckedAnchor, UncheckedAnchor, unchecked_anchors
from app.db.findings import Finding
from app.db.nodes import lock_tree
from app.db.runs import RunStart, finish_run, start_run
from app.jobs.queue import LeaseLost
from app.pipeline import run, x5_stage
from app.pipeline.anchor_check import AnchorMatch
from app.pipeline.run import extract_document
from app.pipeline.shacl import ShaclTimeout
from tests.pipeline.test_run import CV, PLAIN, Model, a_document, a_job, context_of, rows, setup

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run


async def x5_runs(connection: Any, document: Any) -> list[tuple[Any, ...]]:
    return await rows(
        connection,
        "SELECT outcome, result FROM extraction_run WHERE document_id = %s AND stage_iri = %s"
        " ORDER BY started_at",
        document.id,
        CV + "stage_X5",
    )


async def x5_findings(connection: Any, document: Any) -> list[tuple[Any, ...]]:
    return await rows(
        connection,
        "SELECT f.rule, f.severity, f.focus_id FROM validation_finding f"
        " JOIN extraction_run r ON r.id = f.run_id"
        " WHERE f.document_id = %s AND r.stage_iri = %s ORDER BY f.rule, f.focus_id",
        document.id,
        CV + "stage_X5",
    )


async def test_x5_checks_the_document_after_x4_and_writes_its_findings_on_their_rows(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)

    result = await extract_document(context_of(pool, tmp_path, Model(), database_url), job)

    assert result["stages"] == ["X1", "X2", "X3", "X4", "X5"]
    [(outcome, made)] = await x5_runs(connection, document)
    assert (outcome, made["shacl"]) == ("done", "done")
    # X4's stand-in quotes "Aussage E1": no block holds it; the headings' titles stand word for word
    anchored = await rows(
        connection,
        "SELECT CASE WHEN statement_id IS NULL THEN 'node' ELSE 'statement' END,"
        " replace(match_kind_iri, %s, '')"
        " FROM anchor WHERE document_id = %s AND (statement_id IS NOT NULL OR node_id IS NOT NULL)"
        " GROUP BY 1, 2 ORDER BY 1, 2",
        CV,
        document.id,
    )
    assert anchored == [("node", "match_exact"), ("statement", "match_notFound")]
    statements = await rows(connection, "SELECT id FROM statement WHERE document_id = %s", document.id)
    found = await x5_findings(connection, document)
    assert {focus for rule, _, focus in found if rule == "x5.wording_not_found"} == {
        row for (row,) in statements
    }
    assert any(rule.startswith("shacl.") for rule, _, _ in found)
    assert made["anchors"] == {
        "exact": len(await node_anchors(connection, document)),
        "notFound": len(statements),
    }
    assert made["findings"] == {
        severity: sum(1 for _, said, _ in found if said == severity)
        for severity in ("violation", "warning", "info")
    }
    [(progress,)] = await rows(connection, "SELECT progress FROM job WHERE id = %s", job.id)
    assert progress == {"code": "check_document", "params": {}}


async def node_anchors(connection: Any, document: Any) -> list[tuple[Any, ...]]:
    return await rows(
        connection, "SELECT id FROM anchor WHERE document_id = %s AND node_id IS NOT NULL", document.id
    )


async def matched(connection: Any, document: Any) -> int:
    [(count,)] = await rows(
        connection,
        "SELECT count(*) FROM anchor WHERE document_id = %s AND match_kind_iri IS NOT NULL",
        document.id,
    )
    return int(count)


async def test_the_plausibility_findings_are_written_with_the_others(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)

    async def one_noted(_: Any, document_id: Any) -> list[Finding]:
        return [Finding("x5.unit_without_statements", "info", document_id, "a unit read whole holds none")]

    monkeypatch.setattr(x5_stage, "plausibility", one_noted)
    await extract_document(
        context_of(pool, tmp_path, Model(), database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert ("x5.unit_without_statements", "info", document.id) in await x5_findings(connection, document)


async def test_the_node_of_a_unit_under_no_heading_is_not_checked_against_its_blocks(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # X4 titles it by the document: its anchor says where the unit begins, not that the title stands there
    pool, connection = setup
    document = await a_document(connection, blocks=PLAIN)

    await extract_document(
        context_of(pool, tmp_path, Model(), database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    nodes = await rows(connection, "SELECT id FROM node WHERE document_id = %s", document.id)
    assert nodes  # X4 made one
    unchecked = await rows(
        connection,
        "SELECT count(*) FROM anchor"
        " WHERE document_id = %s AND node_id IS NOT NULL AND match_kind_iri IS NULL",
        document.id,
    )
    assert unchecked == [(len(nodes),)]
    found = await x5_findings(connection, document)
    assert not [focus for rule, _, focus in found if rule == "x5.wording_not_found" and (focus,) in nodes]


async def test_x5_sets_no_match_kind_where_the_attempt_lost_its_lease_before(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)

    async def then_lease_lost(*args: Any, **named: Any) -> Any:
        found = await unchecked_anchors(*args, **named)
        await connection.execute(
            "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
        )
        return found

    monkeypatch.setattr(x5_stage, "unchecked_anchors", then_lease_lost)
    with pytest.raises(LeaseLost):
        await extract_document(context_of(pool, tmp_path, Model(), database_url), job)

    assert await matched(connection, document) == 0


async def skipped(*_: Any) -> dict[str, Any]:
    return {}


async def waited_on(look: psycopg.AsyncConnection, holder: int) -> None:
    """Until some backend waits on a lock ``holder`` holds; AssertionError after 10 s."""
    for _ in range(200):
        cursor = await look.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE %s = ANY(pg_blocking_pids(pid))", (holder,)
        )
        [(waiting,)] = await cursor.fetchall()
        if waiting:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"no backend waited on {holder}")


async def test_x5_takes_the_tree_s_lock_before_it_writes_the_matches(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # who changes a tree's anchors takes its lock first (migration l1_nodes), as an editor does
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    context = context_of(pool, tmp_path, Model(), database_url)
    with monkeypatch.context() as patched:
        patched.setattr(run, "run_x5", skipped)
        await extract_document(context, job)  # X1 to X4
    editor = await psycopg.AsyncConnection.connect(database_url)
    try:
        async with editor.transaction():
            await lock_tree(editor, document.id)
            checking = asyncio.create_task(x5_stage.run_x5(context, job, document))
            await waited_on(connection, editor.info.backend_pid)
            meanwhile = await matched(connection, document)
        await asyncio.wait_for(checking, 120)
    finally:
        await editor.close()

    assert (meanwhile, await matched(connection, document) > 0) == (0, True)


def test_a_quote_longer_than_the_anchor_holds_is_left_out_and_its_span_kept() -> None:
    anchor = UncheckedAnchor(uuid.uuid4(), uuid.uuid4(), "Licht", ("Licht",))
    most = x5_stage.checked_anchor(anchor, AnchorMatch("fuzzy", 0.9, "x" * 20_000, 3, 20_003))
    over = x5_stage.checked_anchor(anchor, AnchorMatch("exact", None, "x" * 20_001, 0, 20_001))

    assert most == CheckedAnchor(anchor.id, CV + "match_fuzzy", 0.9, "x" * 20_000, 3, 20_003)
    assert over == CheckedAnchor(anchor.id, CV + "match_exact", None, None, 0, 20_001)


async def test_a_shacl_check_past_its_deadline_is_a_violation_and_x5_ends(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)

    async def too_long(*_: Any, **__: Any) -> list[Any]:
        raise ShaclTimeout("the SHACL validation took longer than 300 s")

    monkeypatch.setattr(x5_stage, "shacl_check", too_long)
    await extract_document(
        context_of(pool, tmp_path, Model(), database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    [(outcome, made)] = await x5_runs(connection, document)
    assert (outcome, made["shacl"]) == ("done", "timeout")
    assert ("x5.shacl_timeout", "violation", document.id) in await x5_findings(connection, document)


async def test_x5_writes_no_finding_where_the_attempt_lost_its_lease(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)

    async def lease_lost(*_: Any, **__: Any) -> list[Any]:
        await connection.execute(
            "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
        )
        return []

    monkeypatch.setattr(x5_stage, "shacl_check", lease_lost)
    with pytest.raises(LeaseLost):
        await extract_document(context_of(pool, tmp_path, Model(), database_url), job)

    assert [(outcome, made.get("failure")) for outcome, made in await x5_runs(connection, document)] == [
        ("failed", "LeaseLost")
    ]
    assert await x5_findings(connection, document) == []


async def test_a_run_of_x5_done_while_this_one_checked_passes_the_stage_over(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)

    async def overtaken(*_: Any, **__: Any) -> list[Any]:  # another job's run of X5 ends first
        other = RunStart(document.id, None, None, "X5", None, None, None, None)
        await finish_run(connection, await start_run(connection, other), "done", {})
        return []

    monkeypatch.setattr(x5_stage, "shacl_check", overtaken)
    await extract_document(
        context_of(pool, tmp_path, Model(), database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert [(outcome, made.get("failure")) for outcome, made in await x5_runs(connection, document)] == [
        ("failed", "X5 of the document was written by another run meanwhile"),
        ("done", None),
    ]
    assert await x5_findings(connection, document) == []
