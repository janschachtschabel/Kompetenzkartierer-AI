"""X1's question for a document's profile as the stage asks it (plan M1 6.2): the excerpt of its
blocks, its sector's document types, node types and statement subkinds in German, by label, and
the words of its active cues for terms (plan M1 6, Festlegung 15: X1 reads cues for terms alone) -
with what the answer is read against (app/pipeline/x1_profile.py): the document as it was made,
its blocks, the call's keys and the vocabularies' values the schema's enums name."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import psycopg

from app.conversion.base import Block
from app.db.documents import Document
from app.domain.lexicon import ActiveCue
from app.pipeline.prompts.x1_profile import profile_prompt
from app.pipeline.toc import Contents
from app.pipeline.x1_excerpt import profile_excerpt
from app.pipeline.x1_profile import ProfileContext
from app.vocab.lookup import ConceptText, concept, concept_texts, notations_of, profile_concepts

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


async def profile_question(
    connection: psycopg.AsyncConnection,
    document: Document,
    blocks: Sequence[Block],
    printed_pages: Sequence[str | None],
    contents: Contents,
    cues: Sequence[ActiveCue],
) -> ProfileQuestion:
    """The question for the document of these blocks (all of its conversion's, in order) and the
    document's active cues; a sector without a profile lists nothing."""
    sector = await concept(connection, document.sector_iri)
    notation = sector.notation if sector is not None and sector.notation is not None else ""
    values = await profile_concepts(connection, notation)
    groups: list[Collection[str]] = (
        [values.document_types, values.node_types, values.subkinds] if values is not None else [(), (), ()]
    )
    texts = await concept_texts(connection, [iri for group in groups for iri in group])
    document_types, node_types, subkinds = (_by_label(texts, group) for group in groups)
    excerpt = profile_excerpt(blocks, printed_pages, contents)
    terms = [found for found in cues if found.cue.kind == _TERM]
    prompt, lists = profile_prompt(excerpt, document_types, node_types, subkinds, terms)
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


def _by_label(texts: dict[str, ConceptText], iris: Collection[str]) -> list[ConceptText]:
    return sorted(
        (texts[iri] for iri in iris if iri in texts), key=lambda text: (text.label.casefold(), text.iri)
    )
