"""X6's question for a work package (plan M1 8b, F3; konzept §13.2: "X6 Reparatur | nur fehlerhafte
Einheiten erneut | wie X4"): X4's instructions and answer schema, behind the prefix every request about
the document's units shares - byte for byte, so cached alike (plan M1, Lesekontext) -, and X4's task
for the package, with what was wrong in the answer before, in words, and the statements the editors
hold: those stay, and the answer is not to bring them again.
"""

from collections.abc import Sequence

from app.pipeline.prompts import x4
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x6_units import Defect

PROMPT_VERSION = "x6-repair/1"
INSTRUCTIONS = x4.INSTRUCTIONS  # the system prompt is part of what a cache shares
SCHEMA = x4.SCHEMA
SCHEMA_NAME = x4.SCHEMA_NAME

# what the reading of an answer found wrong (app/pipeline/statement_read.py), by its rule's name
_READ: dict[str, str] = {
    "too_many_statements": "Mehr Aussagen, als eine Antwort enthalten darf",
    "statement_without_block": "Eine Aussage ohne gültige Blockkennung",
    "statement_without_wording": "Eine Aussage ohne Wortlaut",
    "statement_too_long": "Eine Aussage über der Längengrenze",
    "unknown_block": "Eine Blockkennung, die das Dokument nicht hat",
    "block_outside_unit": "Ein Block außerhalb der Einheit",
    "unknown_value": "Ein Wert, den die Auswahlliste nicht hat",
    "unknown_key": "Eine Kennung, die die Auswahlliste nicht hat",
    "subkind_mismatch": "Eine Unterart, die nicht zur Aussageart gehört",
    # X6's own: the package stayed as it was
    "unanswered": "Die letzte Antwort hatte nicht die Form des Schemas oder galt einer anderen Einheit",
    "empty_answer": "Die letzte Antwort enthielt keine neue lesbare Aussage, obwohl die Einheit welche hat",
}


def repair_task(
    unit: WorkPackage, node: str, excerpt: str, defects: Sequence[Defect], kept: Sequence[str]
) -> str:
    """The task for ``unit`` as X4's names it, then ``defects`` and the wordings the editors hold."""
    blocks = f"{unit.first_block} bis {unit.last_block}"
    parts = x4.unit_parts(unit, node, excerpt)
    parts.append(
        "=== BEFUNDE DER LETZTEN ANTWORT ===\n" + "".join(f"- {_said(defect)}\n" for defect in defects)
    )
    if kept:
        parts.append("=== BLEIBT (nicht zurückgeben) ===\n" + "".join(f"- „{wording}“\n" for wording in kept))
    parts.append(
        f"=== AUFTRAG ===\nLies die Einheit {unit.key} noch einmal und gib alle ihre Aussagen zurück, die in"
        f" den Blöcken {blocks} stehen, mit {unit.key} als unitKey - jeden Wortlaut wörtlich, wie er im"
        " Block steht. Die Befunde nennen, was an der letzten Antwort falsch war. Was unter BLEIBT steht,"
        " ist schon erfasst oder verworfen; gib es nicht zurück. Antworte im vorgegebenen Schema.\n"
    )
    return "\n".join(parts)


def _said(defect: Defect) -> str:
    """A defect in a line of the task: a statement's wording not found, a finding on a statement with
    its message (SHACL's, German) and property, what the reading found with what was at fault - not
    where in an answer the model no longer sees -, else the finding's own message."""
    if defect.rule == "x5.wording_not_found" and defect.wording is not None:
        return f"„{defect.wording}“ steht nicht wörtlich in den Blöcken der Einheit."
    if defect.wording is not None:
        where = f" ({defect.path})" if defect.path else ""
        return f"„{defect.wording}“: {defect.message}{where}"
    read = _READ.get(defect.rule.partition(".")[2])
    if read is None:
        return defect.message
    return f"{read}: {defect.detail}." if defect.detail else f"{read}."
