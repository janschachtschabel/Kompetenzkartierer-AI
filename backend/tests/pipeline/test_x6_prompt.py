"""X6's question for a work package (plan M1 8b, F3): X4's instructions and task for the package - the
prefix before them shared byte for byte - with what was wrong in the answer before, in words, and the
statements the editors hold, which the answer is not to bring again."""

from typing import Any

from app.pipeline.prompts import x4, x6
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x6_units import Defect


def package(**changes: Any) -> WorkPackage:
    values: dict[str, Any] = {
        "key": "E2", "node_id": None, "first": 3, "last": 5, "first_block": "p2-b2", "last_block": "p2-b4",
        "pages": (2, 2), "path": ("Kompetenzen", "Optik"), "depth": "full", "job": "statements",
    } | changes  # fmt: skip
    return WorkPackage(**values)


def test_a_repair_asks_as_x4_does_with_the_same_instructions_and_schema() -> None:
    assert (x6.INSTRUCTIONS, x6.SCHEMA, x6.SCHEMA_NAME) == (x4.INSTRUCTIONS, x4.SCHEMA, x4.SCHEMA_NAME)
    assert x6.PROMPT_VERSION == "x6-repair/1"


def test_the_task_names_the_package_as_x4_s_does_then_what_was_wrong_and_what_stays() -> None:
    defects = (
        Defect(
            "x5.wording_not_found", "the wording is not in the blocks", "Die Lernenden messen Licht.", None
        ),
        Defect("shacl.StatementShape", "Aussage ohne Adressat.", "Sie erklären Schatten.", "cur:addressee"),
        Defect(
            "x4.block_outside_unit", "a block outside the unit", None, "$.statements[1].blockIds[0]", "p2-b9"
        ),
        Defect("x6.unknown_key", "a key the question did not list", None, "$.statements[0].addressee", None),
        Defect("x6.unanswered", "the model's answer never took the form of the unit", None, None),
        Defect("x6.empty_answer", "the answer held no statement", None, None),
        Defect("x6.something_new", "something no word was found for", None, None),
    )

    task = x6.repair_task(package(), "Knotentyp: Inhaltsfeld", "Auge → Organ", defects, ("Bleibt so.",))

    head = x4.unit_task(package(), "Knotentyp: Inhaltsfeld", "Auge → Organ").split("=== AUFTRAG ===")[0]
    assert task.startswith(head)
    assert "=== BEFUNDE DER LETZTEN ANTWORT ===\n" in task
    for line in (
        "- „Die Lernenden messen Licht.“ steht nicht wörtlich in den Blöcken der Einheit.",
        "- „Sie erklären Schatten.“: Aussage ohne Adressat. (cur:addressee)",
        # what was at fault, not where in an answer the model no longer sees
        "- Ein Block außerhalb der Einheit: p2-b9.",
        "- Eine Kennung, die die Auswahlliste nicht hat.",
        "- Die letzte Antwort hatte nicht die Form des Schemas oder galt einer anderen Einheit.",
        "- Die letzte Antwort enthielt keine neue lesbare Aussage, obwohl die Einheit welche hat.",
        "- something no word was found for",
    ):
        assert line in task
    assert "$.statements" not in task
    assert "=== BLEIBT (nicht zurückgeben) ===\n- „Bleibt so.“\n" in task
    order = [
        task.index(mark)
        for mark in ("=== EINHEIT", "=== LEXIKON", "=== BEFUNDE", "=== BLEIBT", "=== AUFTRAG")
    ]
    assert order == sorted(order)
    asked = task.split("=== AUFTRAG ===")[1]
    assert "mit E2 als unitKey" in asked and "wörtlich" in asked
    assert "Was unter BLEIBT steht, ist schon erfasst oder verworfen; gib es nicht zurück." in asked


def test_a_task_without_statements_held_has_no_list_of_them() -> None:
    task = x6.repair_task(package(), "", "", (Defect("x4.unknown_block", "m", None, None),), ())

    assert "=== BLEIBT" not in task and "=== LEXIKON" not in task
