"""X5 in the job extract.run (plan M1 8.5): after X4, no model asked - each anchor's wording checked
against its blocks and its match kind written, the plausibility checks, the document's Kern graph
against the shapes in a child - its findings rows of the document, each on the row it is about, written
with the run's end under the lease. A model stands in for X1 to X4."""

from pathlib import Path
from typing import Any

import pytest

from app.db.runs import RunStart, finish_run, start_run
from app.jobs.queue import LeaseLost
from app.pipeline import x5_stage
from app.pipeline.run import extract_document
from app.pipeline.shacl import ShaclTimeout
from tests.pipeline.test_run import CV, Model, a_document, a_job, context_of, rows, setup

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
    assert made["findings"] == {
        severity: sum(1 for _, said, _ in found if said == severity)
        for severity in ("violation", "warning", "info")
    }
    [(progress,)] = await rows(connection, "SELECT progress FROM job WHERE id = %s", job.id)
    assert progress == {"code": "check_document", "params": {}}


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
