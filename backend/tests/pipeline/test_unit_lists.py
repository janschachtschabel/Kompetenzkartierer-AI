"""The choice lists X4's prefix carries from X3 (plan M1 7b, F8; konzept §13.1): the competency models
with their dimensions, the legend of cross-cutting markers, the operators - each in the order X3
wrote them, an operator once; level models and rules are no choice of X4's and stay out."""

from typing import Any
from uuid import UUID

from app.db.frame_parts import FramePart
from app.domain.l1 import FramePartKind
from app.pipeline.unit_prefix import choice_lists


def part(number: int, kind: FramePartKind, **content: Any) -> FramePart:
    return FramePart(UUID(int=number), kind, content, None)


def dimension(label: str, code: str | None = None, parent: str | None = None) -> dict[str, Any]:
    return {"code": code, "label": label, "parentLabel": parent}


def test_models_legend_and_operators_are_listed_in_the_order_x3_wrote_them() -> None:
    parts = [
        part(1, "operators", lemma="beschreiben", definition=None, taskDemandText="I"),
        part(
            2,
            "competencyModels",
            title="Prozessbezogene Kompetenzen",
            dimensions=[dimension("Kommunizieren", "K1"), dimension("Modellieren", None, "Problemlösen")],
        ),
        part(3, "crossCuttingLegend", marker="L BNE", label="Bildung für nachhaltige Entwicklung"),
        part(4, "operators", lemma="wählen … aus", definition="Eine Auswahl treffen.", taskDemandText=None),
        part(5, "operators", lemma="beschreiben", definition=None, taskDemandText="II"),
        part(6, "levelModels", title="Niveaustufen", levels=[]),
        part(7, "rules", verbatim="Zwei der Wahlmodule sind zu belegen."),
        part(8, "competencyModels", title="Inhaltsbereiche", dimensions=[]),
    ]

    assert choice_lists(parts) == (
        "Kompetenzmodelle:\n"
        "- Prozessbezogene Kompetenzen: K1 Kommunizieren; Modellieren (unter Problemlösen)\n"
        "- Inhaltsbereiche\n"
        "Querschnittsmarker:\n"
        "- L BNE: Bildung für nachhaltige Entwicklung\n"
        "Operatoren: beschreiben, wählen … aus"
    )


def test_a_document_without_them_has_no_lists() -> None:
    assert choice_lists([part(1, "rules", verbatim="Regel.")]) == ""
