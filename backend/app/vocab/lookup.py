"""Looking up the vocabularies as python -m app.vocab.load left them (plan M1 4.1).

A concept is read whether it is retired or not - old data may name a retired one - but chosen
only while it is active: a notation, a profile's values and a region's ancestors are active
concepts. A profile's values - node types, statement subkinds, document types - are the concepts
of those classes named under its namespace (app/db/migrations/0012_lexicon.sql), each with the
core values it refines (``skos:broader``).
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.domain.lexicon import Cue

CUR = "https://w3id.org/wlo/curriculum/core#"
REGIONS = "https://w3id.org/wlo/curriculum/region/Regions"
_VALUE_CLASSES = {
    "node_types": CUR + "NodeType",
    "subkinds": CUR + "StatementSubkind",
    "document_types": CUR + "DocumentType",
}


@dataclass(frozen=True)
class VocabEntry:
    iri: str
    scheme: str
    types: tuple[str, ...]
    notation: str | None
    pref_labels: dict[str, str]
    broader: tuple[str, ...]
    retired: bool


@dataclass(frozen=True)
class ConceptText:
    """A concept as a prompt lists it: its label and definition in one language (any other where
    that has none), the core values it refines, and - for a node type - the depth its nodes are read
    to (``cur:extractionDepth``, as its notation: full, typed, skip)."""

    iri: str
    notation: str | None
    label: str
    definition: str | None
    broader: tuple[str, ...]
    depth: str | None


@dataclass(frozen=True)
class ProfileConcepts:
    """A profile's active values, each with the core values it refines."""

    node_types: Mapping[str, tuple[str, ...]]
    subkinds: Mapping[str, tuple[str, ...]]
    document_types: Mapping[str, tuple[str, ...]]


_ENTRY = (
    "SELECT iri, scheme_iri, types, notation, pref_labels, broader, retired_in IS NOT NULL AS retired"
    " FROM vocab_concept"
)
_ACTIVE_PROFILE = """
FROM terminology_profile p JOIN vocab_concept s ON s.iri = p.sector_iri
WHERE s.notation = %s AND s.retired_in IS NULL AND p.retired_in IS NULL
"""
_PROFILE = "SELECT p.namespace" + _ACTIVE_PROFILE
_PROFILE_IRI = "SELECT p.iri" + _ACTIVE_PROFILE
_VALUES = """
SELECT iri, types, broader FROM vocab_concept
WHERE starts_with(iri, %s) AND retired_in IS NULL AND types && %s
"""
_CUES = """
SELECT c.iri, c.role_iri, c.kind_iri, c.maps_to, c.surface_form, c.pattern, c.layout_signal, c.also_maps_to,
    c.occurs_in, c.scope_regions, c.scope_document_types, c.scope_institution_types, c.scope_subjects,
    c.scope_issuers, c.plan_generations, c.valid_from, c.valid_until, c.strength, c.verified,
    c.recognition_hints, c.negative_hints, c.positive_examples, c.negative_examples
FROM lexical_cue c
JOIN terminology_profile p ON p.iri = c.profile_iri
JOIN vocab_concept s ON s.iri = p.sector_iri
WHERE s.notation = %s AND s.retired_in IS NULL AND p.retired_in IS NULL AND c.retired_in IS NULL
ORDER BY c.iri
"""
_CONCEPT_TEXTS = """
SELECT c.iri, c.notation, c.pref_labels, c.definitions, c.broader, d.notation AS depth
FROM vocab_concept c
LEFT JOIN vocab_concept d ON d.iri = c.properties -> %(depth)s -> 0 ->> 'iri'
WHERE c.iri = ANY (%(iris)s)
"""
_ANCESTORS = """
WITH RECURSIVE up (iri, broader) AS (
    SELECT iri, broader FROM vocab_concept WHERE scheme_iri = %s AND notation = %s AND retired_in IS NULL
    UNION
    SELECT c.iri, c.broader FROM vocab_concept c JOIN up ON c.iri = ANY (up.broader)
    WHERE c.retired_in IS NULL
)
SELECT iri FROM up
"""


async def concept(connection: psycopg.AsyncConnection, iri: str) -> VocabEntry | None:
    """The concept of this IRI, retired or not."""
    return await _entry(connection, _ENTRY + " WHERE iri = %s", (iri,))


async def by_notation(
    connection: psycopg.AsyncConnection, scheme_iri: str, notation: str
) -> VocabEntry | None:
    """The active concept of the scheme with this notation."""
    query = _ENTRY + " WHERE scheme_iri = %s AND notation = %s AND retired_in IS NULL"
    return await _entry(connection, query, (scheme_iri, notation))


async def terminology_profile(connection: psycopg.AsyncConnection, sector_notation: str) -> str | None:
    """The IRI of the sector's active profile, which a run reads with (its ``profile_version``)."""
    cursor = await connection.execute(_PROFILE_IRI, (sector_notation,))
    found = await cursor.fetchone()
    return None if found is None else str(found[0])


