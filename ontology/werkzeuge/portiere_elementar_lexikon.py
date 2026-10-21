"""Port the ELEM V2 country hints into the curriculum-core lexicon model.

Reads elementarbildung/extraktionshinweise-laender.ttl (201 skos-xl hints of
the ELEM research) and writes profile/elementar-lexikon.ttl: one
cur:LexicalCue per hint and country, attached to elem:Terminology.

Decisions applied while porting (see konzept.md, section "Elementarbildung"):
- hints with several countries are fanned out, one cue per country;
- ambiguous hints become role "homonym" and their extra concepts alternatives
  (cur:alsoMapsTo); otherwise extra concepts are additional targets;
- a surface form equal to the target's prefLabel is role "pref", else "cue";
- known errors of the source are corrected (ELEM report H.6 no. 2-6).

Usage: python -I portiere_elementar_lexikon.py <source.ttl> <ergebnis-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import PROV, SKOS

SRC_CUR = Namespace("https://w3id.org/curriculum-core/ontology#")
SRC_VOCAB = "https://w3id.org/curriculum-core/vocab/"
SKOSXL = Namespace("http://www.w3.org/2008/05/skos-xl#")

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
ELEM = Namespace("https://w3id.org/wlo/curriculum/profile/early-childhood#")
KD = Namespace("https://w3id.org/wlo/curriculum/dimension/")
CTX = Namespace("https://w3id.org/wlo/curriculum/context/")
LAND = Namespace("https://w3id.org/wlo/curriculum/region/")

PRINCIPLES = {
    "kinderrechte", "partizipation", "kinderschutz", "inklusion", "diversitaet",
    "geschlechtersensibel", "spiel", "alltagsintegration", "ko-konstruktion",
    "bindung-beziehung", "uebergaenge", "zusammenarbeit-familie", "sozialraum",
    "umgang-mit-veraenderung",
}
THEME_OVERRIDES = {
    "beobachtung-dokumentation": ELEM.BeobachtungDokumentation,
    "eingewoehnung": ELEM["p-uebergaenge"],
    "uebergang-schule": ELEM["p-uebergaenge"],
}
ROLE_MAP = {
    "sammelabschnitt": ELEM.Sammelabschnitt, "grundlagen": ELEM.Grundlagen,
    "leitbild": ELEM.Leitbild, "bildungsbereich": ELEM.Bildungsbereich,
    "teilbereich": ELEM.Teilbereich, "querschnitt": ELEM.Querschnitt,
    "basiskompetenzen": ELEM.Basiskompetenzen, "handlungsfeld": ELEM.Handlungsfeld,
    "alltagssituation": ELEM.Alltagssituation, "uebergang": ELEM.Uebergang,
    "beobachtung-dokumentation": ELEM.BeobachtungDokumentation,
    "zusammenarbeit": ELEM.Zusammenarbeit, "qualitaet": ELEM.Qualitaet,
    "rahmenbedingungen": ELEM.Rahmenbedingungen, "einleitung": ELEM.Einleitung,
    "verzeichnis": ELEM.Verzeichnis,
}
KIND_MAP = {
    "aussagetyp/impuls": ELEM.Impuls, "aussagetyp/praxisbeispiel": ELEM.Praxisbeispiel,
    "aussagetyp/reflexionsfrage": ELEM.Reflexionsfrage, "aussagetyp/ziel": ELEM.Bildungsziel,
    "aussagetyp/inhalt": ELEM.Inhalt,
    "zielart/bildungsanspruch": ELEM.Bildungsanspruch,
    "zielart/qualitaetsanspruch": ELEM.Qualitaetsanspruch,
    "zielart/kompetenz": ELEM.Kompetenzbeschreibung,
    "zielart/fertigkeit": ELEM.Kompetenzbeschreibung,
    "zielart/wissen": ELEM.Kompetenzbeschreibung,
}
DOCTYPE_MAP = {
    "bildungsplan-land": ELEM["dt-Bildungsplan"],
    "bildungsplan-altersuebergreifend": ELEM["dt-Bildungsplan-0-10"],
    "konzeption-einrichtung": ELEM["dt-Einrichtungskonzeption"],
    "konzeption-traeger": ELEM["dt-Traegerkonzeption"],
    "qualitaetsempfehlung": ELEM["dt-Qualitaetsempfehlung"],
    "rahmen-laenderuebergreifend": ELEM["dt-GemeinsamerRahmen"],
    "rechtsnorm": ELEM["dt-Rechtsnorm"],
    # "Rahmenlehrplan" is a routing rule to vocational education (H.6 no. 2).
    "sonstiges": CV.sec_vocational,
}
DIMENSION_MAP = {
    "personal": KD["ec-personal"], "sozial": KD["ec-social"], "sachlich": KD["ec-subject"],
    "lernmethodisch": KD["ec-learning"], "resilienz": KD["ec-resilience"],
    "kognition": KD["ec-cognition"], "motivation": KD["ec-motivation"],
    "selbstwahrnehmung": KD["ec-self-perception"], "selbstregulation": KD["ec-self-regulation"],
    "physisch": KD["ec-physical"], "verantwortung": KD["ec-responsibility"],
    "teilhabe": KD["ec-participation"],
}
CONTEXT_MAP = {
    "aufraeumen": CTX.tidying, "freispiel": CTX["free-play"], "gespraechskreis": CTX["circle-time"],
    "koerperpflege": CTX["body-care"], "mahlzeiten": CTX.meals, "projekt": CTX.project,
    "ruhen-schlafen": CTX["rest-sleep"], "eingewoehnungsphase": CTX["settling-in"],
    "spielsituationen": CTX.play,
}
OCCURRENCE_MAP = {
    "ueberschrift": CV.occ_heading, "titelei": CV.occ_titlePage, "fliesstext": CV.occ_body,
    "inhaltsverzeichnis": CV.occ_toc, "kasten": CV.occ_box, "tabellenkopf": CV.occ_tableHeader,
}
# Hints whose target is corrected while porting (ELEM report H.6).
TARGET_FIXES = {
    # no. 3: "Bildungsdimension" names the competence model, not a subtree.
    "h-1ff256fa1262": [KD.EarlyChildhood],
    # no. 4: area without a slice of the world - node type plus dimension.
    "h-2194c3d58e15": [ELEM.Bildungsbereich, KD["ec-cognition"]],
    "h-b27c5868b3ce": [ELEM.Bildungsbereich, KD["ec-cognition"]],
}
SL_SUSPECT = "h-ed502a997692"  # no. 5
SH_OLD_TERMS = {  # no. 6: SH terms of the pre-2026 guidelines, version unknown
    "Musisch-ästhetische Bildung", "Sprache(n), Zeichen/Schrift und Kommunikation",
    "Körper, Gesundheit und Bewegung", "Mathematik, Naturwissenschaft und Technik",
    "Ethik, Religion und Philosophie", "Medien und Digitalisierung",
}


def map_target(iri: URIRef) -> URIRef:
    """Translate a source vocabulary IRI into the new model."""
    path = str(iri)[len(SRC_VOCAB):]
    head, _, name = path.rpartition("/")
    if head == "rolle":
        return ROLE_MAP[name]
    if head == "elementar/thema":
        if name in THEME_OVERRIDES:
            return THEME_OVERRIDES[name]
        return ELEM[("p-" if name in PRINCIPLES else "f-") + name]
    if head == "elementar/kontext":
        return CONTEXT_MAP[name]
    if head == "kompetenzdimension":
        return DIMENSION_MAP[name]
    if head == "dokumenttyp":
        return DOCTYPE_MAP[name]
    if path in KIND_MAP:
        return KIND_MAP[path]
    raise KeyError(f"no mapping for {iri}")


def load_labels(ergebnis: Path) -> dict[URIRef, str]:
    """German prefLabels of all targets in the new model."""
    g = Graph()
    for ttl in [ergebnis / "profile" / "elementar.ttl", *sorted((ergebnis / "vokabulare").glob("*.ttl")),
                ergebnis / "ontologie" / "cur-vokabular.ttl"]:
        g.parse(ttl)
    return {s: str(o) for s, o in g.subject_objects(SKOS.prefLabel) if getattr(o, "language", None) == "de"}


def port(src: Graph, labels: dict[URIRef, str]) -> Graph:
    out = Graph()
    for prefix, ns in [("cur", CUR), ("cv", CV), ("elem", ELEM), ("kd", KD), ("ctx", CTX), ("land", LAND),
                       ("prov", PROV), ("xsd", XSD)]:
        out.bind(prefix, ns)
    main_of = {hint: concept for concept, hint in src.subject_objects(SKOSXL.altLabel)}
    for hint in sorted(src.subjects(RDF.type, SRC_CUR.Extraktionshinweis)):
        hid = str(hint).rsplit("/", 1)[-1]
        surface = str(src.value(hint, SKOSXL.literalForm))
        ambiguous = src.value(hint, SRC_CUR.mehrdeutig).toPython()
        targets = TARGET_FIXES.get(hid) or [map_target(main_of[hint])]
        extras = sorted({map_target(c) for c in src.objects(hint, SRC_CUR.zusaetzlichesKonzept)} - set(targets))
        lands = sorted(src.objects(hint, SRC_CUR.land)) or [None]
        for land in lands:
            code = str(land).rsplit("/", 1)[-1] if land is not None else None
            cue = ELEM[f"lex-{hid[2:]}" + (f"-{code[3:] or 'DE'}" if code else "")]
            out.add((cue, RDF.type, CUR.LexicalCue))
            out.add((cue, CUR.surfaceForm, Literal(surface)))
            out.add((cue, CUR.cueKind, CV.ck_term))
            out.add((cue, PROV.wasDerivedFrom, hint))
            if DOCTYPE_MAP["sonstiges"] in targets:
                role = CV.role_negative
            elif ambiguous:
                role = CV.role_homonym
            elif labels.get(targets[0]) == surface:
                role = CV.role_pref
            else:
                role = CV.role_cue
            out.add((cue, CUR.cueRole, role))
            for t in targets:
                out.add((cue, CUR.mapsTo, t))
            for t in extras:
                out.add((cue, CUR.alsoMapsTo if ambiguous else CUR.mapsTo, t))
            if land is not None:
                out.add((cue, CUR.scopeRegion, LAND[code]))
            for occ in src.objects(hint, SRC_CUR.vorkommen):
                out.add((cue, CUR.occursIn, OCCURRENCE_MAP[str(occ).rsplit("/", 1)[-1]]))
            strength = src.value(hint, SRC_CUR.hinweisStaerke)
            verified = src.value(hint, SRC_CUR.verifiziert).toPython()
            if hid == SL_SUSPECT:
                strength, verified = Literal("0.5", datatype=XSD.decimal), False
                out.add((cue, CUR.negativeHint, Literal(
                    "Bereichsname des Berliner Bildungsprogramms 2014; SL-Zuordnung am Bildungsprogramm "
                    "für saarländische Krippen und Kindergärten (2018) prüfen.", lang="de")))
            if code == "DE-SH" and surface in SH_OLD_TERMS:
                verified = False
                out.add((cue, CUR.planGeneration, Literal("SH-Leitlinien vor der Neufassung 2026")))
            out.add((cue, CUR.strength, Literal(str(strength), datatype=XSD.decimal)))
            out.add((cue, CUR.verified, Literal(verified)))
            for src_p, new_p in [(SRC_CUR.erkennungshinweis, CUR.recognitionHint),
                                 (SRC_CUR.negativHinweis, CUR.negativeHint),
                                 (SRC_CUR.gueltigAb, CUR.validFrom), (SRC_CUR.gueltigBis, CUR.validUntil)]:
                for value in src.objects(hint, src_p):
                    out.add((cue, new_p, value))
            out.add((ELEM.Terminology, CUR.hasCue, cue))
    return out


HEADER = """# =============================================================================
# GENERIERT von werkzeuge/portiere_elementar_lexikon.py aus
# elementarbildung/extraktionshinweise-laender.ttl (ELEM V2, 201 Hinweise).
# Nicht von Hand ändern: Quelle oder Skript anpassen und neu erzeugen.
# Je Land ein Hinweis; Korrekturen laut ELEM-Bericht H.6 Nr. 2–6 angewandt.
# =============================================================================
"""


def main() -> None:
    src_path, ergebnis = Path(sys.argv[1]), Path(sys.argv[2])
    src = Graph()
    src.parse(src_path)
    out = port(src, load_labels(ergebnis))
    target = ergebnis / "profile" / "elementar-lexikon.ttl"
    target.write_bytes((HEADER + out.serialize(format="turtle")).replace("\r\n", "\n").encode("utf-8"))
    cues = len(set(out.subjects(RDF.type, CUR.LexicalCue)))
    print(f"{cues} cues from {len(set(src.subjects(RDF.type, SRC_CUR.Extraktionshinweis)))} hints -> {target}")


if __name__ == "__main__":
    main()
