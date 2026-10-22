"""The vocabularies of Curriculum-Kern 1.0, read from the ontology's Turtle files.

A scheme is any resource typed as one of SCHEME_CLASSES; a concept is any resource in such a
scheme (``skos:inScheme``) - the levels are ``cur:LevelConcept``, not ``skos:Concept``. The
SKOS core fields become columns; every other statement about a scheme or concept is kept in
``properties``, so a new property in the Turtle files needs no migration. A vocabulary the
tables cannot hold faithfully (a concept in two schemes, two labels in one language, a
broader concept that does not exist) is refused rather than trimmed.
"""

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import SKOS, XSD
from rdflib.term import Node

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
# The folders pruefe.py reads as the model; examples and research material stay out
MODEL_DIRS = ("ontologie", "vokabulare", "profile")
SCHEME_CLASSES = frozenset({SKOS.ConceptScheme, CUR.CompetencyModel, CUR.LevelScheme, CUR.OperatorList})
NO_LANGUAGE = "und"  # BCP 47 for "undetermined"
# Raised with every change to what the reader yields, so the same files load anew afterwards
READER_FORMAT = 1
# A relative IRI resolves under this base (.invalid is reserved) and is refused: against the
# file's own place it would differ from machine to machine
_RELATIVE_BASE = "https://relative.invalid/"
_SCHEME_COLUMNS = frozenset({RDF.type, SKOS.prefLabel})
_CONCEPT_COLUMNS = frozenset(
    {RDF.type, SKOS.inScheme, SKOS.prefLabel, SKOS.altLabel, SKOS.notation, SKOS.definition, SKOS.broader}
)

Properties = dict[str, list[dict[str, str]]]


class VocabularyError(Exception):
    """The Turtle files hold something the vocabulary tables cannot represent as it is."""


@dataclass(frozen=True)
class Scheme:
    iri: str
    types: list[str]
    pref_labels: dict[str, str]
    properties: Properties = field(default_factory=dict)


@dataclass(frozen=True)
class Concept:
    iri: str
    scheme: str
    types: list[str]
    notation: str | None
    pref_labels: dict[str, str]
    alt_labels: dict[str, list[str]]
    definitions: dict[str, str]
    broader: list[str]
    properties: Properties = field(default_factory=dict)


@dataclass(frozen=True)
class Vocabulary:
    content_hash: str  # over the files' names and SHA-256 digests
    files: dict[str, str]
    schemes: dict[str, Scheme]
    concepts: dict[str, Concept]


def read_vocabulary(root: Path) -> Vocabulary:
    """Schemes and concepts of the model folders under ``root`` (the ``ontology`` folder).

    A missing or empty model folder, or files without any scheme, are refused: read as a
    smaller vocabulary, a wrong ONTOLOGY_DIR would retire everything it does not hold.
    """
    root = root.resolve()
    graph = Graph()
    files: dict[str, str] = {}
    for path in _model_files(root):
        content = path.read_bytes()
        name = path.relative_to(root).as_posix()
        files[name] = hashlib.sha256(content).hexdigest()
        try:
            graph.parse(data=content, format="turtle", publicID=_RELATIVE_BASE + name)
        except Exception as error:  # rdflib reports bad Turtle as SyntaxError, IndexError, ...
            raise VocabularyError(f"{name} does not parse: {error}") from error
    _refuse_relative_iris(graph)
    entries = [f"{name} {digest}" for name, digest in sorted(files.items())]
    listing = "\n".join([f"reader {READER_FORMAT}", *entries])
    schemes = {
        str(iri): _scheme(graph, iri)
        for iri in sorted({iri for cls in SCHEME_CLASSES for iri in graph.subjects(RDF.type, cls)}, key=str)
        if isinstance(iri, URIRef)
    }
    if not schemes:
        raise VocabularyError(f"no scheme in {root}: is ONTOLOGY_DIR the ontology folder?")
    concepts = _concepts(graph, schemes)
    return Vocabulary(hashlib.sha256(listing.encode()).hexdigest(), files, schemes, concepts)


def _model_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise VocabularyError(f"{root} is no folder: is ONTOLOGY_DIR the ontology folder?")
    paths: list[Path] = []
    for directory in MODEL_DIRS:
        found = sorted((root / directory).glob("*.ttl"))
        if not found:
            raise VocabularyError(f"{root / directory} holds no Turtle files: is ONTOLOGY_DIR right?")
        paths.extend(found)
    return sorted(paths)


def _refuse_relative_iris(graph: Graph) -> None:
    for triple in graph:
        for term in triple:
            if isinstance(term, URIRef) and str(term).startswith(_RELATIVE_BASE):
                place = str(term).removeprefix(_RELATIVE_BASE)
                raise VocabularyError(f"relative IRI <{place}>: write the full IRI")


def _scheme(graph: Graph, iri: URIRef) -> Scheme:
    return Scheme(
        iri=str(iri),
        types=_iris(graph.objects(iri, RDF.type)),
        pref_labels=_one_per_language(graph, iri, SKOS.prefLabel),
        properties=_properties(graph, iri, _SCHEME_COLUMNS),
    )


