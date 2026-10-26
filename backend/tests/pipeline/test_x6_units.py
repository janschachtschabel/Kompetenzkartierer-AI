"""Which work packages a repair asks again (X6, plan M1 8b, Festlegung F1): a package X4 did whose
statements the model left wrong - a violation on a statement X4 or X6 wrote and nobody has touched
since, or a warning of the reading of its answer that names it (the answer lost something) - and that
was not repaired twice already. Hints, SHACL's warnings, findings on nodes or the document, packages
still open or read typed are no cause: they are the editors', X1's or extract.run's."""

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.db.migrate import migrate
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x6_units import Defect, repairable_units
from tests.db.l1 import CV, add_conversion, add_document, add_entity, add_node, add_statement, seed_vocabulary

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


def package(key: str, node: Any, job: Any = "statements") -> WorkPackage:
    depth: Any = {"statements": "full", "frame": "typed"}[job]
    return WorkPackage(key, node, 0, 0, "p2-b1", "p2-b2", (2, 2), ("Kompetenzen",), depth, job)


class Tree:
    """A document after X1 to X5: the title pages read typed (E0), a node of one package (E1), a node
    parted at pages (E2, E3), a package under no heading with X4's node of its own (E4), a package X4
    has not done (E5) - and its runs."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection
        self.document = add_document(connection, add_conversion(connection))
        self.one, self.parted, self.unwritten = (
            add_node(connection, self.document, position=at) for at in (1, 2, 3)
        )
        self.own = add_node(
            connection, self.document, position=4, function_iri=CV + "fn_unit", origin_iri=CV + "orig_rule",
            rule_id="x4.unit_without_node",
        )  # fmt: skip
        self.packages = [
            package("E0", None, "frame"), package("E1", self.one), package("E2", self.parted),
            package("E3", self.parted), package("E4", None), package("E5", self.unwritten),
        ]  # fmt: skip
        self.x2 = self.run("X2", {"packages": [item.as_result() for item in self.packages]})
        self.x3, self.x4 = self.run("X3"), self.run("X4")
        self.x5 = self.run("X5")
        for key, node in (("E1", self.one), ("E2", self.parted), ("E3", self.parted), ("E4", self.own)):
            connection.execute(
                "INSERT INTO extraction_unit (document_id, unit_key, run_id, node_id, statements)"
                " VALUES (%s, %s, %s, %s, 1)",
                (self.document, key, self.x4, node),
            )

    def run(self, stage: str, result: dict[str, Any] | None = None) -> Any:
        run = add_entity(self.connection, "extraction_run")
        self.connection.execute(
            "INSERT INTO extraction_run (id, document_id, stage_scheme, stage_iri, outcome, finished_at,"
            " result) VALUES (%s, %s, %s, %s, 'done', now(), %s)",
            (run, self.document, CV + "Stages", CV + "stage_" + stage, Jsonb(result or {})),
        )
        return run

    def statement(self, node: Any, position: int, verbatim: str, run: Any = None, **columns: Any) -> Any:
        columns = {"origin_iri": CV + "orig_model", "run_id": run or self.x4} | columns
        return add_statement(
            self.connection, self.document, node, position=position, verbatim=verbatim, **columns
        )

    def finding(self, run: Any, rule: str, severity: str, focus: Any, **more: Any) -> None:
        self.connection.execute(
            "INSERT INTO validation_finding (id, document_id, run_id, rule, severity, focus_id, path,"
            " message, details) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                uuid.uuid4(), self.document, run, rule, severity, focus, more.get("path"),
                more.get("message", rule), Jsonb(more.get("details", {})),
            ),
        )  # fmt: skip


@pytest.fixture
def tree(database_url: str) -> Iterator[Tree]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as connection:
        seed_vocabulary(connection)
        yield Tree(connection)


@pytest.fixture
async def connection(database_url: str) -> Any:
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


async def keys(connection: Any, tree: Tree) -> list[str]:
    return [unit.package.key for unit in await repairable_units(connection, tree.document)]


async def test_a_violation_on_a_statement_the_model_wrote_asks_its_package_again(
    tree: Tree, connection: Any
) -> None:
    wrong = tree.statement(tree.one, 1, "Aussage E1")
    tree.finding(tree.x5, "x5.wording_not_found", "violation", wrong, message="not in the blocks")

    [unit] = await repairable_units(connection, tree.document)

    assert (unit.package.key, unit.node_id, unit.first) == ("E1", tree.one, 1)
    assert unit.defects == (Defect("x5.wording_not_found", "not in the blocks", "Aussage E1", None),)
    assert unit.kept == ()


async def test_a_warning_of_reading_an_answer_asks_the_package_it_names_again(
    tree: Tree, connection: Any
) -> None:
    tree.finding(tree.x4, "x4.unknown_block", "warning", tree.document, path="statements[0].blockIds[0]",
                 message="a block id nobody showed", details={"unit": "E2", "block": "p9-b1"})  # fmt: skip
    tree.finding(tree.x4, "x4.unknown_value", "warning", tree.document, path="statements[1].obligation",
                 message="no such value", details={"unit": "E2", "value": "sometimes"})  # fmt: skip

    [unit] = await repairable_units(connection, tree.document)

    assert (unit.package.key, unit.first) == ("E2", 1)
    assert unit.defects == (  # with what was at fault: the block, value or key the reading named
        Defect("x4.unknown_block", "a block id nobody showed", None, "statements[0].blockIds[0]", "p9-b1"),
        Defect("x4.unknown_value", "no such value", None, "statements[1].obligation", "sometimes"),
    )


async def test_hints_shacl_s_warnings_and_findings_on_nodes_or_the_document_ask_nothing_again(
    tree: Tree, connection: Any
) -> None:
    stated = tree.statement(tree.one, 1, "Die Lernenden messen.")
    tree.finding(tree.x5, "shacl.StatementPlausibilityShape", "warning", stated)
    tree.finding(tree.x5, "x5.unit_without_statements", "info", tree.document, details={"unit": "E1"})
    tree.finding(tree.x4, "x4.value_cut", "info", tree.document, details={"unit": "E1"})
    tree.finding(tree.x4, "x4.pattern_timeout", "warning", tree.document, details={"unit": "E1"})
    tree.finding(tree.x5, "shacl.CurriculumNodeShape", "violation", tree.one)
    tree.finding(tree.x5, "x5.shacl_timeout", "violation", tree.document)
    tree.finding(tree.x4, "x4.unanswered", "warning", tree.document, details={"units": ["E1"]})

    assert await keys(connection, tree) == []


async def test_a_statement_the_editors_hold_is_no_cause_and_is_named_as_kept(
    tree: Tree, connection: Any
) -> None:
    changed = tree.statement(tree.one, 1, "Geändert.", revision=2)
    confirmed = tree.statement(tree.one, 2, "Bestätigt.", review_status_iri=CV + "rev_confirmed")
    rejected = tree.statement(tree.one, 3, "Verworfen.", review_status_iri=CV + "rev_rejected")
    human = tree.statement(tree.one, 4, "Von Hand.", origin_iri=CV + "orig_human")
    for held in (changed, confirmed, rejected, human):
        tree.finding(tree.x5, "x5.wording_not_found", "violation", held)
    assert await keys(connection, tree) == []
    wrong = tree.statement(tree.one, 5, "Aussage E1")
    tree.finding(tree.x5, "x5.wording_not_found", "violation", wrong)

    [unit] = await repairable_units(connection, tree.document)

    assert (unit.package.key, unit.kept) == ("E1", ("Geändert.", "Bestätigt.", "Verworfen.", "Von Hand."))


async def test_a_package_repaired_twice_or_not_done_is_not_asked_again(tree: Tree, connection: Any) -> None:
    tree.connection.execute("UPDATE extraction_unit SET repairs = 2 WHERE unit_key = 'E1'")
    tree.finding(tree.x4, "x4.unknown_block", "warning", tree.document, details={"unit": "E1"})
    tree.finding(tree.x4, "x4.unknown_block", "warning", tree.document, details={"unit": "E5"})  # open

    assert await keys(connection, tree) == []


async def test_a_statement_is_the_package_s_of_its_part_or_of_its_own_node(
    tree: Tree, connection: Any
) -> None:
    second_part = tree.statement(tree.parted, 10_002, "Aussage E3")
    under_no_heading = tree.statement(tree.own, 1, "Aussage E4")
    for wrong in (second_part, under_no_heading):
        tree.finding(tree.x5, "x5.wording_not_found", "violation", wrong)

    found = await repairable_units(connection, tree.document)

    assert [(unit.package.key, unit.node_id, unit.first) for unit in found] == [
        ("E3", tree.parted, 10_001),
        ("E4", tree.own, 1),
    ]


async def test_a_statement_x3_wrote_and_a_repair_s_own_count_as_written(tree: Tree, connection: Any) -> None:
    frame = tree.statement(tree.one, 1, "Ziel des Fachs", run=tree.x3)
    tree.finding(tree.x5, "x5.wording_not_found", "violation", frame)
    assert await keys(connection, tree) == []
    x6 = tree.run("X6")
    repaired = tree.statement(tree.one, 2, "Aussage E1, repariert", run=x6)
    tree.finding(tree.x5, "x5.wording_not_found", "violation", repaired)
    tree.finding(x6, "x6.statement_without_block", "warning", tree.document, details={"unit": "E2"})

    assert await keys(connection, tree) == ["E1", "E2"]


async def test_the_defects_of_a_package_are_all_named_in_their_order(tree: Tree, connection: Any) -> None:
    first, second = tree.statement(tree.one, 1, "Aussage A"), tree.statement(tree.one, 2, "Aussage B")
    tree.finding(tree.x5, "x5.wording_not_found", "violation", first)
    tree.finding(tree.x5, "x5.wording_not_found", "violation", second)
    tree.finding(tree.x5, "shacl.StatementShape", "violation", first, message="Aussage ohne Adressat.",
                 path="cur:addressee")  # fmt: skip
    tree.finding(tree.x4, "x4.unknown_block", "warning", tree.document, details={"unit": "E1"})

    [unit] = await repairable_units(connection, tree.document)

    assert [(defect.rule, defect.wording) for defect in unit.defects] == [
        ("shacl.StatementShape", "Aussage A"),
        ("x5.wording_not_found", "Aussage A"),
        ("x5.wording_not_found", "Aussage B"),
        ("x4.unknown_block", None),
    ]


async def test_a_package_whose_node_was_taken_away_is_not_asked_again(tree: Tree, connection: Any) -> None:
    tree.connection.execute("UPDATE extraction_unit SET node_id = NULL WHERE unit_key = 'E1'")
    tree.finding(tree.x4, "x4.unknown_block", "warning", tree.document, details={"unit": "E1"})

    assert await keys(connection, tree) == []
