"""The job extract.check (plan M1 9; Paket 9 G9): X5 again on a document its editors changed - its findings
in place of those before - with no model asked, so no model job; a document X5 has not checked yet is
left to its extraction."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.draft_copy import copy_document
from app.db.runs import x5_owed
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, account_lane, claim, enqueue
from app.pipeline.extraction import CHECK_KIND
from app.pipeline.x5_check import check_document
from app.usage.admission import MODEL_JOB_KINDS
from tests.pipeline.test_run import CV, a_document, context_of, rows, setup
from tests.pipeline.test_x4_statements import FIELDS
from tests.pipeline.test_x6_repair import Quoting, extracted, not_found, runs_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run


async def a_check(connection: Any, document: Any) -> Job:
    await enqueue(connection, CHECK_KIND, account_lane(document.owner_id), {"document_id": str(document.id)})
    job = await claim(connection, "w1", [CHECK_KIND], 60)
    assert job is not None
    return job


def test_the_check_is_a_job_of_its_own_and_no_model_job() -> None:
    from app.jobs.handlers import make_handlers

    assert CHECK_KIND == "extract.check"
    assert CHECK_KIND not in MODEL_JOB_KINDS
    assert CHECK_KIND in make_handlers(context=None)  # type: ignore[arg-type]


async def test_a_check_finds_anew_what_the_editors_left(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    assert await not_found(connection, document) == ["Aussage E3"]
    await connection.execute(  # an editor rejects the wording no block holds
        "UPDATE statement SET review_status_iri = %s WHERE verbatim = 'Aussage E3'", (CV + "rev_rejected",)
    )
    asked = Quoting()

    made = await check_document(
        context_of(pool, tmp_path, asked, database_url), await a_check(connection, document)
    )

    assert made == {"document_id": str(document.id), "checked": True}
    assert (await not_found(connection, document), asked.units, asked.asked) == ([], [], [])
    assert [(stage, outcome) for stage, outcome, _ in await runs_of(connection, document)] == [
        ("X5", "done"), ("X5", "done"),
    ]  # fmt: skip


async def test_an_attempt_after_its_check_was_done_checks_not_again(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=())
    context = context_of(pool, tmp_path, Quoting(), database_url)
    job = await a_check(connection, document)

    await check_document(context, job)
    again = await check_document(context, job)

    assert again == {"document_id": str(document.id), "checked": True}
    assert len(await runs_of(connection, document)) == 2  # the extraction's, the check's


async def test_a_document_not_checked_yet_is_left_to_its_extraction(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)

    with pytest.raises(PermanentError) as refused:
        await check_document(
            context_of(pool, tmp_path, Quoting(), database_url), await a_check(connection, document)
        )

    assert refused.value.code == "document_not_checked"
    assert await rows(
        connection, "SELECT count(*) FROM extraction_run WHERE document_id = %s", document.id
    ) == [(0,)]


async def test_a_draft_copy_is_checked_with_no_x5_of_its_own_and_x5_owes_it_nothing_after(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # a copy takes no runs along (app/db/draft_copy.py): its first check is this job's
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=())
    await connection.execute(
        "UPDATE document SET iri = 'https://example.org/kk/doc/a/b/c/1', frozen_at = now() WHERE id = %s",
        (document.id,),
    )
    copy = await copy_document(connection, document.id)
    assert await x5_owed(connection, copy)

    made = await check_document(
        context_of(pool, tmp_path, Quoting(), database_url),
        await a_check(connection, SimpleNamespace(id=copy, owner_id=document.owner_id)),
    )

    assert made == {"document_id": str(copy), "checked": True}
    assert await rows(
        connection, "SELECT count(*) FROM extraction_run WHERE document_id = %s AND outcome = 'done'", copy
    ) == [(1,)]
    assert not await x5_owed(connection, copy)
