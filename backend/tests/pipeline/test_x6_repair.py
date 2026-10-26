"""The job extract.repair (plan M1 8.6, 8b; konzept §13.2): X6 asks the model again only for the work
packages whose statements X5 or the reading found wrong - X4's question with the defects named, the same
prefix -, writes them anew without touching what the editors hold, and then X5 checks the document
again, its findings replacing the ones before. A model stands in (FunctionModel)."""

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, account_lane, claim, enqueue
from app.pipeline import x6_repair
from app.pipeline.extraction import REPAIR_KIND
from app.pipeline.progress import report
from app.pipeline.run import extract_document
from app.pipeline.x5_stage import run_x5
from app.usage.admission import MODEL_JOB_KINDS
from app.usage.ledger import usage_of
from tests.pipeline.test_run import BODY, CV, Model, a_document, a_job, a_statement, context_of, rows, setup
from tests.pipeline.test_x3_frame import prompt_of
from tests.pipeline.test_x4_statements import FIELDS, with_concurrency

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run


class Quoting(Model):
    """Answers a unit with the wording of its first block as the prompt's document shows it - but the
    units in ``invent``, which it answers with "Aussage <key>", a wording no block holds."""

    def __init__(self, invent: tuple[str, ...] = (), **given: Any) -> None:
        super().__init__(**given)
        self.invent = invent
        self.prompts: list[str] = []

    def unit(self, prompt: str) -> dict[str, Any]:
        found = re.search(r"^=== EINHEIT ===\n(E\d+) \| .* \| Blöcke (\S+) bis", prompt, re.M)
        assert found is not None
        key, first = found[1], found[2]
        self.units.append(key)
        self.prompts.append(prompt)
        if key in self.invent or key in self.answers:
            return self.answers.get(key) or {
                "unitKey": key, "statements": [a_statement(first, f"Aussage {key}")], "checkedAbsent": [],
            }  # fmt: skip
        text = re.search(rf"^\[{re.escape(first)}\] (.*)$", prompt, re.M)
        assert text is not None
        return {"unitKey": key, "statements": [a_statement(first, text[1])], "checkedAbsent": []}


async def a_repair(connection: Any, document: Any) -> Job:
    await enqueue(connection, REPAIR_KIND, account_lane(document.owner_id), {"document_id": str(document.id)})
    job = await claim(connection, "w1", [REPAIR_KIND], 60)
    assert job is not None
    return job


async def extracted(setup: Any, tmp_path: Path, database_url: str, invent: tuple[str, ...]) -> Any:
    """The document of FIELDS extracted to X5, ``invent``'s units answered with wordings no block holds."""
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    context = context_of(pool, tmp_path, Quoting(invent), database_url)
    await extract_document(context, await a_job(connection, document.id, document.owner_id))
    return document


async def runs_of(connection: Any, document: Any) -> list[tuple[Any, ...]]:
    found = await rows(
        connection,
        "SELECT replace(stage_iri, %s, ''), outcome, result FROM extraction_run WHERE document_id = %s"
        " AND stage_iri IN (%s, %s) ORDER BY started_at",
        CV + "stage_", document.id, CV + "stage_X5", CV + "stage_X6",
    )  # fmt: skip
    return found


async def wordings(connection: Any, document: Any) -> list[str]:
    found = await rows(
        connection, "SELECT verbatim FROM statement WHERE document_id = %s ORDER BY 1", document.id
    )
    return [verbatim for (verbatim,) in found]


async def not_found(connection: Any, document: Any) -> list[str]:
    found = await rows(
        connection,
        "SELECT s.verbatim FROM validation_finding f JOIN statement s ON s.id = f.focus_id"
        " WHERE f.document_id = %s AND f.rule = 'x5.wording_not_found' ORDER BY 1",
        document.id,
    )
    return [verbatim for (verbatim,) in found]


