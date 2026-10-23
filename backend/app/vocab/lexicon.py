"""The lexicon of Curriculum-Kern 1.0: each sector's terminology profile and its cues (konzept
§12.1), read off the model's graph with the vocabularies (app/vocab/loader.py).

A profile (``cur:TerminologyProfile``) names one education sector (``cur:profileScope``) and
lists one cue at least; its namespace - its IRI up to the last '#' or '/' - is where its values
are named. One profile for each sector: a country's file (profile/laender/) lists its cues on
its sector's profile with ``cur:hasCue`` and scopes them to its region, rather than making a
profile of the sector and country of its own (konzept §12.4) - the active profile of a document
is then one profile's cues. A cue (``cur:LexicalCue``) belongs to the one profile that lists it
(``cur:hasCue``). It names a form - a word, a pattern or a layout signal - its role and kind
(one each, from ``cv:CueRoles`` and ``cv:CueKinds``) and a target at least; every IRI it names
is typed in the model, since a target may be a class or a property as well as a concept.
Its layout signal, places and regions are concepts of ``cv:LayoutMarkers``, ``cv:Occurrences``
and the regions, its document types ``cur:DocumentType``s; a date is an xsd:date, gYearMonth or
gYear as written, without a time zone (cur-shapes.ttl). A pattern compiles with Python's re and
with ``regex`` as re reads it. What the tables cannot hold as it is - text where an IRI belongs,
two values of one form, a date in prose - is refused; whatever else a file says of a cue goes to its
properties.
"""

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import regex
from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD
from rdflib.term import Node

from app.vocab.graph import (
    Properties,
    VocabularyError,
    all_per_language,
    iris,
    one_per_language,
    other_properties,
)

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
SECTORS = str(CV.EducationSectors)
ROLES = str(CV.CueRoles)
KINDS = str(CV.CueKinds)
LAYOUT_MARKERS = str(CV.LayoutMarkers)
REGIONS = "https://w3id.org/wlo/curriculum/region/Regions"
# What a cue's places and regions are concepts of
_SCHEMES = {"occursIn": str(CV.Occurrences), "scopeRegion": REGIONS}
# A date's lexical form by its datatype (cur-shapes.ttl DateLike); the tables keep it as written
_DATES: dict[URIRef | None, re.Pattern[str]] = {
    XSD.date: re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    XSD.gYearMonth: re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])"),
    XSD.gYear: re.compile(r"[0-9]{4}"),
}
_TARGETS = ("mapsTo", "alsoMapsTo", "occursIn", "scopeRegion", "scopeDocumentType", "scopeInstitutionType")
_TEXTS = ("scopeIssuer", "planGeneration", "positiveExample", "negativeExample")
_SINGLE = ("surfaceForm", "pattern", "layoutSignal", "cueRole", "cueKind", "validFrom", "validUntil")
# scopeSector has no column: a cue holds in its profile's sector, and may say so
_COLUMNS = frozenset(
    {RDF.type, CUR.strength, CUR.verified, CUR.recognitionHint, CUR.negativeHint, CUR.scopeSubject}
    | {CUR.scopeSector}
    | {CUR[name] for name in (*_TARGETS, *_TEXTS, *_SINGLE)}
)


@dataclass(frozen=True)
class TerminologyProfile:
    iri: str
    namespace: str
    sector: str
    labels: dict[str, str]


@dataclass(frozen=True)
class LexicalCue:
    iri: str
    profile: str
    surface_form: str | None
    pattern: str | None
    layout_signal: str | None
    role: str
    kind: str
    maps_to: list[str]
    also_maps_to: list[str]
    occurs_in: list[str]
    scope_regions: list[str]
    scope_document_types: list[str]
    scope_institution_types: list[str]
    scope_subjects: list[str]
    scope_issuers: list[str]
    plan_generations: list[str]
    valid_from: str | None
    valid_until: str | None
    strength: Decimal | None
    verified: bool
    recognition_hints: dict[str, list[str]]
    negative_hints: dict[str, list[str]]
    positive_examples: list[str]
    negative_examples: list[str]
    properties: Properties


@dataclass(frozen=True)
class Lexicon:
    profiles: dict[str, TerminologyProfile]
    cues: dict[str, LexicalCue]


