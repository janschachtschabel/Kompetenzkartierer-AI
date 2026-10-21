"""Check research results (recherche-ergebnisse/*.md) before they are imported.

For every CSV block of a result file:
  - which table it is (recognised by its header line);
  - rows whose column count differs from the header (unquoted semicolons
    inside a field shift the columns);
  - fixed-value columns (funktion, rolle, beleg, abgleich_vorliste) outside
    the allowed values;
  - ziel_id values that are neither "neu" nor an existing term of the model;
  - share of rows with evidence E.
Prints one block per file; exit code 0 always (this is a report, not a gate).

Usage: python -I pruefe_recherche.py <ergebnis-dir> [file ...]
"""

from __future__ import annotations

import csv
import io
import re
import sys
from collections import Counter
from pathlib import Path

from rdflib import Graph

PREFIXES = {
    "cur:": "https://w3id.org/wlo/curriculum/core#",
    "cv:": "https://w3id.org/wlo/curriculum/vocab#",
    "lvl:": "https://w3id.org/wlo/curriculum/level/",
    "qz:": "https://w3id.org/wlo/curriculum/crosscutting/",
    "kd:": "https://w3id.org/wlo/curriculum/dimension/",
    "ctx:": "https://w3id.org/wlo/curriculum/context/",
    "fld:": "https://w3id.org/wlo/curriculum/field/",
    "land:": "https://w3id.org/wlo/curriculum/region/",
    "schul:": "https://w3id.org/wlo/curriculum/profile/school#",
    "elem:": "https://w3id.org/wlo/curriculum/profile/early-childhood#",
    "beruf:": "https://w3id.org/wlo/curriculum/profile/vocational#",
    "hs:": "https://w3id.org/wlo/curriculum/profile/higher-education#",
    "eb:": "https://w3id.org/wlo/curriculum/profile/adult-education#",
}
ROLES = {"pref", "alt", "cue", "negative", "homonym"}
EVIDENCE = {"E", "S", "A"}
MATCH = {"bestaetigt", "korrigiert", "neu", "nicht_gefunden"}
FUNCTION = re.compile(r"^(dokumenttyp|gliederung:\w+|aussage:\w+|niveau|zeit|verbindlichkeit|querschnittsmarker|"
                      r"verweismarker|kontext|lernort|feld|regel|anerkennung|sonstiges)$")
BLOCK = re.compile(r"```csv\s*\n(.*?)```", re.S)


def model_terms(ergebnis: Path) -> set[str]:
    g = Graph()
    for d in ("ontologie", "vokabulare", "profile"):
        for p in sorted((ergebnis / d).glob("*.ttl")):
            g.parse(p)
    terms = set()
    for s in g.subjects():
        text = str(s)
        for prefix, ns in PREFIXES.items():
            if text.startswith(ns):
                terms.add(prefix + text[len(ns):])
    return terms


def check_file(path: Path, terms: set[str]) -> None:
    text = path.read_text(encoding="utf-8")
    print(f"== {path.name}")
    for block in BLOCK.findall(text):
        rows = list(csv.reader(io.StringIO(block.strip()), delimiter=";"))
        if not rows:
            continue
        header, data = rows[0], rows[1:]
        name = ";".join(header[:3])
        shifted = [i + 2 for i, r in enumerate(data) if len(r) != len(header)]
        col = {h: i for i, h in enumerate(header)}
        bad = Counter()
        unknown = Counter()
        evidence = Counter()
        for r in data:
            if len(r) != len(header):
                continue

            def val(key):
                return r[col[key]].strip() if key in col else None

            if val("rolle") not in (None, "", "-") and val("rolle") not in ROLES:
                bad["rolle=" + val("rolle")] += 1
            if val("abgleich_vorliste") not in (None, "", "-") and val("abgleich_vorliste") not in MATCH:
                bad["abgleich=" + val("abgleich_vorliste")] += 1
            if val("funktion") not in (None, "", "-"):
                for f in re.split(r"\s*\|\s*", val("funktion")):
                    if not FUNCTION.match(f):
                        bad["funktion=" + f] += 1
            if val("beleg") is not None:
                evidence[val("beleg")[:1] if val("beleg") else ""] += 1
            ziel = val("ziel_id")
            if ziel and ziel not in ("neu", "-"):
                # briefs separate several targets with " | "; older results used commas
                for z in re.split(r"\s*[,|]\s*", ziel):
                    if z and z not in ("neu", "-") and z not in terms:
                        unknown[z] += 1
        total_ev = sum(evidence.values())
        share = f"{evidence['E'] / total_ev:.0%} E" if total_ev else "–"
        print(f"  [{name}…] {len(data)} rows, shifted {len(shifted)}{' (lines ' + ','.join(map(str, shifted[:8])) + ('…' if len(shifted) > 8 else '') + ')' if shifted else ''}, evidence {share}")
        if bad:
            print("    not allowed: " + ", ".join(f"{k} ×{v}" for k, v in bad.most_common(8)))
        if unknown:
            print("    unknown ziel_id: " + ", ".join(f"{k} ×{v}" for k, v in unknown.most_common(12)))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ergebnis = Path(sys.argv[1])
    files = [Path(f) for f in sys.argv[2:]] or sorted((ergebnis / "recherche-ergebnisse").glob("*.md"))
    terms = model_terms(ergebnis)
    for f in files:
        if f.name != "README.md":
            check_file(f, terms)


if __name__ == "__main__":
    main()
