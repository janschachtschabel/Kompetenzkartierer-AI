"""Export the current lexicon as checklists for the state research briefs.

Writes recherche-auftraege/vorlisten/:
  <bereich>-ziele.csv      allowed targets of the profile (node types,
                           statement subkinds, document types), the concepts
                           of the profile's schemes (fields, principles,
                           school types …) and the shared vocabularies
                           (contexts, cross-cutting objectives, levels,
                           competence dimensions) with a short definition –
                           the research maps found terms onto these IDs or
                           marks them "neu";
  <bereich>-<land>.csv     every cue that applies to a state (DE-XX), to all
                           states (DE) or has no state scope (ohne-land) –
                           the research confirms, corrects or rejects them.
Semicolon-separated UTF-8, one row per cue and state.

Usage: python -I exportiere_vorlisten.py <ergebnis-dir>
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Namespace
from rdflib.namespace import SKOS

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
SECTORS = {CV.sec_school: "schule", CV.sec_elementary: "elementar", CV.sec_vocational: "beruf",
           CV.sec_higher: "hochschule", CV.sec_adult: "erwachsenenbildung"}
PREFIXES = {
    "https://w3id.org/wlo/curriculum/profile/school#": "schul:",
    "https://w3id.org/wlo/curriculum/profile/early-childhood#": "elem:",
    "https://w3id.org/wlo/curriculum/profile/vocational#": "beruf:",
    "https://w3id.org/wlo/curriculum/profile/higher-education#": "hs:",
    "https://w3id.org/wlo/curriculum/profile/adult-education#": "eb:",
    "https://w3id.org/wlo/curriculum/core#": "cur:",
    "https://w3id.org/wlo/curriculum/vocab#": "cv:",
    "https://w3id.org/wlo/curriculum/level/": "lvl:",
    "https://w3id.org/wlo/curriculum/crosscutting/": "qz:",
    "https://w3id.org/wlo/curriculum/dimension/": "kd:",
    "https://w3id.org/wlo/curriculum/context/": "ctx:",
    "https://w3id.org/wlo/curriculum/region/": "land:",
}
TARGET_KINDS = ((CUR.NodeType, "Knotentyp"), (CUR.StatementSubkind, "Aussage-Unterart"), (CUR.DocumentType, "Dokumenttyp"))
# shared vocabularies every sector may map onto (ISCED-F fields and regions are left out: too long, not looked up by term)
SHARED_NAMESPACES = ("https://w3id.org/wlo/curriculum/context/", "https://w3id.org/wlo/curriculum/crosscutting/",
                     "https://w3id.org/wlo/curriculum/level/", "https://w3id.org/wlo/curriculum/dimension/")


def short(iri) -> str:
    text = str(iri)
    for ns, prefix in PREFIXES.items():
        if text.startswith(ns):
            return prefix + text[len(ns):]
    return text


def label(g: Graph, iri) -> str:
    # concepts carry skos:prefLabel, classes and properties of the core rdfs:label
    for prop in (SKOS.prefLabel, RDFS.label):
        for lab in g.objects(iri, prop):
            if getattr(lab, "language", None) == "de":
                return str(lab)
    return ""


def first_sentence(text: str, limit: int = 220) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def german(g: Graph, iri, prop) -> str:
    values = [v for v in g.objects(iri, prop) if getattr(v, "language", None) in ("de", None)]
    return first_sentence(values[0]) if values else ""


def targets_of_profile(g: Graph, namespace: str):
    rows = []
    for cls, kind in TARGET_KINDS:
        for c in sorted(g.subjects(RDF.type, cls)):
            if not str(c).startswith(namespace):
                continue
            core = [b for b in g.objects(c, SKOS.broader) if str(b).startswith(str(CV))]
            rows.append([short(c), kind, label(g, c), ", ".join(short(b) for b in core),
                         german(g, c, SKOS.definition) or german(g, c, SKOS.scopeNote)])
    return rows


def concepts_in_schemes(g: Graph, namespace: str):
    """Every member of a concept scheme declared in `namespace`, grouped by scheme.

    Without these rows the research invented IDs for fields, principles and
    contexts (pilot BB: ctx:reading, ctx:outdoor …) because only node types
    were listed.
    """
    rows = []
    schemes = sorted({s for s in g.objects(None, SKOS.inScheme) if str(s).startswith(namespace)})
    for scheme in schemes:
        for c in sorted(g.subjects(SKOS.inScheme, scheme)):
            if any((c, RDF.type, cls) in g for cls, _ in TARGET_KINDS):
                continue  # already listed with its kind by targets_of_profile
            related = [o for p in (SKOS.broader, SKOS.broadMatch, SKOS.closeMatch, SKOS.exactMatch)
                       for o in g.objects(c, p) if short(o) != str(o)]
            alt = sorted(str(a) for a in g.objects(c, SKOS.altLabel) if getattr(a, "language", None) == "de")
            note = german(g, c, SKOS.definition) or german(g, c, SKOS.scopeNote)
            if alt:
                note = first_sentence(f"auch: {', '.join(alt)}" + (f". {note}" if note else ""))
            rows.append([short(c), f"Konzept: {label(g, scheme) or short(scheme)}", label(g, c),
                         ", ".join(sorted(short(r) for r in related)), note])
    return rows


def main() -> None:
    ergebnis = Path(sys.argv[1])
    g = Graph()
    for d in ("ontologie", "vokabulare", "profile"):
        for p in sorted((ergebnis / d).glob("*.ttl")):
            g.parse(p)
    out = ergebnis / "recherche-auftraege" / "vorlisten"
    out.mkdir(parents=True, exist_ok=True)
    header = ["land", "begriff_oder_muster", "rolle", "ziel", "ziel_label", "fundort", "dokumenttyp", "plangeneration",
              "staerke", "geprueft", "regel_oder_hinweis", "hinweis_id"]
    shared = [row for ns in SHARED_NAMESPACES for row in concepts_in_schemes(g, ns)]
    written = 0
    for profile, sector in g.subject_objects(CUR.profileScope):
        name = SECTORS.get(sector)
        if name is None:
            continue
        namespace = str(profile).rsplit("#", 1)[0] + "#"
        with open(out / f"{name}-ziele.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";", lineterminator="\n")
            w.writerow(["id", "art", "label", "kernfunktion_oder_kernart", "definition"])
            w.writerows(targets_of_profile(g, namespace))
            w.writerows(concepts_in_schemes(g, namespace))
            w.writerows(shared)
        by_land = defaultdict(list)
        for cue in g.objects(profile, CUR.hasCue):
            lands = [short(r).replace("land:", "") for r in g.objects(cue, CUR.scopeRegion)] or ["ohne-land"]
            form = g.value(cue, CUR.surfaceForm) or g.value(cue, CUR.pattern) or short(g.value(cue, CUR.layoutSignal) or "")
            targets = sorted(g.objects(cue, CUR.mapsTo), key=str)
            row = [None, str(form), short(g.value(cue, CUR.cueRole)).replace("cv:role_", ""),
                   ", ".join(short(t) for t in targets), ", ".join(filter(None, (label(g, t) for t in targets))),
                   ", ".join(short(o).replace("cv:occ_", "") for o in g.objects(cue, CUR.occursIn)),
                   ", ".join(short(t) for t in g.objects(cue, CUR.scopeDocumentType)),
                   str(g.value(cue, CUR.planGeneration) or ""), str(g.value(cue, CUR.strength) or ""),
                   "ja" if str(g.value(cue, CUR.verified)) == "true" else "nein",
                   german(g, cue, CUR.recognitionHint) or german(g, cue, CUR.negativeHint), short(cue)]
            for land in lands:
                by_land[land].append([land] + row[1:])
        for land, rows in sorted(by_land.items()):
            with open(out / f"{name}-{land}.csv", "w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh, delimiter=";", lineterminator="\n")
                w.writerow(header)
                w.writerows(sorted(rows, key=lambda r: (r[3], r[1].casefold())))
            written += 1
    print(f"wrote {written} state lists and target lists to {out}")


if __name__ == "__main__":
    main()
