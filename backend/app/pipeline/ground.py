"""What the stages of an extraction read a document with (plan M1 6.2, 7): its sector's cues and
node types, its own regions and the wider ones they lie in, its terminology profile and the
vocabularies' release."""

from dataclasses import dataclass

import psycopg

from app.db.documents import Document
from app.domain.lexicon import Cue
from app.vocab.lookup import (
    REGIONS,
    by_notation,
    concept,
    cues_for,
    current_release,
    profile_concepts,
    region_with_ancestors,
    terminology_profile,
)


@dataclass(frozen=True)
class Ground:
    """What a stage reads the document with: its sector's cues and node types, its regions."""

    sector: str
    cues: list[Cue]
    regions: frozenset[str]
    wider: frozenset[str]
    node_types: frozenset[str]
    profile: str | None
    release: int | None


async def ground_of(connection: psycopg.AsyncConnection, document: Document) -> Ground:
    """The ground of the document as the store holds it now."""
    sector = await concept(connection, document.sector_iri)
    notation = sector.notation if sector is not None and sector.notation is not None else ""
    own: set[str] = set()
    every: set[str] = set()
    for region in document.regions:
        if (entry := await by_notation(connection, REGIONS, region)) is not None:
            own.add(entry.iri)
        every |= await region_with_ancestors(connection, region)
    values = await profile_concepts(connection, notation)
    return Ground(
        sector=notation,
        cues=await cues_for(connection, notation),
        regions=frozenset(own),
        wider=frozenset(every - own),
        node_types=frozenset(values.node_types) if values is not None else frozenset(),
        profile=await terminology_profile(connection, notation),
        release=await current_release(connection),
    )
