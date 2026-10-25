"""X5 of the job extract.run (plan M1 8.1-8.5; konzept §13.2 "Prüfen"): no model asked.

1. Each anchor of a statement or a node's heading that has no match kind yet is checked against the
   text of the blocks it names (app/pipeline/anchor_check.py) - CPU work, beside the event loop - and
   its match kind, the document's text at the place and its span written under the attempt's lease and
   the tree's lock (who changes a tree's anchors takes it first, migration l1_nodes).
2. A wording its named blocks do not hold is ``x5.wording_not_found`` (violation) on its statement or
   node, read from the anchors as they stand, so a later run of X5 finds it again; the plausibility
   checks (app/pipeline/x5_checks.py) add theirs.
3. The document's Kern graph is validated against the shapes in a child process
   (app/pipeline/shacl.py) within SHACL_TIMEOUT_S; past it, ``x5.shacl_timeout`` (violation) keeps the
   gate shut, and X5 ends all the same.
4. The findings and the run's end are written in one transaction under the lease; another job's run of
   X5 done meanwhile passes this one over (app/pipeline/asking.py, Superseded).

After a repair (job extract.repair, plan M1 8b) X5 runs ``again``: a run done before does not stop it, and
its findings replace those of the stage's runs before - they describe the document before the repair.
One open extraction job per document (app/pipeline/extraction.py) keeps a second such run away.
"""

import asyncio
from collections import Counter
from collections.abc import Sequence
from typing import Any

from app.core.child import ChildLog
from app.core.logging import current_request_id
from app.db.anchors import (
    CheckedAnchor,
    UncheckedAnchor,
    match_kinds,
    not_found_anchors,
    set_matches,
    unchecked_anchors,
)
from app.db.documents import Document
from app.db.findings import Finding, add_findings, drop_stage_findings
from app.db.nodes import lock_tree
from app.db.runs import RunStart, done_stages, finish_run, lock_for_stage, start_run
from app.domain.l1 import Severity
from app.exports.kern_rdf import kern_graph
from app.exports.kern_rows import read_document
from app.jobs.context import JobContext
from app.jobs.queue import Job, hold_lease
from app.pipeline.anchor_check import AnchorMatch, check_wording
from app.pipeline.asking import Superseded, ended
from app.pipeline.progress import report
from app.pipeline.shacl import ShaclTimeout, as_findings, shacl_check
from app.pipeline.x4_unit import UNIT_WITHOUT_NODE
from app.pipeline.x5_checks import plausibility
from app.vocab.lookup import current_release

PROMPT_VERSION = "x5-checks/1"  # the checks' version: a run says by which rules it found
_CV = "https://w3id.org/wlo/curriculum/vocab#"
_MOST_QUOTE = 20_000  # what the anchor's quote holds (0015)
_SEVERITIES: tuple[Severity, ...] = ("violation", "warning", "info")


async def run_x5(context: JobContext, job: Job, document: Document, *, again: bool = False) -> dict[str, Any]:
    """X5 of the document, ended by what it found or by what broke it; ``again`` after a repair."""
    async with context.pool.connection() as connection:
        if not again and "X5" in await done_stages(connection, document.id):
            return {"done_before": True}
        # the lease first: an attempt that lost it starts no run that would never end
        await report(connection, job, "check_document")
        start = RunStart(
            document.id,
            job.id,
            job.attempts,
            "X5",
            None,
            PROMPT_VERSION,
            None,
            await current_release(connection),
        )
        run_id = await start_run(connection, start)
    return await ended(context, run_id, "X5", _checked(context, job, document, run_id, again=again))


async def _checked(
    context: JobContext, job: Job, document: Document, run_id: Any, *, again: bool
) -> dict[str, Any]:
    await _anchors(context, job, document)
    # the findings and the graph of one state of the document: a node moved meanwhile is in both or in none
    async with context.pool.connection() as connection, connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        findings = [
            Finding(
                "x5.wording_not_found",
                "violation",
                owner,
                "the wording is not in the blocks its anchor names",
                details={"anchor": str(anchor)},
            )
            for anchor, owner in await not_found_anchors(connection, document.id)
        ]
        findings += await plausibility(connection, document.id)
        kinds = await match_kinds(connection, document.id)  # as they stand: an attempt before set some
        rows = await read_document(connection, document.id)
    graph = await asyncio.to_thread(kern_graph, rows)  # a second for a long document: beside the loop
    settings = context.settings
    told = ChildLog(level=settings.log_level, format=settings.log_format, request_id=current_request_id())
    shacl = "done"
    try:
        results = await shacl_check(
            graph, ontology_dir=settings.ontology_dir, timeout_s=settings.shacl_timeout_s, told=told
        )
        findings += as_findings(results, document.id)
    except ShaclTimeout:
        shacl = "timeout"
        message = f"the SHACL validation took longer than {settings.shacl_timeout_s} s: the gate stays shut"
        findings.append(Finding("x5.shacl_timeout", "violation", document.id, message))
    counted = Counter(found.severity for found in findings)
    result = {
        "anchors": kinds,
        "findings": {severity: counted[severity] for severity in _SEVERITIES},
        "shacl": shacl,
    }
    async with context.pool.connection() as connection, connection.transaction():
        await hold_lease(connection, job)
        if await lock_for_stage(connection, document.id, "X5") and not again:
            raise Superseded
        if again:
            await drop_stage_findings(connection, document.id, "X5", keep_run=run_id)
        await add_findings(connection, document.id, run_id, findings)
        await finish_run(connection, run_id, "done", result)
    return result


async def _anchors(context: JobContext, job: Job, document: Document) -> None:
    """Check the document's unchecked anchors and write their matches."""
    async with context.pool.connection() as connection:
        # X4's node of a unit under no heading bears the document's title, no wording of its blocks
        unchecked = await unchecked_anchors(connection, document.id, rule_titles=(UNIT_WITHOUT_NODE,))
    matches = await asyncio.to_thread(_matched, unchecked)
    async with context.pool.connection() as connection, connection.transaction():
        await hold_lease(connection, job)
        await lock_tree(connection, document.id)
        await set_matches(
            connection,
            [checked_anchor(anchor, match) for anchor, match in zip(unchecked, matches, strict=True)],
        )


def _matched(unchecked: Sequence[UncheckedAnchor]) -> list[AnchorMatch]:
    return [check_wording(anchor.wording, anchor.texts) for anchor in unchecked]


def checked_anchor(anchor: UncheckedAnchor, match: AnchorMatch) -> CheckedAnchor:
    """The match as the anchor keeps it; a quote longer than the store holds is left out, its span kept."""
    quote = match.quote if match.quote is None or len(match.quote) <= _MOST_QUOTE else None
    return CheckedAnchor(anchor.id, _CV + "match_" + match.kind, match.score, quote, match.start, match.end)
