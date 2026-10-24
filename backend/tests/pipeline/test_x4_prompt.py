"""X4's question for a unit (plan M1 7b, F3; schema x4-aussagen; konzept §13.1): the choice lists of
its prefix - X3's, then the profile's statement subkinds, the same for every unit -, and its task:
the unit by its key, title path and blocks, its node's type, the lexicon excerpt over its text."""

from uuid import UUID

from app.pipeline.prompts import x4
from app.pipeline.prompts.statements import STATEMENT_RULES
from app.pipeline.x2_segments import WorkPackage


def unit(key: str, path: tuple[str, ...], first: str, last: str) -> WorkPackage:
    return WorkPackage(key, UUID(int=1), 0, 0, first, last, (2, 2), path, "full", "statements")


def test_the_task_names_the_unit_its_node_and_its_lexicon() -> None:
    task = x4.unit_task(
        unit("E2", ("Kompetenzen", "Optik"), "p2-b3", "p2-b4"),
        "Knotentyp: Inhaltsbereich — Thematische Ordnungseinheit.",
        "„Leitperspektive“ → Querschnittsbereich (U2)",
    )

    assert task == (
        "=== EINHEIT ===\n"
        "E2 | Kompetenzen / Optik | Blöcke p2-b3 bis p2-b4\n"
        "Knotentyp: Inhaltsbereich — Thematische Ordnungseinheit.\n"
        "\n=== LEXIKON ===\n"
        "„Leitperspektive“ → Querschnittsbereich (U2)\n"
        "\n=== AUFTRAG ===\n"
        "Gib die Aussagen der Einheit E2 zurück, die in den Blöcken p2-b3 bis p2-b4 stehen, mit E2 als"
        " unitKey. Das übrige Dokument ist Zusammenhang. Antworte im vorgegebenen Schema.\n"
    )


def test_a_unit_of_no_node_type_and_no_lexicon_is_asked_without_them() -> None:
    task = x4.unit_task(unit("E1", (), "p1-b1", "p3-b1"), "", "")

    assert task.startswith("=== EINHEIT ===\nE1 | Dokument | Blöcke p1-b1 bis p3-b1\n\n=== AUFTRAG ===\n")


def test_the_prefix_lists_x3_s_choices_then_the_subkinds() -> None:
    assert x4.prefix_lists("Operatoren: beschreiben", "U1: Kompetenzerwartung") == (
        "Operatoren: beschreiben\nAussage-Unterarten (statementSubkind):\nU1: Kompetenzerwartung"
    )
    assert x4.prefix_lists("", "U1: Kompetenzerwartung") == (
        "Aussage-Unterarten (statementSubkind):\nU1: Kompetenzerwartung"
    )
    assert x4.prefix_lists("", "") == ""


def test_the_instructions_carry_the_statements_rules_and_name_the_schema() -> None:
    assert STATEMENT_RULES in x4.INSTRUCTIONS
    assert (x4.SCHEMA, x4.SCHEMA_NAME) == ("x4-aussagen", "x4_aussagen")
    assert x4.PROMPT_VERSION.startswith("x4-")
