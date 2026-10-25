"""The SHACL validation X5 runs in a child process (plan M1 8.4; app/pipeline/shacl.py starts it).

As ontology/pruefung/pruefe.py checks the examples: the shapes of cur-shapes.ttl and profil-shapes.ttl,
no inference (konzept §14: RDFS inference would hide 22 class checks), the model in the data graph -
``sh:class`` reads ``rdfs:subClassOf`` from cur-kern, the In… shapes ``skos:inScheme``, the node type and
subkind checks ``skos:broader``. Measured on the examples and on documents as the export writes them
(plan M1, Nachtrag 8a): the model without the lexicons, alignments and migration, and the document's
rows as the only focus nodes, find what the whole model finds; and rdflib parses and translates a
SPARQL constraint's query anew for each focus node - two thirds of the time - so its translation is kept
for the run (``queries_kept_translated``), the reuse rdflib's ``prepareQuery`` stands for. A document of
2,400 rows took 43 s so, 192 s without.

pyshacl is imported here alone, in the child: the worker never loads it.
"""

import contextlib
import json
import logging
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

from rdflib import RDF, BNode, Graph, Namespace, URIRef

from app.core.child import ChildLog, stand_alone, write
from app.vocab.loader import MODEL_DIRS

SH = Namespace("http://www.w3.org/ns/shacl#")
SHAPE_FILES = ("ontologie/cur-shapes.ttl", "profile/profil-shapes.ttl")
_LEFT_OUT = ("-lexikon", "cur-alignments", "migration")  # no shape a document's row meets reads them
_LIBRARIES = ("rdflib", "pyshacl", "owlrl")
_SEVERITIES = {str(SH.Violation): "violation", str(SH.Warning): "warning", str(SH.Info): "info"}
_PREFIXES = (
    ("cur", "https://w3id.org/wlo/curriculum/core#"),
    ("dct", "http://purl.org/dc/terms/"),
    ("skos", "http://www.w3.org/2004/02/skos/core#"),
)


class ShaclResult(NamedTuple):
    focus: str  # the focus node's IRI
    shape: str  # the node shape's name in shs: (of a property shape, its node shape's)
    severity: str  # violation, warning, info
    path: str | None  # the property, as a CURIE where its namespace is bound
    message: str
    value: str | None
    component: str | None  # the constraint component's name


def model_paths(ontology_dir: Path) -> list[Path]:
    # the folders the image holds; their files, not their subfolders: as pruefe.py
    paths = [path for folder in MODEL_DIRS for path in sorted((ontology_dir / folder).glob("*.ttl"))]
    return [path for path in paths if not any(mark in path.name for mark in _LEFT_OUT)]


def validate_graph(ontology_dir: Path, data: Graph) -> list[ShaclResult]:
    """The results of the shapes over ``data`` at its subjects: the model read, the queries kept."""
    from pyshacl import validate

    shapes = _parsed([ontology_dir / name for name in SHAPE_FILES])
    model = _parsed(model_paths(ontology_dir))
    focus: list[str | URIRef] = sorted(
        {subject for subject in data.subjects() if isinstance(subject, URIRef)}
    )
    with queries_kept_translated():
        _, report, _ = validate(
            model + data, shacl_graph=shapes, inference="none", advanced=True, allow_warnings=True,
            meta_shacl=False, focus_nodes=focus,
        )  # fmt: skip
    return _results(report, shapes, data)


@contextlib.contextmanager
def queries_kept_translated() -> Iterator[None]:
    """rdflib's SPARQL queries translated once each, while the block runs: pyshacl asks the same query
    text for each focus node, with ``$this`` bound by initBindings, and rdflib parses it each time."""
    from rdflib.plugins.sparql import processor
    from rdflib.plugins.sparql.algebra import translateQuery
    from rdflib.plugins.sparql.evaluate import evalQuery
    from rdflib.plugins.sparql.parser import parseQuery

    asked = processor.SPARQLProcessor.query
    kept: dict[tuple[Any, ...], Any] = {}

    def query(  # the signature of SPARQLProcessor.query
        self: Any,
        text: Any,
        initBindings: Any = None,
        initNs: Any = None,
        base: Any = None,
        DEBUG: bool = False,
    ) -> Any:
        if not isinstance(text, str):
            return asked(self, text, initBindings or {}, initNs or {}, base, DEBUG)
        key = (text, base, tuple(sorted((initNs or {}).items())))
        if key not in kept:
            kept[key] = translateQuery(parseQuery(text), base, initNs or {})
        return evalQuery(self.graph, kept[key], initBindings or {}, base)

    processor.SPARQLProcessor.query = query  # type: ignore[method-assign, assignment]
    try:
        yield
    finally:
        processor.SPARQLProcessor.query = asked  # type: ignore[method-assign]


def run_child(ontology_dir: str, data: str, told: ChildLog, out: str) -> None:
    """The child: validate the N-Triples ``data``, and leave the results in ``out``."""
    stand_alone(told, _LIBRARIES)
    try:
        results = validate_graph(Path(ontology_dir), Graph().parse(data=data, format="nt"))
    except Exception as error:
        frames = "".join(traceback.format_tb(error.__traceback__))
        logging.getLogger(__name__).error("the SHACL validation raised %s\n%s", type(error).__name__, frames)
        write(Path(out) / "crashed.json", json.dumps({"error": type(error).__name__}))
        raise SystemExit(1) from None
    write(Path(out) / "result.json", json.dumps([list(result) for result in results]))


def _parsed(paths: list[Path]) -> Graph:
    graph = Graph()
    for path in paths:
        graph.parse(path, format="turtle")
    return graph


def _results(report: Graph, shapes: Graph, data: Graph) -> list[ShaclResult]:
    subjects = set(data.subjects())
    found = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        focus = report.value(result, SH.focusNode)
        if focus not in subjects:
            continue
        shape = report.value(result, SH.sourceShape)
        if isinstance(shape, BNode):
            shape = shapes.value(None, SH.property, shape) or shape
        path = report.value(result, SH.resultPath)
        value = report.value(result, SH.value)
        component = report.value(result, SH.sourceConstraintComponent)
        found.append(
            ShaclResult(
                str(focus), _name(shape), _SEVERITIES[str(report.value(result, SH.resultSeverity))],
                _curie(path) if isinstance(path, URIRef) else None,
                str(report.value(result, SH.resultMessage) or ""),
                None if value is None else str(value), None if component is None else _name(component),
            )
        )  # fmt: skip
    return sorted(found, key=lambda result: [part or "" for part in result])


def _curie(path: URIRef) -> str:
    for prefix, namespace in _PREFIXES:
        if str(path).startswith(namespace):
            return f"{prefix}:{str(path).removeprefix(namespace)}"
    return str(path)


def _name(term: Any) -> str:
    text = str(term)
    return text.rsplit("#", 1)[-1] if "#" in text else text
