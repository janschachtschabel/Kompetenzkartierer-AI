"""Check the curriculum-core ontology package for consistency.

Runs without network access. Checks:
  1. every Turtle file parses;
  2. every term of our namespaces that is used is also defined;
  3. concepts carry a German prefLabel and a scheme; notations are unique
     per scheme;
  4. node types, statement subkinds and document types hang under exactly
     one core value of the right core scheme;
  5. every cue has a role, a kind and a target and is listed in a profile's
     cur:hasCue; homonyms carry an alternative or a hint; every pattern
     compiles and matches its positive and none of its negative examples;
  6. JSON-schema enums equal the notations of the core schemes they name;
  7. SHACL: positive examples conform, negative examples raise exactly the
     violations they declare (ex:expectsViolationOf) and the warnings they
     declare (ex:expectsWarningOf), without RDFS inference and with
     ontology, vocabularies and profiles in the data graph;
  8. owl:imports point to ontologies of the package;
  9. the use-case queries in pruefung/abfragen/ find results on the
     positive examples.
Prints a lexicon collision report (same surface form, different targets,
overlapping scope, no homonym role) as information.

Usage: python -I pruefung/pruefe.py            (from the ergebnis folder)
Exit code 0 when no check failed.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import OWL, RDF, BNode, Graph, Namespace, URIRef
from rdflib.namespace import SKOS

ROOT = Path(__file__).resolve().parent.parent
CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
SH = Namespace("http://www.w3.org/ns/shacl#")
EX = Namespace("https://w3id.org/wlo/curriculum/example/")
OURS = "https://w3id.org/wlo/curriculum/"
MODEL_DIRS = ["ontologie", "vokabulare", "profile"]
CONCEPT_CLASSES = {
    SKOS.Concept, CUR.NodeType, CUR.StatementSubkind, CUR.DocumentType, CUR.CompetenceDimension,
    CUR.LevelConcept, CUR.CrossCuttingObjective, CUR.ContextConcept, CUR.OperatorLemma, CUR.OperatorEntry,
    CUR.AreaConcept, CUR.ContentConcept, CUR.CompetencyConcept,
}
SCHEME_CLASSES = {SKOS.ConceptScheme, CUR.CompetencyModel, CUR.LevelScheme, CUR.OperatorList}
BROADER_RULES = {CUR.NodeType: CV.NodeFunctions, CUR.StatementSubkind: CV.StatementKinds, CUR.DocumentType: CV.DocumentKinds}

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def parse_all(dirs: list[str]) -> dict[Path, Graph]:
    graphs = {}
    for d in dirs:
        for path in sorted((ROOT / d).glob("*.ttl")):
            g = Graph()
            try:
                g.parse(path, format="turtle")
            except Exception as exc:  # noqa: BLE001 - report every parse error, then go on
                fail(f"parse {path.relative_to(ROOT)}: {exc}")
                continue
            graphs[path] = g
    return graphs


def union(graphs) -> Graph:
    u = Graph()
    for g in graphs:
        for prefix, ns in g.namespaces():
            u.bind(prefix, ns, override=False)
        u += g
    return u


def ours(term) -> bool:
    return isinstance(term, URIRef) and str(term).startswith(OURS) and "/example/" not in str(term)


def check_defined(model: Graph, label: str, scope: Graph | None = None) -> None:
    defined = {s for s in model.subjects() if isinstance(s, URIRef)}
    used = set()
    for s, p, o in (scope or model):
        for t in (s, p, o):
            if ours(t):
                used.add(t)
    for t in sorted(used - defined):
        # ontology IRIs are defined by their owl:Ontology header
        fail(f"{label}: undefined term {t}")


def check_concepts(model: Graph) -> None:
    for cls in CONCEPT_CLASSES:
        for c in model.subjects(RDF.type, cls):
            if not ours(c):
                continue
            if not any(getattr(label, "language", None) == "de" for label in model.objects(c, SKOS.prefLabel)):
                fail(f"concept without prefLabel@de: {c}")
            if model.value(c, SKOS.inScheme) is None:
                fail(f"concept without skos:inScheme: {c}")
    seen = defaultdict(set)
    for c, n in model.subject_objects(SKOS.notation):
        for scheme in model.objects(c, SKOS.inScheme):
            key = (scheme, str(n))
            seen[key].add(c)
    for (scheme, n), cs in seen.items():
        if len(cs) > 1:
            fail(f"notation {n!r} not unique in {scheme}: {sorted(cs)}")
    for cls, scheme in BROADER_RULES.items():
        for c in model.subjects(RDF.type, cls):
            core = [b for b in model.objects(c, SKOS.broader) if (b, SKOS.inScheme, scheme) in model]
            if len(core) != 1:
                fail(f"{c} needs exactly one skos:broader in {scheme}, has {len(core)}")


def check_cues(model: Graph) -> int:
    tested = 0
    for cue in model.subjects(RDF.type, CUR.LexicalCue):
        name = str(cue).rsplit("#", 1)[-1]
        role = model.value(cue, CUR.cueRole)
        if role is None or model.value(cue, CUR.cueKind) is None or model.value(cue, CUR.mapsTo) is None:
            fail(f"cue {name}: role, kind and target are required")
        # tools (target-list export, prompts) reach cues only through a profile
        if (None, CUR.hasCue, cue) not in model:
            fail(f"cue {name}: not listed in any profile's cur:hasCue")
        if model.value(cue, CUR.surfaceForm) is None and model.value(cue, CUR.pattern) is None \
                and model.value(cue, CUR.layoutSignal) is None:
            fail(f"cue {name}: needs a surface form, a pattern or a layout signal")
        if role == CV.role_homonym and model.value(cue, CUR.alsoMapsTo) is None \
                and model.value(cue, CUR.recognitionHint) is None:
            fail(f"cue {name}: homonym without alternative or hint")
        for pat in model.objects(cue, CUR.pattern):
            try:
                rx = re.compile(str(pat))
            except re.error as exc:
                fail(f"cue {name}: pattern does not compile: {exc}")
                continue
            for ex in model.objects(cue, CUR.positiveExample):
                tested += 1
                if not rx.search(str(ex)):
                    fail(f"cue {name}: pattern misses positive example {str(ex)!r}")
            for ex in model.objects(cue, CUR.negativeExample):
                tested += 1
                if rx.search(str(ex)):
                    fail(f"cue {name}: pattern matches negative example {str(ex)!r}")
    return tested


def collision_report(model: Graph) -> list[str]:
    by_form = defaultdict(list)
    profile_of = {cue: prof for prof, cue in model.subject_objects(CUR.hasCue)}
    for cue in model.subjects(RDF.type, CUR.LexicalCue):
        form = model.value(cue, CUR.surfaceForm)
        if form is None:
            continue
        by_form[(profile_of.get(cue), str(form).casefold())].append(cue)
    lines = []
    for (prof, form), cues in sorted(by_form.items(), key=lambda kv: str(kv[0])):
        if len(cues) < 2:
            continue
        targets = {frozenset(model.objects(c, CUR.mapsTo)) for c in cues}
        if len(targets) < 2:
            continue
        roles = {model.value(c, CUR.cueRole) for c in cues}
        # a homonym carries its own rule; a negative cue is meant to contradict another target
        if CV.role_homonym in roles or CV.role_negative in roles:
            continue
        regions = [set(model.objects(c, CUR.scopeRegion)) for c in cues]
        overlap = any(not a or not b or a & b for i, a in enumerate(regions) for b in regions[i + 1:])
        if overlap:
            short = sorted(str(c).rsplit("#", 1)[-1] for c in cues)
            lines.append(f"  {form!r}: {', '.join(short)}")
    return lines


def check_schemas(model: Graph) -> int:
    count = 0
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        for node in walk_json(schema):
            if node.get("type") == "object":
                # strict structured-output mode: closed objects, every property required
                if node.get("additionalProperties") is not False or set(node.get("required", [])) != set(node.get("properties", {})):
                    fail(f"{path.name}: object {node.get('description')!r} is not strict-mode compatible")
            scheme = node.get("x-cv-scheme")
            if scheme is None:
                continue
            count += 1
            notations = {str(n) for c in model.subjects(SKOS.inScheme, CV[scheme])
                         for n in model.objects(c, SKOS.notation)}
            enum = set(node.get("enum") or node.get("items", {}).get("enum", [])) - {None}
            if not notations:
                fail(f"{path.name}: cv:{scheme} has no notations")
            elif node.get("x-cv-subset"):
                if not enum <= notations:
                    fail(f"{path.name}: subset for cv:{scheme} has unknown values {sorted(enum - notations)}")
            elif enum != notations:
                fail(f"{path.name}: enum for cv:{scheme} differs: missing {sorted(notations - enum)}, "
                     f"extra {sorted(enum - notations)}")
    return count


def walk_json(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk_json(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_json(v)


def check_imports(model: Graph) -> None:
    ontologies = set(model.subjects(RDF.type, OWL.Ontology))
    for o in model.objects(None, OWL.imports):
        if str(o).startswith(OURS) and o not in ontologies:
            fail(f"owl:imports points to unknown ontology {o}")


def shape_of(result: Graph, src, shapes: Graph):
    """Map a result's sourceShape (often a blank property shape) to its node shape."""
    if isinstance(src, BNode):
        parent = shapes.value(None, SH.property, src)
        return parent if parent is not None else src
    return src