def _concepts(graph: Graph, schemes: dict[str, Scheme]) -> dict[str, Concept]:
    members: dict[URIRef, list[str]] = defaultdict(list)
    for iri, scheme in graph.subject_objects(SKOS.inScheme):
        if isinstance(iri, URIRef) and str(scheme) in schemes:
            members[iri].append(str(scheme))
    concepts = {}
    for iri in sorted(members, key=str):
        if len(members[iri]) > 1:
            raise VocabularyError(f"{iri} is in more than one scheme: {sorted(members[iri])}")
        outside = sorted(
            str(other) for other in graph.objects(iri, SKOS.inScheme) if str(other) not in schemes
        )
        if outside:
            raise VocabularyError(f"{iri} is also in a scheme the model does not define: {outside}")
        concepts[str(iri)] = Concept(
            iri=str(iri),
            scheme=members[iri][0],
            types=_iris(graph.objects(iri, RDF.type)),
            notation=_notation(graph, iri),
            pref_labels=_one_per_language(graph, iri, SKOS.prefLabel),
            alt_labels=_all_per_language(graph, iri, SKOS.altLabel),
            definitions=_one_per_language(graph, iri, SKOS.definition),
            broader=_broader(graph, iri),
            properties=_properties(graph, iri, _CONCEPT_COLUMNS),
        )
    _check_links(concepts)
    return concepts


def _check_links(concepts: dict[str, Concept]) -> None:
    """Every broader concept exists; a notation names one concept within its scheme."""
    named: dict[tuple[str, str], str] = {}
    for concept in concepts.values():
        for broader in concept.broader:
            if broader not in concepts:
                raise VocabularyError(f"{concept.iri}: broader {broader} is no concept of the vocabularies")
        if concept.notation is not None:
            first = named.setdefault((concept.scheme, concept.notation), concept.iri)
            if first != concept.iri:
                raise VocabularyError(
                    f"notation {concept.notation} twice in {concept.scheme}: {first}, {concept.iri}"
                )


def _notation(graph: Graph, iri: URIRef) -> str | None:
    values = list(graph.objects(iri, SKOS.notation))
    if len(values) > 1:
        raise VocabularyError(f"{iri} has more than one notation: {sorted(str(value) for value in values)}")
    if not values:
        return None
    value = values[0]
    if not isinstance(value, Literal) or value.datatype not in (None, XSD.string):
        raise VocabularyError(f"{iri}: a notation is a plain string, not {value!r}")
    return str(value)


def _broader(graph: Graph, iri: URIRef) -> list[str]:
    values = list(graph.objects(iri, SKOS.broader))
    if any(not isinstance(value, URIRef) for value in values):
        raise VocabularyError(f"{iri}: broader must name a concept by its IRI")
    return _iris(values)


def _iris(nodes: Iterable[Node]) -> list[str]:
    return sorted(str(node) for node in nodes if isinstance(node, URIRef))


def _all_per_language(graph: Graph, iri: URIRef, predicate: URIRef) -> dict[str, list[str]]:
    texts: dict[str, list[str]] = defaultdict(list)
    for value in graph.objects(iri, predicate):
        if not isinstance(value, Literal):
            name = predicate.split("#")[-1]
            raise VocabularyError(f"{iri} {name}: text belongs here, not {value!r}")
        # BCP 47 tags ignore case: "de" and "DE" are one language
        texts[(value.language or NO_LANGUAGE).lower()].append(str(value))
    return {language: sorted(values) for language, values in sorted(texts.items())}


def _one_per_language(graph: Graph, iri: URIRef, predicate: URIRef) -> dict[str, str]:
    texts = _all_per_language(graph, iri, predicate)
    for language, values in texts.items():
        if len(values) > 1:
            name = predicate.split("#")[-1]
            raise VocabularyError(f"{iri} has more than one {name} in language {language}: {values}")
    return {language: values[0] for language, values in texts.items()}


def _properties(graph: Graph, iri: URIRef, columns: frozenset[URIRef]) -> Properties:
    found: dict[str, list[dict[str, str]]] = defaultdict(list)
    for predicate, value in graph.predicate_objects(iri):
        if predicate not in columns:
            found[str(predicate)].append(_value(iri, predicate, value))
    return {
        predicate: sorted(values, key=lambda value: json.dumps(value, sort_keys=True))
        for predicate, values in sorted(found.items())
    }


def _value(iri: URIRef, predicate: Node, value: Node) -> dict[str, str]:
    if isinstance(value, URIRef):
        return {"iri": str(value)}
    if isinstance(value, Literal):
        literal = {"value": str(value)}
        if value.language:
            literal["lang"] = value.language
        elif value.datatype is not None:
            literal["datatype"] = str(value.datatype)
        return literal
    raise VocabularyError(f"{iri} {predicate}: a blank node has no place in the vocabulary tables")
