"""X1's questions as the stage asks them (plan M1 6.2, 6.4), each with what its answers are read
against. The profile's: the excerpt of the document's blocks, its sector's document types, node
types and statement subkinds in German by label, and the words of its active cues for terms (plan
M1 6, Festlegung 15: X1 reads cues for terms alone). The outline's: the headings the skeleton left
untyped, in batches, with the sector's node types and their core functions and X1's specifications."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import psycopg

from app.conversion.base import Block
from app.db.documents import Document
from app.domain.lexicon import ActiveCue
from app.pipeline.prompts.x1_outline import outline_prompt
from app.pipeline.prompts.x1_profile import profile_prompt
from app.pipeline.skeleton import Skeleton
from app.pipeline.toc import Contents
from app.pipeline.x1_excerpt import profile_excerpt
from app.pipeline.x1_outline import OutlineContext, batches, outline_items
from app.pipeline.x1_profile import ProfileContext
from app.vocab.lookup import (
    ConceptText,
    ProfileConcepts,
    concept,
    concept_texts,
    notations_of,
    profile_concepts,
)

CV = "https://w3id.org/wlo/curriculum/vocab#"
# the schemes the x1-dokumentprofil schema's enums name (x-cv-scheme)
SCHEMES = (
    "LegalForms", "DocumentBindings", "Lifecycles", "EducationSectors", "Formalities", "TimeKinds",
    "VariantKinds", "NodeFunctions",
)  # fmt: skip
_TERM = CV + "ck_term"


@dataclass(frozen=True)
class ProfileQuestion:
    prompt: str
    context: ProfileContext


@dataclass(frozen=True)
class OutlineQuestions:
    prompts: list[str]  # one a batch; none where every heading is typed
    asked: list[str]  # the keys of the headings asked
    context: OutlineContext


async def profile_question(
    connection: psycopg.AsyncConnection,
    document: Document,
    blocks: Sequence[Block],
    printed_pages: Sequence[str | None],
    contents: Contents,
    cues: Sequence[ActiveCue],
    *,
    today: date | None = None,
) -> ProfileQuestion:
    """The question for the document of these blocks (all of its conversion's, in order) and the
    document's active cues; a sector without a profile lists nothing."""
    notation, values = await _profile(connection, document)
    groups: list[Collection[str]] = (
        [values.document_types, values.node_types, values.subkinds] if values is not None else [(), (), ()]
    )
    texts = await concept_texts(connection, [iri for group in groups for iri in group])
    document_types, node_types, subkinds = (_by_label(texts, group) for group in groups)
    excerpt = profile_excerpt(blocks, printed_pages, contents)
    terms = [found for found in cues if found.cue.kind == _TERM]
    prompt, lists = profile_prompt(
        excerpt, document_types, node_types, subkinds, terms, today=today or date.today()
    )
    codes = {scheme: await notations_of(connection, CV + scheme) for scheme in SCHEMES}
    context = ProfileContext(
        document_id=document.id,
        sector=notation,
        regions=document.regions,
        block_ids=frozenset(block.id for block in blocks),
        lists=lists,
        codes=codes,
    )
    return ProfileQuestion(prompt, context)


async def outline_questions(
    connection: psycopg.AsyncConnection,
    document: Document,
    skeleton: Skeleton,
    blocks: Sequence[Block],
    specifications: Sequence[tuple[str, str]],
) -> OutlineQuestions:
    """The questions for the skeleton's untyped headings; ``specifications`` are X1's keys with their
    titles."""
    _, values = await _profile(connection, document)
    node_types: Mapping[str, tuple[str, ...]] = values.node_types if values is not None else {}
    texts = await concept_texts(connection, list(node_types))
    functions = await notations_of(connection, CV + "NodeFunctions")
    cores = set(functions.values())
    functions_of = {
        iri: core
        for iri, broader in node_types.items()
        if (core := next((b for b in broader if b in cores), None))
    }
    listed = _by_label(texts, node_types)
    names = {iri: name for name, iri in functions.items()}
    items = outline_items(skeleton, blocks)
    prompts: list[str] = []
    types: dict[str, str] = {}
    for batch in batches(items):
        prompt, types = outline_prompt(batch, listed, names, specifications)
        prompts.append(prompt)
    context = OutlineContext(
        document_id=document.id,
        types=types,
        functions_of=functions_of,
        codes={"NodeFunctions": functions, "ScopeShares": await notations_of(connection, CV + "ScopeShares")},
        specifications=frozenset(key for key, _ in specifications),
    )
    return OutlineQuestions(prompts, [item.key for item in items], context)


async def _profile(
    connection: psycopg.AsyncConnection, document: Document
) -> tuple[str, ProfileConcepts | None]:
    """The notation of the document's sector and its profile's values (none without a profile)."""
    sector = await concept(connection, document.sector_iri)
    notation = sector.notation if sector is not None and sector.notation is not None else ""
    return notation, await profile_concepts(connection, notation)


def _by_label(texts: dict[str, ConceptText], iris: Collection[str]) -> list[ConceptText]:
    return sorted(
        (texts[iri] for iri in iris if iri in texts), key=lambda text: (text.label.casefold(), text.iri)
    )
