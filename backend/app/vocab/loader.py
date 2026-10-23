"""The vocabularies of Curriculum-Kern 1.0, read from the ontology's Turtle files.

A scheme is any resource typed as one of SCHEME_CLASSES; a concept is any resource in such a
scheme (``skos:inScheme``) - the levels are ``cur:LevelConcept``, not ``skos:Concept``. The
SKOS core fields become columns; every other statement about a scheme or concept is kept in
``properties``, so a new property in the Turtle files needs no migration. A vocabulary the
tables cannot hold faithfully (a concept in two schemes, two labels in one language, a
broader concept that does not exist) is refused rather than trimmed. The lexicon - the
sectors' terminology profiles and their cues - is read off the same files (app/vocab/lexicon.py),
the profiles' with their subfolders (a country's cues in profile/laender/).
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import SKOS, XSD

from app.vocab.graph import (
    Properties,
    VocabularyError,
    all_per_language,
    iris,
    one_per_language,
    other_properties,
)
from app.vocab.lexicon import LexicalCue, TerminologyProfile, read_lexicon

__all__ = ["MODEL_DIRS", "Concept", "Scheme", "Vocabulary", "VocabularyError", "read_vocabulary"]

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
# The folders that make the model, as pruefe.py names them; examples and research material
# stay out. pruefe.py reads none of their subfolders; this reader reads the profiles' too, where
# a country's cues stand (profile/laender/), and only theirs
MODEL_DIRS = ("ontologie", "vokabulare", "profile")
_WITH_SUBFOLDERS = frozenset({"profile"})
SCHEME_CLASSES = frozenset({SKOS.ConceptScheme, CUR.CompetencyModel, CUR.LevelScheme, CUR.OperatorList})
# Raised with every change to what the reader yields, so the same files load anew afterwards
READER_FORMAT = 2
# A relative IRI resolves under this base (.invalid is reserved) and is refused: against the
# file's own place it would differ from machine to machine
_RELATIVE_BASE = "https://relative.invalid/"
_SCHEME_COLUMNS = frozenset({RDF.type, SKOS.prefLabel})
_CONCEPT_COLUMNS = frozenset(
    {RDF.type, SKOS.inScheme, SKOS.prefLabel, SKOS.altLabel, SKOS.notation, SKOS.definition, SKOS.broader}
)


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
    profiles: dict[str, TerminologyProfile] = field(default_factory=dict)
    cues: dict[str, LexicalCue] = field(default_factory=dict)


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
    lexicon = read_lexicon(graph, {iri: concept.scheme for iri, concept in concepts.items()})
    content_hash = hashlib.sha256(listing.encode()).hexdigest()
    return Vocabulary(content_hash, files, schemes, concepts, lexicon.profiles, lexicon.cues)


def _model_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise VocabularyError(f"{root} is no folder: is ONTOLOGY_DIR the ontology folder?")
    paths: list[Path] = []
    for directory in MODEL_DIRS:
        glob = (root / directory).rglob if directory in _WITH_SUBFOLDERS else (root / directory).glob
        found = sorted(glob("*.ttl"))
        if not found:
            raise VocabularyError(f"{root / directory} holds no Turtle files: is ONTOLOGY_DIR right?")
        paths.extend(found)
    return sorted(paths)


def _refuse_relative_iris(graph: Graph) -> None:
    for triple in graph:
        for term in triple:
            # a literal's datatype is an IRI too, and resolves the same way
            iri = term.datatype if isinstance(term, Literal) else term
            if isinstance(iri, URIRef) and str(iri).startswith(_RELATIVE_BASE):
                place = str(iri).removeprefix(_RELATIVE_BASE)
                raise VocabularyError(f"relative IRI <{place}>: write the full IRI")


def _scheme(graph: Graph, iri: URIRef) -> Scheme:
    return Scheme(
        iri=str(iri),
        types=iris(graph.objects(iri, RDF.type)),
        pref_labels=one_per_language(graph, iri, SKOS.prefLabel),
        properties=other_properties(graph, iri, _SCHEME_COLUMNS),
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
            types=iris(graph.objects(iri, RDF.type)),
            notation=_notation(graph, iri),
            pref_labels=one_per_language(graph, iri, SKOS.prefLabel),
            alt_labels=all_per_language(graph, iri, SKOS.altLabel),
            definitions=one_per_language(graph, iri, SKOS.definition),
            broader=_broader(graph, iri),
            properties=other_properties(graph, iri, _CONCEPT_COLUMNS),
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
    return iris(values)