def check_shacl(model: Graph) -> int:
    from pyshacl import validate

    shapes = Graph()
    shapes.parse(ROOT / "ontologie" / "cur-shapes.ttl", format="turtle")
    extra = ROOT / "profile" / "profil-shapes.ttl"
    if extra.exists():
        shapes.parse(extra, format="turtle")
    runs = 0
    for path in sorted((ROOT / "beispiele").glob("*.ttl")):
        data = Graph()
        data.parse(path, format="turtle")
        expected = {(focus, shp) for case in data.subjects(EX.expectsViolationOf, None)
                    for shp in data.objects(case, EX.expectsViolationOf)
                    for focus in data.objects(case, EX.focus)}
        expected_warnings = {(focus, shp) for case in data.subjects(EX.expectsWarningOf, None)
                             for shp in data.objects(case, EX.expectsWarningOf)
                             for focus in data.objects(case, EX.focus)}
        full = model + data
        conforms, report, text = validate(full, shacl_graph=shapes, inference="none", advanced=True,
                                          allow_warnings=True, meta_shacl=False)
        runs += 1
        violations = set()
        warned = set()
        warnings = 0
        for res in report.subjects(RDF.type, SH.ValidationResult):
            sev = report.value(res, SH.resultSeverity)
            key = (report.value(res, SH.focusNode), shape_of(report, report.value(res, SH.sourceShape), shapes))
            if sev != SH.Violation:
                warnings += 1
                warned.add(key)
                continue
            violations.add(key)
        name = path.name
        missing_warnings = expected_warnings - warned
        if missing_warnings:
            fail(f"SHACL {name}: expected warnings not raised: {sorted(missing_warnings, key=str)}")
        elif expected_warnings:
            print(f"  SHACL {name}: {len(expected_warnings)} expected warnings raised")
        if not expected:
            if violations:
                listing = "\n".join(f"    {f} <- {s}" for f, s in sorted(violations, key=str))
                fail(f"SHACL {name}: expected to conform, got {len(violations)} violations:\n{listing}")
            else:
                print(f"  SHACL {name}: conforms ({warnings} warnings/infos)")
        else:
            missing = expected - violations
            unexpected = {v for v in violations if v[0] not in {f for f, _ in expected}}
            if missing:
                fail(f"SHACL {name}: expected violations not raised: {sorted(missing, key=str)}")
            if unexpected:
                fail(f"SHACL {name}: unexpected violations: {sorted(unexpected, key=str)}")
            if not missing and not unexpected:
                print(f"  SHACL {name}: {len(expected)} expected violations raised ({warnings} warnings/infos)")
    return runs


