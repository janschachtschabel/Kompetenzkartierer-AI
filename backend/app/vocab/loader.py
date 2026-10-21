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
from rdflib.namespace import SKOS
from rdflib.term import Node

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
# The folders pruefe.py reads as the model; examples and research material stay out
MODEL_DIRS = ("ontologie", "vokabulare", "profile")
SCHEME_CLASSES = frozenset({SKOS.ConceptScheme, CUR.CompetencyModel, CUR.LevelScheme, CUR.OperatorList})
NO_LANGUAGE = "und"  # BCP 47 for "undetermined"
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
    """Schemes and concepts of the model folders under ``root`` (the ``ontology`` folder)."""
    graph = Graph()
    files: dict[str, str] = {}
    for path in sorted(path for directory in MODEL_DIRS for path in (root / directory).glob("*.ttl")):
        content = path.read_bytes()
        files[path.relative_to(root).as_posix()] = hashlib.sha256(content).hexdigest()
        graph.parse(data=content, format="turtle", publicID=path.as_uri())
    listing = "\n".join(f"{name} {digest}" for name, digest in sorted(files.items()))
    schemes = {
        str(iri): _scheme(graph, iri)
        for iri in sorted({iri for cls in SCHEME_CLASSES for iri in graph.subjects(RDF.type, cls)}, key=str)
        if isinstance(iri, URIRef)
    }
    concepts = _concepts(graph, schemes)
    return Vocabulary(hashlib.sha256(listing.encode()).hexdigest(), files, schemes, concepts)


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
        notations = [str(notation) for notation in graph.objects(iri, SKOS.notation)]
        if len(notations) > 1:
            raise VocabularyError(f"{iri} has more than one notation: {sorted(notations)}")
        concepts[str(iri)] = Concept(
            iri=str(iri),
            scheme=members[iri][0],
            types=_iris(graph.objects(iri, RDF.type)),
            notation=notations[0] if notations else None,
            pref_labels=_one_per_language(graph, iri, SKOS.prefLabel),
            alt_labels=_all_per_language(graph, iri, SKOS.altLabel),
            definitions=_one_per_language(graph, iri, SKOS.definition),
            broader=_iris(graph.objects(iri, SKOS.broader)),
            properties=_properties(graph, iri, _CONCEPT_COLUMNS),
        )
    for concept in concepts.values():
        for broader in concept.broader:
            if broader not in concepts:
                raise VocabularyError(f"{concept.iri}: broader {broader} is no concept of the vocabularies")
    return concepts


def _iris(nodes: Iterable[Node]) -> list[str]:
    return sorted(str(node) for node in nodes if isinstance(node, URIRef))


def _all_per_language(graph: Graph, iri: URIRef, predicate: URIRef) -> dict[str, list[str]]:
    texts: dict[str, list[str]] = defaultdict(list)
    for value in graph.objects(iri, predicate):
        if isinstance(value, Literal):
            texts[value.language or NO_LANGUAGE].append(str(value))
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