def read_lexicon(graph: Graph, scheme_of: Mapping[str, str]) -> Lexicon:
    """The profiles and cues of ``graph``; ``scheme_of``: each concept of the vocabularies, with
    its scheme."""
    profiles = {
        str(iri): _profile(graph, iri, scheme_of)
        for iri in sorted(graph.subjects(RDF.type, CUR.TerminologyProfile), key=str)
        if isinstance(iri, URIRef)
    }
    by_sector: dict[str, list[str]] = defaultdict(list)
    for read in profiles.values():
        by_sector[read.sector].append(read.iri)
    for sector, named in sorted(by_sector.items()):
        if len(named) > 1:
            raise VocabularyError(f"{sector} has more than one profile: {named}, a sector has one")
    owners: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        its_cues = _all_iris(graph, URIRef(profile), CUR.hasCue)
        if not its_cues:
            raise VocabularyError(f"{profile} lists no cue: a profile lists one at least (cur:hasCue)")
        for cue in its_cues:
            owners[cue].append(profile)
    typed = {str(iri) for iri in graph.subjects(RDF.type, CUR.LexicalCue) if isinstance(iri, URIRef)}
    for listed in sorted(set(owners) - typed):
        raise VocabularyError(
            f"{owners[listed][0]} lists {listed} as a cue, but it is no cue (cur:LexicalCue)"
        )
    cues = {}
    for iri in sorted(typed):
        if len(owners[iri]) != 1:
            if not owners[iri]:
                raise VocabularyError(f"{iri} is in no profile: a profile lists it with cur:hasCue")
            raise VocabularyError(f"{iri} is in more than one profile: {sorted(owners[iri])}")
        cues[iri] = _cue(graph, URIRef(iri), profiles[owners[iri][0]], scheme_of)
    return Lexicon(profiles, cues)


def _profile(graph: Graph, iri: URIRef, scheme_of: Mapping[str, str]) -> TerminologyProfile:
    scopes = _all_iris(graph, iri, CUR.profileScope)
    if len(scopes) != 1:
        raise VocabularyError(f"{iri} names {len(scopes)} sectors: a profile names one (cur:profileScope)")
    if scheme_of.get(scopes[0]) != SECTORS:
        raise VocabularyError(f"{iri}: {scopes[0]} is no education sector (cv:EducationSectors)")
    name = str(iri)
    end = max(name.rfind("#"), name.rfind("/")) + 1
    if end == len(name):
        raise VocabularyError(f"{iri}: a profile's IRI names it within its namespace")
    return TerminologyProfile(name, name[:end], scopes[0], one_per_language(graph, iri, RDFS.label))


def _cue(graph: Graph, iri: URIRef, profile: TerminologyProfile, scheme_of: Mapping[str, str]) -> LexicalCue:
    for sector in _all_iris(graph, iri, CUR.scopeSector):
        if sector != profile.sector:
            raise VocabularyError(
                f"{iri} scopeSector: {sector} is not the sector of its profile {profile.iri}, where it holds"
            )
    surface_form = _one_text(graph, iri, "surfaceForm")
    pattern = _one_text(graph, iri, "pattern")
    layout_signal = _one_iri(graph, iri, "layoutSignal")
    if surface_form is None and pattern is None and layout_signal is None:
        raise VocabularyError(f"{iri} has no form: a surfaceForm, a pattern or a layoutSignal")
    if pattern is not None:
        _check_pattern(iri, pattern)
    role = _one_of(graph, iri, "cueRole", ROLES, scheme_of)
    kind = _one_of(graph, iri, "cueKind", KINDS, scheme_of)
    named = {name: _all_iris(graph, iri, CUR[name]) for name in (*_TARGETS, "scopeSubject")}
    if not named["mapsTo"]:
        raise VocabularyError(f"{iri} names no target (cur:mapsTo)")
    for target in [*(target for targets in named.values() for target in targets), layout_signal]:
        if target is not None and (URIRef(target), RDF.type, None) not in graph:
            raise VocabularyError(f"{iri} names {target}, which the model does not type: no such target")
    _check_kinds_of_values(graph, iri, named, layout_signal, scheme_of)
    texts = {name: _all_texts(graph, iri, CUR[name]) for name in _TEXTS}
    return LexicalCue(
        iri=str(iri),
        profile=profile.iri,
        surface_form=surface_form,
        pattern=pattern,
        layout_signal=layout_signal,
        role=role,
        kind=kind,
        maps_to=named["mapsTo"],
        also_maps_to=named["alsoMapsTo"],
        occurs_in=named["occursIn"],
        scope_regions=named["scopeRegion"],
        scope_document_types=named["scopeDocumentType"],
        scope_institution_types=named["scopeInstitutionType"],
        scope_subjects=named["scopeSubject"],
        scope_issuers=texts["scopeIssuer"],
        plan_generations=texts["planGeneration"],
        valid_from=_date(graph, iri, "validFrom"),
        valid_until=_date(graph, iri, "validUntil"),
        strength=_strength(graph, iri),
        verified=_verified(graph, iri),
        recognition_hints=all_per_language(graph, iri, CUR.recognitionHint),
        negative_hints=all_per_language(graph, iri, CUR.negativeHint),
        positive_examples=texts["positiveExample"],
        negative_examples=texts["negativeExample"],
        properties=other_properties(graph, iri, _COLUMNS),
    )


