"""X3's question (plan M1 7b, F2; schema x3-rahmenteile): one a document, behind the prefix every
request about its units shares (app/pipeline/prefix.py) - the document, its profile, no choice
lists yet: X3 makes them. The task names the frame's ranges - the packages X2 reads typed, the title
pages among them - by their keys, title paths and first and last blocks, the profile's statement
subkinds (prompts/statements.py) and the lexicon excerpt over the ranges' text. Models, operators,
legends and rules are read wherever the document declares them; statements from the ranges alone,
the other sections' are X4's.
"""

from collections.abc import Sequence

from app.pipeline.prompts.statements import STATEMENT_RULES
from app.pipeline.x2_segments import WorkPackage

PROMPT_VERSION = "x3-frame/1"
SCHEMA = "x3-rahmenteile"
SCHEMA_NAME = "x3_rahmenteile"
_PATH = " / "

INSTRUCTIONS = f"""Du liest die Rahmenteile eines Bildungsdokuments: Lehrplan, Rahmenlehrplan,
Ausbildungsordnung, Bildungsplan oder Modulhandbuch. Vor dem Auftrag steht das Dokument - vor jedem
Block seine Kennung in eckigen Klammern ([p3-b2]), vor jeder Tabellenzeile die ihrer Zeile, die
Seiten markiert - und sein Profil. Ist das Dokument gekürzt, nennt eine Gliederung die übrigen
Abschnitte.

Regeln:
- competencyModels und levelModels: nur Modelle, die das Dokument selbst erklärt - Kompetenzbereiche
  mit ihren Dimensionen, Niveau- oder Stufenmodelle mit ihren Stufen -, wo im Dokument auch immer;
  Bezeichnungen wörtlich.
- operators: die Operatorenliste des Dokuments, ein Eintrag je Zeile der Liste.
- crossCuttingLegend: die Legende der Querschnittsmarker, je Marker seine Erklärung.
- rules: Regeln zu Wahl, Voraussetzung, Abschluss, Anrechnung und Fortschritt im Wortlaut, ihre Zahlen
  gelesen; was die Regel nicht sagt, ist null.
- statements: nur Bildungsziele, Aufträge und Grundsätze aus den Rahmenbereichen, die der Auftrag
  nennt. Die Aussagen der übrigen Abschnitte liest ein anderer Schritt.
- evidenceBlockIds, evidenceBlockId und blockIds sind Kennungen von Blöcken des Dokuments (p…-b…),
  nie Seitenzahlen.

{STATEMENT_RULES}"""


def frame_task(ranges: Sequence[WorkPackage], subkinds: str, excerpt: str) -> str:
    """The task for the frame of these ``ranges`` (X2's packages read typed); ``subkinds`` is the
    list of statement subkinds (prompts/statements.py), ``excerpt`` the lexicon's lines."""
    listed = "".join(
        f"{item.key} | {_PATH.join(item.path) or 'Titelei'}"
        f" | Blöcke {item.first_block} bis {item.last_block}\n"
        for item in ranges
    )
    parts = [
        "=== RAHMENBEREICHE ===\n"
        + (listed or "Das Dokument hat keine Rahmenbereiche: statements bleibt leer.\n")
    ]
    if subkinds:
        parts.append(f"=== AUSSAGE-UNTERARTEN (statementSubkind) ===\n{subkinds}\n")
    if excerpt:
        parts.append(f"=== LEXIKON ===\n{excerpt}\n")
    parts.append(
        "=== AUFTRAG ===\nLies die Rahmenteile des Dokuments: die Modelle, Operatoren, Legenden und"
        " Regeln, wo das Dokument sie erklärt, und die Aussagen der Rahmenbereiche."
        " Antworte im vorgegebenen Schema.\n"
    )
    return "\n".join(parts)
