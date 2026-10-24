"""X3's question (plan M1 7b, F2; schema x3-rahmenteile): the instructions with the rules a statement
is read by, the frame's ranges by their keys, title paths and first and last blocks, the profile's
statement subkinds keyed U1 … with the core kind each refines, the lexicon excerpt; and the task."""

from uuid import UUID

from app.pipeline.prompts import x3
from app.pipeline.prompts.statements import STATEMENT_RULES, subkind_list
from app.pipeline.x2_segments import WorkPackage
from app.vocab.lookup import ConceptText

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"


def package(key: str, path: tuple[str, ...], first: str, last: str) -> WorkPackage:
    node = None if not path else UUID(int=int(key[1:]))
    return WorkPackage(key, node, 0, 0, first, last, (1, 1), path, "typed", "frame")


def subkind(name: str, kind: str, definition: str | None = None) -> ConceptText:
    return ConceptText(SCHOOL + name, None, name, definition, (CV + kind,), None)


KINDS = {CV + "kind_learningOutcome": "learningOutcome", CV + "kind_mandate": "mandate"}


def test_the_subkinds_are_keyed_with_the_core_kind_each_refines() -> None:
    text, keys = subkind_list(
        [
            subkind("Kompetenzerwartung", "kind_learningOutcome", "Überprüfbare Erwartung."),
            subkind("Auftrag", "kind_mandate"),
        ],
        KINDS,
    )

    assert text == (
        "U1: Kompetenzerwartung (Aussageart learningOutcome) — Überprüfbare Erwartung.\n"
        "U2: Auftrag (Aussageart mandate)"
    )
    assert keys == {"U1": SCHOOL + "Kompetenzerwartung", "U2": SCHOOL + "Auftrag"}


def test_the_task_names_the_frame_s_ranges_the_subkinds_and_the_lexicon() -> None:
    task = x3.frame_task(
        [
            package("E0", (), "p1-b1", "p1-b2"),
            package("E3", ("Hinweise", "Leistungsbewertung"), "p3-b1", "p3-b9"),
        ],
        "U1: Kompetenzerwartung (Aussageart learningOutcome)",
        "„Leitperspektive“ → Querschnittsbereich (U2)",
    )

    assert task == (
        "=== RAHMENBEREICHE ===\n"
        "E0 | Titelei | Blöcke p1-b1 bis p1-b2\n"
        "E3 | Hinweise / Leistungsbewertung | Blöcke p3-b1 bis p3-b9\n"
        "\n=== AUSSAGE-UNTERARTEN (statementSubkind) ===\n"
        "U1: Kompetenzerwartung (Aussageart learningOutcome)\n"
        "\n=== LEXIKON ===\n"
        "„Leitperspektive“ → Querschnittsbereich (U2)\n"
        "\n=== AUFTRAG ===\n"
        "Lies die Rahmenteile des Dokuments: die Modelle, Operatoren, Legenden und Regeln, wo das Dokument"
        " sie erklärt, und die Aussagen der Rahmenbereiche. Antworte im vorgegebenen Schema.\n"
    )


def test_a_document_without_a_frame_is_told_so_and_an_empty_list_is_left_out() -> None:
    task = x3.frame_task([], "", "")

    assert task.startswith(
        "=== RAHMENBEREICHE ===\nDas Dokument hat keine Rahmenbereiche: statements bleibt leer.\n"
        "\n=== AUFTRAG ===\n"
    )


def test_the_instructions_carry_the_statements_rules_and_name_the_schema() -> None:
    assert STATEMENT_RULES in x3.INSTRUCTIONS
    assert (x3.SCHEMA, x3.SCHEMA_NAME) == ("x3-rahmenteile", "x3_rahmenteile")
    assert x3.PROMPT_VERSION.startswith("x3-")
