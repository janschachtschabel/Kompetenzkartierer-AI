"""Generate a starter school lexicon from the FWU/MEM state classes.

Input: werkzeuge/quellen/fwu-landesklassen.csv – one row per state-specific
class of the FWU Lehrplan-Ontologie (data/sources/fwu-lehrplan-ontologie,
lp.ttl, CC BY-SA 4.0), with the state term, the state and the FWU base type
derived from the superclass chain.
Output: profile/schule-lexikon-fwu.ttl – one cur:LexicalCue per class with
cur:scopeRegion, cur:mapsTo on the school profile and skos:exactMatch to the
FWU class. Strength is low (0.6) and verified false: the FWU classes say
which terms a state uses, not how they look in a given document.

Rows without a state term (generic classes, school leaving levels) and terms
that a reviewed hand cue in schule.ttl already covers for the same state are
skipped; combined base types become homonyms with a rule text.

Usage: python -I erzeuge_schul_lexikon_fwu.py <ergebnis-dir>
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import SKOS

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
SCHUL = Namespace("https://w3id.org/wlo/curriculum/profile/school#")
LAND = Namespace("https://w3id.org/wlo/curriculum/region/")

BASE = {
    "CE-Bereich": SCHUL.Inhaltsbereich,
    "CE-Kompetenzspezifikation": SCHUL.Kompetenzerwartung,
    "CE-Lerninhalt": SCHUL.Inhalt,
    "CE-Hinweis": SCHUL.Hinweis,
    "CE-Verweis": SCHUL.Verweis,
    "CE-Fragment": SCHUL.Rahmenteil,
    "CE-Leitperspektive": SCHUL.Querschnittsbereich,
}
COMBINED = {
    "CE-Lerninhalt + CE-Hinweis": (SCHUL.Inhalt, SCHUL.Hinweis,
        "FWU führt den Begriff als Inhalt und Hinweis: verbindliche Stichworte → Inhalt, „z. B.“/Anregungen → Hinweis."),
    "CE-Kompetenzspezifikation + CE-Hinweis": (SCHUL.Kompetenzerwartung, SCHUL.Hinweis,
        "FWU führt den Begriff als Kompetenzspezifikation und Hinweis: Sätze mit Operator → Erwartung, Anregungen → Hinweis."),
    "CE-Kompetenzspezifikation + CE-Lerninhalt": (SCHUL.Kompetenzerwartung, SCHUL.Inhalt,
        "Spalte mit Lernzielen und Inhalten: Sätze mit Operator → Kompetenzerwartung, Stichworte → Inhalt."),
}
GENERIC_TERMS = {"Element", "Curriculares Element"}


def cue_name(iri: str) -> str:
    return "fwu-" + iri.rsplit("/", 1)[-1]


def region(code: str) -> tuple[URIRef, bool]:
    """Map the FWU state column; KMK-level classes (Bista/Bistas/KMK) apply nationwide."""
    if code in {"Bista", "Bistas", "KMK"}:
        return LAND.DE, True
    return LAND["DE-" + code], False


def hand_coverage(schule: Path) -> set[tuple[str, URIRef | None]]:
    """(surface form, region) pairs the hand-written school cues already cover."""
    hand = Graph()
    hand.parse(schule)
    covered = set()
    for cue in hand.subjects(RDF.type, CUR.LexicalCue):
        form = hand.value(cue, CUR.surfaceForm)
        if form is None:
            continue
        regions = list(hand.objects(cue, CUR.scopeRegion)) or [None]
        for r in regions:
            covered.add((str(form).casefold(), r))
    return covered


def is_covered(covered, term: str, land: URIRef) -> bool:
    key = term.casefold()
    return (key, land) in covered or (key, None) in covered


def build(rows, covered) -> Graph:
    g = Graph()
    for prefix, ns in [("cur", CUR), ("cv", CV), ("schul", SCHUL), ("land", LAND), ("skos", SKOS), ("xsd", XSD)]:
        g.bind(prefix, ns)
    g.bind("lp", "https://w3id.org/lehrplan/ontology/")
    for row in rows:
        base, term, code = row["basistyp"], row["term"].strip(), row["land"].strip()
        if base == "Curriculares Element" and term not in GENERIC_TERMS:
            targets, alt, hint = [CV.kind_unclassified], None, "FWU-Basistyp nur „Curriculares Element“; Art am Dokument bestimmen."
        elif base in BASE:
            targets, alt, hint = [BASE[base]], None, None
            # "Kompetenzschwerpunkt" (ST) is a content area despite its name; only names
            # of competence areas or dimensions become Kompetenzbereich
            if base == "CE-Bereich" and (term == "Kompetenzbereich" or term.endswith(("kompetenz", "Kompetenzen"))):
                targets = [SCHUL.Kompetenzbereich]
        elif base in COMBINED:
            first, second, hint = COMBINED[base]
            targets, alt = [first], second
        else:
            continue
        if not term or term in GENERIC_TERMS or not code:
            continue
        land, national = region(code)
        if is_covered(covered, term, land):
            # the reviewed hand cue in schule.ttl takes precedence
            continue
        cue = SCHUL[cue_name(row["iri"])]
        g.add((cue, RDF.type, CUR.LexicalCue))
        g.add((cue, CUR.surfaceForm, Literal(term)))
        g.add((cue, CUR.cueRole, CV.role_homonym if alt is not None else CV.role_cue))
        g.add((cue, CUR.cueKind, CV.ck_term))
        for t in targets:
            g.add((cue, CUR.mapsTo, t))
        if alt is not None:
            g.add((cue, CUR.alsoMapsTo, alt))
        g.add((cue, CUR.scopeRegion, land))
        if national:
            g.add((cue, CUR.scopeDocumentType, SCHUL["dt-Bildungsstandards"]))
        if hint:
            g.add((cue, CUR.recognitionHint, Literal(hint, lang="de")))
        g.add((cue, CUR.strength, Literal("0.6", datatype=XSD.decimal)))
        g.add((cue, CUR.verified, Literal(False)))
        g.add((cue, SKOS.exactMatch, URIRef(row["iri"])))
        g.add((SCHUL.Terminology, CUR.hasCue, cue))
    return g


HEADER = """# =============================================================================
# GENERIERT von werkzeuge/erzeuge_schul_lexikon_fwu.py aus
# werkzeuge/quellen/fwu-landesklassen.csv (Länderklassen der FWU-Lehrplan-
# Ontologie, data/sources/fwu-lehrplan-ontologie/lp.ttl).
# Abgeleitet aus der FWU-Ontologie: Lizenz CC BY-SA 4.0
# (https://creativecommons.org/licenses/by-sa/4.0/), Weitergabe unter
# gleichen Bedingungen. Nicht von Hand ändern.
# Startbestand: Stärke 0,6, nicht am Dokument geprüft. Von Hand geprüfte
# Hinweise stehen in schule.ttl und haben Vorrang.
# =============================================================================
"""


def main() -> None:
    ergebnis = Path(sys.argv[1])
    with open(ergebnis / "werkzeuge" / "quellen" / "fwu-landesklassen.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    g = build(rows, hand_coverage(ergebnis / "profile" / "schule.ttl"))
    target = ergebnis / "profile" / "schule-lexikon-fwu.ttl"
    target.write_bytes((HEADER + g.serialize(format="turtle")).replace("\r\n", "\n").encode("utf-8"))
    print(f"{len(set(g.subjects(RDF.type, CUR.LexicalCue)))} cues from {len(rows)} rows -> {target}")


if __name__ == "__main__":
    main()