def test_the_repair_is_a_model_job_of_its_own() -> None:
    from app.jobs.handlers import make_handlers

    assert REPAIR_KIND == "extract.repair"
    assert REPAIR_KIND in MODEL_JOB_KINDS
    assert REPAIR_KIND in make_handlers(context=None)  # type: ignore[arg-type]


async def test_a_repair_asks_again_only_the_packages_with_defects_and_checks_the_document_again(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    assert await not_found(connection, document) == ["Aussage E3"]
    fixer = Quoting()

    made = await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    assert fixer.units == ["E3"]  # E2 and E4 were right
    [asked] = fixer.prompts
    assert "=== BEFUNDE DER LETZTEN ANTWORT ===\n- „Aussage E3“ steht nicht wörtlich" in asked
    assert "Aussage E3" not in await wordings(connection, document)
    assert await not_found(connection, document) == []
    runs = await runs_of(connection, document)
    assert [(stage, outcome) for stage, outcome, _ in runs] == [
        ("X5", "done"),
        ("X6", "done"),
        ("X5", "done"),
    ]
    assert runs[1][2] == {"units": 1, "statements": 1, "dropped": 0, "unanswered": []}
    assert await rows(
        connection,
        "SELECT unit_key, repairs FROM extraction_unit WHERE document_id = %s ORDER BY 1",
        document.id,
    ) == [("E2", 0), ("E3", 1), ("E4", 0)]
    assert made == {"document_id": str(document.id), "units": 1, "checked": True}


async def test_a_repair_s_prefix_is_x4_s_byte_for_byte(setup: Any, tmp_path: Path, database_url: str) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    first = Quoting(invent=("E3",))
    await extract_document(
        context_of(pool, tmp_path, first, database_url),
        await a_job(connection, document.id, document.owner_id),
    )
    fixer = Quoting()

    await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    [x4_asked] = [
        prompt for prompt in first.prompts if prompt.split("=== EINHEIT ===")[1].startswith("\nE3 ")
    ]
    assert fixer.prompts[0].split("=== EINHEIT ===")[0] == x4_asked.split("=== EINHEIT ===")[0]


async def test_a_package_whose_wrong_statement_the_editors_hold_is_left_to_them(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    await connection.execute(
        "UPDATE statement SET revision = 2 WHERE verbatim = 'Aussage E3' AND document_id = %s", (document.id,)
    )
    await connection.execute("UPDATE statement SET verbatim = 'Aussage E3b' WHERE verbatim = 'Aussage E3'")
    # the editors' wording still not the block's: a violation on a statement they hold is theirs
    fixer = Quoting()

    made = await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    assert (fixer.units, made["units"]) == ([], 0)
    assert "Aussage E3b" in await wordings(connection, document)


async def test_a_document_nothing_is_wrong_with_is_neither_asked_nor_checked_again(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=())
    fixer = Quoting()

    made = await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    assert (fixer.units, made) == ([], {"document_id": str(document.id), "units": 0, "checked": False})
    assert [stage for stage, _, _ in await runs_of(connection, document)] == ["X5"]


async def test_a_document_not_checked_yet_is_not_repaired(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)

    with pytest.raises(PermanentError) as refused:
        await x6_repair.repair_document(
            context_of(pool, tmp_path, Quoting(), database_url), await a_repair(connection, document)
        )

    assert refused.value.code == "document_not_checked"


async def test_an_answer_out_of_form_leaves_its_package_counts_the_repair_and_says_so(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    fixer = Quoting(units={"E3": {"unitKey": "E9", "statements": [], "checkedAbsent": []}})

    await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    assert "Aussage E3" in await wordings(connection, document)
    runs = await runs_of(connection, document)
    assert [(stage, outcome) for stage, outcome, _ in runs] == [
        ("X5", "done"),
        ("X6", "done"),
        ("X5", "done"),
    ]
    assert runs[1][2]["unanswered"] == ["E3"]
    assert await rows(
        connection,
        "SELECT f.rule, f.severity, f.details ->> 'unit' FROM validation_finding f"
        " JOIN extraction_run r ON r.id = f.run_id WHERE r.stage_iri = %s",
        CV + "stage_X6",
    ) == [("x6.unanswered", "warning", "E3")]
    assert await rows(connection, "SELECT repairs FROM extraction_unit WHERE unit_key = 'E3'") == [(1,)]


async def test_an_answer_of_no_statement_leaves_its_package_counts_the_repair_and_says_so(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    fixer = Quoting(units={"E3": {"unitKey": "E3", "statements": [], "checkedAbsent": []}})

    await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    assert "Aussage E3" in await wordings(connection, document)  # not lost with the answer
    runs = await runs_of(connection, document)
    assert runs[1][2]["unanswered"] == ["E3"]
    assert await rows(
        connection,
        "SELECT f.rule, f.severity, f.details ->> 'unit' FROM validation_finding f"
        " JOIN extraction_run r ON r.id = f.run_id WHERE r.stage_iri = %s",
        CV + "stage_X6",
    ) == [("x6.empty_answer", "warning", "E3")]
    assert await rows(connection, "SELECT repairs FROM extraction_unit WHERE unit_key = 'E3'") == [(1,)]


async def test_a_budget_spent_amid_the_repair_still_checks_what_was_repaired(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E2", "E3"))
    fixer = Quoting()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===" in prompt_of(messages) and not fixer.units:
            usage = await usage_of(connection, document.owner_id)
            await connection.execute(
                "UPDATE quota SET token_limit = %s WHERE account_id = %s",
                (usage.tokens_spent + usage.tokens_held, document.owner_id),
            )
        return fixer(messages, info)

    context = with_concurrency(context_of(pool, tmp_path, answer, database_url), database_url, 1)
    with pytest.raises(PermanentError) as ended:
        await x6_repair.repair_document(context, await a_repair(connection, document))

    assert ended.value.code == "budget_exhausted"
    assert fixer.units == ["E2"]
    assert await not_found(connection, document) == ["Aussage E3"]  # checked again: E2's is gone
    assert [(stage, outcome) for stage, outcome, _ in await runs_of(connection, document)] == [
        ("X5", "done"), ("X6", "budget_exhausted"), ("X5", "done"),
    ]  # fmt: skip


async def test_an_attempt_after_a_break_checks_what_its_repair_wrote_and_asks_nothing_again(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    job = await a_repair(connection, document)
    checked = run_x5

    async def broken(*_: Any, **__: Any) -> Any:
        raise ConnectionError("the database went away")

    monkeypatch.setattr(x6_repair, "run_x5", broken)
    with pytest.raises(ConnectionError):
        await x6_repair.repair_document(context_of(pool, tmp_path, Quoting(), database_url), job)
    monkeypatch.setattr(x6_repair, "run_x5", checked)
    again = Quoting()

    made = [await x6_repair.repair_document(context_of(pool, tmp_path, again, database_url), job)]
    made.append(await x6_repair.repair_document(context_of(pool, tmp_path, again, database_url), job))

    assert again.units == []
    assert made == [{"document_id": str(document.id), "units": 1, "checked": True}] * 2  # X6's, done before
    assert [(stage, outcome) for stage, outcome, _ in await runs_of(connection, document)] == [
        ("X5", "done"), ("X6", "done"), ("X5", "done"),
    ]  # fmt: skip


async def test_a_package_answered_wrong_again_is_asked_by_the_next_repair_and_no_third(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    first, second, third = Quoting(invent=("E3",)), Quoting(invent=("E3",)), Quoting()

    for model in (first, second, third):
        await x6_repair.repair_document(
            context_of(pool, tmp_path, model, database_url), await a_repair(connection, document)
        )

    assert (first.units, second.units, third.units) == (["E3"], ["E3"], [])  # twice at most (F2)
    assert await rows(connection, "SELECT repairs FROM extraction_unit WHERE unit_key = 'E3'") == [(2,)]
    assert await not_found(connection, document) == ["Aussage E3"]  # the editors' to take up


async def broken_once(monkeypatch: pytest.MonkeyPatch, name: str) -> Any:
    """``x6_repair.<name>`` breaking as a database gone away does; the original, to put back."""
    original = getattr(x6_repair, name)

    async def broken(*_: Any, **__: Any) -> Any:
        raise ConnectionError("the database went away")

    monkeypatch.setattr(x6_repair, name, broken)
    return original


async def test_an_attempt_after_x6_broke_off_asks_no_package_again_and_checks_what_it_wrote(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the attempt before wrote E2 anew and was answered out of form for E3; then its run broke off
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E2", "E3"))
    job = await a_repair(connection, document)
    first = Quoting(units={"E3": {"unitKey": "E9", "statements": [], "checkedAbsent": []}})
    ends = await broken_once(monkeypatch, "finish_run")
    with pytest.raises(ConnectionError):
        await x6_repair.repair_document(context_of(pool, tmp_path, first, database_url), job)
    monkeypatch.setattr(x6_repair, "finish_run", ends)
    again = Quoting()

    made = await x6_repair.repair_document(context_of(pool, tmp_path, again, database_url), job)

    assert (sorted(first.units), again.units) == (["E2", "E3"], [])  # each package once a job
    assert await rows(
        connection,
        "SELECT unit_key, repairs FROM extraction_unit WHERE document_id = %s ORDER BY 1",
        document.id,
    ) == [("E2", 1), ("E3", 1), ("E4", 0)]
    assert await not_found(connection, document) == ["Aussage E3"]  # checked again: E2's is gone
    assert [(stage, outcome) for stage, outcome, _ in await runs_of(connection, document)] == [
        ("X5", "done"), ("X6", "failed"), ("X5", "done"),
    ]  # fmt: skip
    assert made == {"document_id": str(document.id), "units": 0, "checked": True}


async def test_a_repair_ended_before_its_check_leaves_the_next_extraction_to_check_the_document(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # cancelled while it checked, or its attempts spent: what it wrote is checked by whatever comes next
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    checks = await broken_once(monkeypatch, "run_x5")
    with pytest.raises(ConnectionError):
        await x6_repair.repair_document(
            context_of(pool, tmp_path, Quoting(), database_url), await a_repair(connection, document)
        )
    monkeypatch.setattr(x6_repair, "run_x5", checks)
    model = Quoting()

    await extract_document(
        context_of(pool, tmp_path, model, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert model.units == []
    assert await not_found(connection, document) == []
    assert [(stage, outcome) for stage, outcome, _ in await runs_of(connection, document)] == [
        ("X5", "done"), ("X6", "done"), ("X5", "done"),
    ]  # fmt: skip


async def test_a_repair_with_nothing_left_to_ask_checks_what_one_before_left_unchecked(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    checks = await broken_once(monkeypatch, "run_x5")
    with pytest.raises(ConnectionError):
        await x6_repair.repair_document(
            context_of(pool, tmp_path, Quoting(), database_url), await a_repair(connection, document)
        )
    monkeypatch.setattr(x6_repair, "run_x5", checks)
    fixer = Quoting()

    made = await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    assert (fixer.units, made) == ([], {"document_id": str(document.id), "units": 0, "checked": True})
    assert await not_found(connection, document) == []
    assert [(stage, outcome) for stage, outcome, _ in await runs_of(connection, document)] == [
        ("X5", "done"), ("X6", "done"), ("X5", "done"),
    ]  # fmt: skip


async def test_an_attempt_after_the_budget_s_check_checks_what_it_repaired_then(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # the worker died once X5 had checked what the spent budget let X6 write: the job is asked again;
    # E2, answered wrong once more and found so, is not asked twice by the job
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E2", "E3"))
    job = await a_repair(connection, document)
    fixer = Quoting(invent=("E2",))

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===" in prompt_of(messages) and not fixer.units:
            usage = await usage_of(connection, document.owner_id)
            await connection.execute(
                "UPDATE quota SET token_limit = %s WHERE account_id = %s",
                (usage.tokens_spent + usage.tokens_held, document.owner_id),
            )
        return fixer(messages, info)

    spent = with_concurrency(context_of(pool, tmp_path, answer, database_url), database_url, 1)
    with pytest.raises(PermanentError):
        await x6_repair.repair_document(spent, job)
    await connection.execute(
        "UPDATE quota SET token_limit = NULL WHERE account_id = %s", (document.owner_id,)
    )
    again = Quoting()

    made = await x6_repair.repair_document(context_of(pool, tmp_path, again, database_url), job)

    assert (fixer.units, again.units) == (["E2"], ["E3"])
    assert await not_found(connection, document) == ["Aussage E2"]  # the next repair's to ask
    assert [(stage, outcome) for stage, outcome, _ in await runs_of(connection, document)] == [
        ("X5", "done"), ("X6", "budget_exhausted"), ("X5", "done"), ("X6", "done"), ("X5", "done"),
    ]  # fmt: skip
    assert made == {"document_id": str(document.id), "units": 1, "checked": True}


async def test_a_repair_reports_its_packages_as_they_are_written(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E2", "E4"))
    reported: list[tuple[str, dict[str, int]]] = []

    async def noted(connection: Any, job: Any, code: Any, **params: int) -> None:
        reported.append((code, params))
        await report(connection, job, code, **params)

    monkeypatch.setattr(x6_repair, "report", noted)
    context = with_concurrency(context_of(pool, tmp_path, Quoting(), database_url), database_url, 1)
    await x6_repair.repair_document(context, await a_repair(connection, document))

    assert reported == [
        ("repair_units", {"done": 0, "total": 2}),
        ("repair_units", {"done": 1, "total": 2}),
        ("repair_units", {"done": 2, "total": 2}),
    ]


async def test_a_repair_leaves_out_the_wording_the_editors_hold_and_names_it(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    first = [a_statement("p3-b2", "Aussage E3"), a_statement("p3-b2", "Zweite E3")]
    two = {"unitKey": "E3", "statements": first, "checkedAbsent": []}
    await extract_document(
        context_of(pool, tmp_path, Quoting(units={"E3": two}), database_url),
        await a_job(connection, document.id, document.owner_id),
    )
    await connection.execute("UPDATE statement SET revision = 2 WHERE verbatim = 'Zweite E3'")
    again = {"unitKey": "E3", "statements": [a_statement("p3-b2", "Zweite E3"), a_statement("p3-b2", BODY)],
             "checkedAbsent": []}  # fmt: skip
    fixer = Quoting(units={"E3": again})

    await x6_repair.repair_document(
        context_of(pool, tmp_path, fixer, database_url), await a_repair(connection, document)
    )

    assert "=== BLEIBT (nicht zurückgeben) ===\n- „Zweite E3“\n" in fixer.prompts[0]
    [*_, (_, _, repaired), _] = await runs_of(connection, document)
    assert repaired == {"units": 1, "statements": 1, "dropped": 1, "unanswered": []}
    assert sorted(await wordings(connection, document)).count("Zweite E3") == 1


async def test_what_reading_a_repair_s_answer_finds_is_x6_s_and_names_its_package(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await extracted(setup, tmp_path, database_url, invent=("E3",))
    outside = {"unitKey": "E3", "statements": [a_statement("p3-b2", BODY), a_statement("p2-b3", BODY)],
               "checkedAbsent": []}  # fmt: skip

    await x6_repair.repair_document(
        context_of(pool, tmp_path, Quoting(units={"E3": outside}), database_url),
        await a_repair(connection, document),
    )

    assert await rows(
        connection,
        "SELECT f.rule, f.details ->> 'unit' FROM validation_finding f"
        " JOIN extraction_run r ON r.id = f.run_id"
        " WHERE r.stage_iri = %s ORDER BY 1",
        CV + "stage_X6",
    ) == [("x6.block_outside_unit", "E3"), ("x6.statement_without_block", "E3")]