def check_queries(model: Graph, examples: dict[Path, Graph]) -> None:
    """Run the use-case queries on model + positive examples; each must find something."""
    data = model + union(g for p, g in examples.items() if not p.name.startswith("fehlerhaft"))
    for path in sorted((ROOT / "pruefung" / "abfragen").glob("*.rq")):
        rows = list(data.query(path.read_text(encoding="utf-8")))
        if not rows:
            fail(f"query {path.name} returned no rows on the examples")
            continue
        print(f"  {path.name}: {len(rows)} rows")
        for row in rows[:3]:
            print("    " + " | ".join(short(v) for v in row))


def short(value) -> str:
    text = str(value)
    for sep in ("#", "/"):
        if isinstance(value, URIRef) and sep in text:
            text = text.rsplit(sep, 1)[-1]
            break
    return text if len(text) <= 70 else text[:67] + "…"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    graphs = parse_all(MODEL_DIRS)
    model = union(graphs.values())
    print(f"parsed {len(graphs)} model files, {len(model)} triples")
    check_defined(model, "model")
    check_concepts(model)
    tested = check_cues(model)
    print(f"cues: {len(set(model.subjects(RDF.type, CUR.LexicalCue)))}, pattern examples tested: {tested}")
    check_imports(model)
    print(f"schema enums checked: {check_schemas(model)}")
    examples = parse_all(["beispiele"])
    for path, g in examples.items():
        check_defined(model + g, f"example {path.name}", scope=g)
    if examples:
        print(f"SHACL runs: {check_shacl(model)}")
        print("use-case queries:")
        check_queries(model, examples)
    lines = collision_report(model)
    print(f"lexicon collisions (same form, different targets, overlapping scope, no homonym): {len(lines)}")
    for line in lines:
        print(line)
    if failures:
        print(f"\nFAILED: {len(failures)}")
        for f in failures:
            print(" -", f)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