def _check_kinds_of_values(
    graph: Graph,
    iri: URIRef,
    named: Mapping[str, list[str]],
    layout_signal: str | None,
    scheme_of: Mapping[str, str],
) -> None:
    """A cue's layout signal, places, regions and document types are of the kind cur-shapes.ttl
    and the core name: typed in the model, a place or a region of another scheme would go
    unnoticed until a document met it."""
    if layout_signal is not None and scheme_of.get(layout_signal) != LAYOUT_MARKERS:
        raise VocabularyError(f"{iri} layoutSignal: {layout_signal} is no concept of {LAYOUT_MARKERS}")
    for name, scheme in _SCHEMES.items():
        for value in named[name]:
            if scheme_of.get(value) != scheme:
                raise VocabularyError(f"{iri} {name}: {value} is no concept of {scheme}")
    for value in named["scopeDocumentType"]:
        if (URIRef(value), RDF.type, CUR.DocumentType) not in graph:
            raise VocabularyError(f"{iri} scopeDocumentType: {value} is no cur:DocumentType")


def _check_pattern(iri: URIRef, pattern: str) -> None:
    """A pattern is in the syntax of Python's re (konzept §12.1), searched with ``regex`` for its
    time limit: regex reads more (``\\p{L}``, ``(?r)``), which pruefe.py and any other reader of
    the files would refuse, so it compiles with both."""
    try:
        re.compile(pattern)
        regex.compile(pattern, regex.V0)
    except (re.error, regex.error) as error:
        raise VocabularyError(f"{iri}: the pattern {pattern!r} does not compile: {error}") from error


def _single(graph: Graph, iri: URIRef, name: str) -> Node | None:
    values = list(graph.objects(iri, CUR[name]))
    if len(values) > 1:
        raise VocabularyError(f"{iri} has more than one {name}: {sorted(str(value) for value in values)}")
    return values[0] if values else None


def _one_text(graph: Graph, iri: URIRef, name: str) -> str | None:
    value = _single(graph, iri, name)
    if value is not None and not isinstance(value, Literal):
        raise VocabularyError(f"{iri} {name}: text belongs here, not {value!r}")
    return None if value is None else str(value)


def _one_iri(graph: Graph, iri: URIRef, name: str) -> str | None:
    value = _single(graph, iri, name)
    if value is not None and not isinstance(value, URIRef):
        raise VocabularyError(f"{iri} {name}: an IRI belongs here, not {value!r}")
    return None if value is None else str(value)


def _one_of(graph: Graph, iri: URIRef, name: str, scheme: str, scheme_of: Mapping[str, str]) -> str:
    value = _one_iri(graph, iri, name)
    if value is None or scheme_of.get(value) != scheme:
        what = name.removeprefix("cue").lower()
        raise VocabularyError(f"{iri}: a cue's {what} ({name}) is one concept of {scheme}, not {value}")
    return value


def _all_iris(graph: Graph, iri: URIRef, predicate: URIRef) -> list[str]:
    values = list(graph.objects(iri, predicate))
    if any(not isinstance(value, URIRef) for value in values):
        name = predicate.split("#")[-1]
        raise VocabularyError(f"{iri} {name}: an IRI belongs here, not {[str(value) for value in values]}")
    return iris(values)


def _all_texts(graph: Graph, iri: URIRef, predicate: URIRef) -> list[str]:
    values = list(graph.objects(iri, predicate))
    if any(not isinstance(value, Literal) for value in values):
        name = predicate.split("#")[-1]
        raise VocabularyError(f"{iri} {name}: text belongs here, not {[str(value) for value in values]}")
    return sorted(str(value) for value in values)


def _date(graph: Graph, iri: URIRef, name: str) -> str | None:
    value = _single(graph, iri, name)
    if value is None:
        return None
    # rdflib checks an xsd:date (ill_typed), not a gYearMonth or gYear: their form does
    if isinstance(value, Literal) and not value.ill_typed:
        form = _DATES.get(value.datatype)
        if form is not None and form.fullmatch(value) is not None:
            return str(value)
    raise VocabularyError(
        f"{iri} {name}: a date belongs here - an xsd:date, gYearMonth or gYear (YYYY-MM-DD, YYYY-MM"
        f" or YYYY) without a time zone - not {value!r}"
    )


def _strength(graph: Graph, iri: URIRef) -> Decimal | None:
    value = _single(graph, iri, "strength")
    if value is None:
        return None
    number = value.toPython() if isinstance(value, Literal) else None
    if isinstance(number, bool) or not isinstance(number, (Decimal, int, float)) or not 0 <= number <= 1:
        raise VocabularyError(f"{iri} strength: a number from 0 to 1 belongs here, not {value!r}")
    return Decimal(str(number))


def _verified(graph: Graph, iri: URIRef) -> bool:
    value = _single(graph, iri, "verified")
    if value is None:
        return False  # unsaid, it was not checked against an original
    # an ill-typed boolean ("ja") rdflib reads as false, with no more than a warning
    if not isinstance(value, Literal) or value.datatype != XSD.boolean or value.ill_typed:
        raise VocabularyError(f"{iri} verified: true or false belongs here, not {value!r}")
    return bool(value.toPython())
