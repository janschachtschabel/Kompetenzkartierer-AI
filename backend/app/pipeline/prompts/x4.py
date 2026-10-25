"""X4's question for a unit (plan M1 7b, F3; schema x4-aussagen; konzept §13.1): one a unit - an X2
package read in full -, behind the prefix every request about the document's units shares
(app/pipeline/prefix.py): the document, its profile and the choice lists, X3's with the profile's
statement subkinds (prompts/statements.py), the same for every unit and so cached. The task names
the unit by its key, title path and first and last blocks, its node's type, and the lexicon excerpt
over its text. The block range says what the answer is for, not what is read (konzept §13.1).
"""

from app.pipeline.prompts.statements import STATEMENT_RULES
from app.pipeline.x2_segments import WorkPackage

PROMPT_VERSION = "x4-statements/1"
SCHEMA = "x4-aussagen"
SCHEMA_NAME = "x4_aussagen"
_PATH = " / "

INSTRUCTIONS = f"""Du liest die Aussagen einer Einheit eines Bildungsdokuments: Lehrplan, Rahmenlehrplan,
Ausbildungsordnung, Bildungsplan oder Modulhandbuch. Vor dem Auftrag steht das Dokument - vor jedem
Block seine Kennung in eckigen Klammern ([p3-b2]), vor jeder Tabellenzeile die ihrer Zeile, die
Seiten markiert -, sein Profil und die Auswahllisten: Kompetenzmodelle, Querschnittsmarker,
Operatoren und die Aussage-Unterarten des Profils. Ist das Dokument gekürzt, nennt eine Gliederung
die übrigen Abschnitte.

Regeln:
- Gib alle Aussagen zurück, die in den Blöcken der Einheit stehen, und nur sie; das übrige Dokument
  ist Zusammenhang für das Verständnis. unitKey ist die Kennung der Einheit aus dem Auftrag.
- Überschriften sind keine Aussagen. Eine Aussage über mehrere Blöcke nennt jeden davon.

{STATEMENT_RULES}"""


def prefix_lists(choices: str, subkinds: str) -> str:
    """The choice lists of X4's prefix: X3's (app/pipeline/unit_prefix.py, choice_lists), then the
    statement subkinds; none where both are empty."""
    parts = [choices] if choices else []
    if subkinds:
        parts.append(f"Aussage-Unterarten (statementSubkind):\n{subkinds}")
    return "\n".join(parts)


def unit_task(unit: WorkPackage, node: str, excerpt: str) -> str:
    """The task for ``unit``; ``node`` is the line naming its node's type (none where it has none),
    ``excerpt`` the lexicon's lines over its text."""
    blocks = f"{unit.first_block} bis {unit.last_block}"
    order = (
        f"=== AUFTRAG ===\nGib die Aussagen der Einheit {unit.key} zurück, die in den Blöcken {blocks}"
        f" stehen, mit {unit.key} als unitKey. Das übrige Dokument ist Zusammenhang."
        " Antworte im vorgegebenen Schema.\n"
    )
    return "\n".join([*unit_parts(unit, node, excerpt), order])


def unit_parts(unit: WorkPackage, node: str, excerpt: str) -> list[str]:
    """What a task about ``unit`` names before its order: the unit, its node's type, the lexicon."""
    blocks = f"{unit.first_block} bis {unit.last_block}"
    parts = [
        f"=== EINHEIT ===\n{unit.key} | {_PATH.join(unit.path) or 'Dokument'} | Blöcke {blocks}\n"
        + (f"{node}\n" if node else "")
    ]
    if excerpt:
        parts.append(f"=== LEXIKON ===\n{excerpt}\n")
    return parts
