"""X5's SHACL gate (plan M1 8.4): a document's Kern graph (app/exports/kern_rdf.py) validated in a child
process (app/pipeline/shacl_child.py, app/core/child.py) within a deadline, its results as findings.

The child keeps the results on the data's subjects. A result is about the row whose ``urn:uuid`` its
focus node is; one on a subject of another name goes to the document, its focus in the details. The
rule is the shape's name (``shacl.StatementShape``), the severity SHACL's. A validation past its
deadline is given up and its child killed (ShaclTimeout); one that breaks in its child, or whose child
ends without an answer, comes back by its error's kind (ShaclCrashed).

The graph reaches the child as a file, written beside the event loop: its N-Triples as an argument of
the spawn would fill the pipe the child drains only once it has started - seconds of a halted loop for
a long document (review of 8a).
"""

import asyncio
import json
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

from rdflib import Graph

from app.core.child import ChildLog, run_in_child
from app.db.findings import Finding
from app.domain.l1 import Severity
from app.pipeline.shacl_child import ShaclResult, run_child

_ROW = "urn:uuid:"


class ShaclTimeout(Exception):
    """The validation took longer than its deadline; its child was ended."""


class ShaclCrashed(RuntimeError):
    """The validation raised in its process, or the process ended without an answer."""


async def shacl_check(
    graph: Graph, *, ontology_dir: Path, timeout_s: float, told: ChildLog
) -> list[ShaclResult]:
    """The shapes' results over ``graph`` at its subjects, validated in a child process."""
    # one mkdir, made here: in a thread, a cancel meanwhile would leave the folder behind (a cancel
    # while the thread writes the file still may: a folder in the temporary files)
    folder = Path(tempfile.mkdtemp(prefix="shacl-data-"))
    try:
        data = folder / "data.nt"
        await asyncio.to_thread(graph.serialize, destination=data, format="nt", encoding="utf-8")
        async with asyncio.timeout(timeout_s):
            return await run_in_child(
                run_child, (str(ontology_dir), str(data), told), prefix="shacl-", read=_outcome
            )
    except TimeoutError:
        raise ShaclTimeout(f"the SHACL validation took longer than {timeout_s} s") from None
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def as_findings(results: Sequence[ShaclResult], document_id: UUID) -> list[Finding]:
    """The results as findings of the document's rows - the document's, where the focus is none."""
    findings = []
    for result in results:
        row = _row(result.focus)
        details: dict[str, str] = {}
        if result.component is not None:
            details["component"] = result.component
        if row is None:
            details["focus"] = result.focus
        if result.value is not None:
            details["value"] = result.value
        if result.lang is not None and result.message:  # the page quotes a message without as English
            details["lang"] = result.lang
        findings.append(
            Finding(
                f"shacl.{result.shape}", cast(Severity, result.severity), row or document_id,
                result.message or result.shape, path=result.path, details=details,
            )
        )  # fmt: skip
    return findings


def _row(focus: str) -> UUID | None:
    if not focus.startswith(_ROW):
        return None
    try:
        return UUID(focus.removeprefix(_ROW))
    except ValueError:
        return None


def _outcome(exit_code: int | None, out: Path) -> list[ShaclResult]:
    if (out / "result.json").exists():
        return [ShaclResult(*row) for row in json.loads((out / "result.json").read_text(encoding="utf-8"))]
    if (out / "crashed.json").exists():
        crashed = json.loads((out / "crashed.json").read_text(encoding="utf-8"))
        raise ShaclCrashed(f"the SHACL validation raised {crashed['error']} in its process")
    raise ShaclCrashed(f"the SHACL validation's process ended without an answer (exit code {exit_code})")