async def profile_concepts(
    connection: psycopg.AsyncConnection, sector_notation: str
) -> ProfileConcepts | None:
    """The active values of the sector's profile (``school``, ``vocational``), or None where the
    sector has no active profile."""
    cursor = await connection.execute(_PROFILE, (sector_notation,))
    profile = await cursor.fetchone()
    if profile is None:
        return None
    cursor = await connection.execute(_VALUES, (profile[0], list(_VALUE_CLASSES.values())))
    grouped: dict[str, dict[str, tuple[str, ...]]] = {name: {} for name in _VALUE_CLASSES}
    for iri, types, broader in await cursor.fetchall():
        for name, value_class in _VALUE_CLASSES.items():
            if value_class in types:
                grouped[name][iri] = tuple(broader)
    return ProfileConcepts(**grouped)


async def cues_for(connection: psycopg.AsyncConnection, sector_notation: str) -> list[Cue]:
    """The active cues of the sector's active profile (``school``), for its documents' active
    profile (app/domain/lexicon.py); none where the sector has no profile."""
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(_CUES, (sector_notation,))
        rows = await cursor.fetchall()
    return [
        Cue(
            iri=row["iri"],
            role=row["role_iri"],
            kind=row["kind_iri"],
            maps_to=tuple(row["maps_to"]),
            surface_form=row["surface_form"],
            pattern=row["pattern"],
            layout_signal=row["layout_signal"],
            also_maps_to=tuple(row["also_maps_to"]),
            occurs_in=frozenset(row["occurs_in"]),
            scope_regions=frozenset(row["scope_regions"]),
            scope_document_types=frozenset(row["scope_document_types"]),
            scope_institution_types=frozenset(row["scope_institution_types"]),
            scope_subjects=frozenset(row["scope_subjects"]),
            scope_issuers=frozenset(row["scope_issuers"]),
            plan_generations=frozenset(row["plan_generations"]),
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            strength=None if row["strength"] is None else float(row["strength"]),
            verified=row["verified"],
            recognition_hints=_texts(row["recognition_hints"]),
            negative_hints=_texts(row["negative_hints"]),
            positive_examples=tuple(row["positive_examples"]),
            negative_examples=tuple(row["negative_examples"]),
        )
        for row in rows
    ]


def _texts(by_language: dict[str, list[str]]) -> tuple[str, ...]:
    return tuple(text for language in sorted(by_language) for text in by_language[language])


async def concept_texts(
    connection: psycopg.AsyncConnection, iris: Collection[str], language: str = "de"
) -> dict[str, ConceptText]:
    """The concepts of these IRIs as a prompt lists them, retired or not; an unknown IRI is left out."""
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(_CONCEPT_TEXTS, {"depth": CUR + "extractionDepth", "iris": list(iris)})
        rows = await cursor.fetchall()
    return {
        row["iri"]: ConceptText(
            iri=row["iri"],
            notation=row["notation"],
            label=_in(row["pref_labels"], language) or row["notation"] or row["iri"],
            definition=_in(row["definitions"], language),
            broader=tuple(row["broader"]),
            depth=row["depth"],
        )
        for row in rows
    }


def _in(by_language: dict[str, str], language: str) -> str | None:
    """The text in ``language``, else in the first other one there is."""
    if language in by_language:
        return by_language[language]
    return next((by_language[other] for other in sorted(by_language)), None)


async def current_release(connection: psycopg.AsyncConnection) -> int | None:
    """The release the vocabularies were last loaded as, which a run reads with; None before any load."""
    cursor = await connection.execute("SELECT max(id) FROM vocab_release")
    row = await cursor.fetchone()
    return None if row is None else row[0]


async def notations_of(connection: psycopg.AsyncConnection, scheme_iri: str) -> dict[str, str]:
    """The scheme's active concepts by their notations, as an output schema's enums name them."""
    cursor = await connection.execute(
        "SELECT notation, iri FROM vocab_concept"
        " WHERE scheme_iri = %s AND notation IS NOT NULL AND retired_in IS NULL",
        (scheme_iri,),
    )
    return {str(notation): str(iri) for notation, iri in await cursor.fetchall()}


async def notations_by_iri(connection: psycopg.AsyncConnection, iris: Collection[str]) -> dict[str, str]:
    """The notations of these concepts by their IRIs, retired ones too: what a document took when
    it was made stays named as it was."""
    cursor = await connection.execute(
        "SELECT iri, notation FROM vocab_concept WHERE iri = ANY(%s) AND notation IS NOT NULL", (list(iris),)
    )
    return {str(iri): str(notation) for iri, notation in await cursor.fetchall()}


async def region_with_ancestors(connection: psycopg.AsyncConnection, notation: str) -> frozenset[str]:
    """The active region of this notation ("DE-NW") and those it lies in ("DE"); none if unknown.
    One set: for ``active_cues`` the caller parts the region itself from those it lies in
    (``wider_regions``), or Germany's cues would rank as the country's own."""
    cursor = await connection.execute(_ANCESTORS, (REGIONS, notation))
    return frozenset(str(row[0]) for row in await cursor.fetchall())


async def _entry(
    connection: psycopg.AsyncConnection, query: str, params: tuple[Any, ...]
) -> VocabEntry | None:
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        row = await cursor.fetchone()
    if row is None:
        return None
    return VocabEntry(
        iri=row["iri"],
        scheme=row["scheme_iri"],
        types=tuple(row["types"]),
        notation=row["notation"],
        pref_labels=row["pref_labels"],
        broader=tuple(row["broader"]),
        retired=row["retired"],
    )
