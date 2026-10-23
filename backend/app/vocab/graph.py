"""Reading the statements of the ontology's graph as the vocabulary tables hold them.

Texts are kept by language - BCP 47 tags ignore case, so "de" and "DE" are one - and a text
without one under "und" (undetermined); IRIs sorted; whatever has no column of its own as
``properties``: {predicate: [{"iri"} or {"value", "lang" or "datatype"}]}. What a table cannot
hold as it is - text where an IRI belongs, a blank node - is refused rather than trimmed.
"""

import json
from collections import defaultdict
from collections.abc import Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.term import Node

NO_LANGUAGE = "und"  # BCP 47 for "undetermined"

Properties = dict[str, list[dict[str, str]]]


class VocabularyError(Exception):
    """The Turtle files hold something the vocabulary tables cannot represent as it is."""


def iris(nodes: Iterable[Node]) -> list[str]:
    return sorted(str(node) for node in nodes if isinstance(node, URIRef))


def all_per_language(graph: Graph, iri: URIRef, predicate: URIRef) -> dict[str, list[str]]:
    texts: dict[str, list[str]] = defaultdict(list)
    for value in graph.objects(iri, predicate):
        if not isinstance(value, Literal):
            name = predicate.split("#")[-1]
            raise VocabularyError(f"{iri} {name}: text belongs here, not {value!r}")
        texts[(value.language or NO_LANGUAGE).lower()].append(str(value))
    return {language: sorted(values) for language, values in sorted(texts.items())}


def one_per_language(graph: Graph, iri: URIRef, predicate: URIRef) -> dict[str, str]:
    texts = all_per_language(graph, iri, predicate)
    for language, values in texts.items():
        if len(values) > 1:
            name = predicate.split("#")[-1]
            raise VocabularyError(f"{iri} has more than one {name} in language {language}: {values}")
    return {language: values[0] for language, values in texts.items()}


def other_properties(graph: Graph, iri: URIRef, columns: frozenset[URIRef]) -> Properties:
    """Every statement about ``iri`` whose predicate has no column of its own."""
    found: dict[str, list[dict[str, str]]] = defaultdict(list)
    for predicate, value in graph.predicate_objects(iri):
        if predicate not in columns:
            found[str(predicate)].append(term_value(iri, predicate, value))
    return {
        predicate: sorted(values, key=lambda value: json.dumps(value, sort_keys=True))
        for predicate, values in sorted(found.items())
    }


def term_value(iri: URIRef, predicate: Node, value: Node) -> dict[str, str]:
    if isinstance(value, URIRef):
        return {"iri": str(value)}
    if isinstance(value, Literal):
        literal = {"value": str(value)}
        if value.language:
            literal["lang"] = value.language.lower()  # as in the label columns: tags ignore case
        elif value.datatype is not None:
            literal["datatype"] = str(value.datatype)
        return literal
    raise VocabularyError(f"{iri} {predicate}: a blank node has no place in the vocabulary tables")
