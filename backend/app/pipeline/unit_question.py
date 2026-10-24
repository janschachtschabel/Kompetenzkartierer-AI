"""What X3's and X4's questions about a document's units are built of (plan M1 7b, F5-F8): the plan of
the prefix they share - the document's blocks, the sections of its tree, its profile, the choice
lists given -, the profile's statement subkinds keyed for the question with the words the lexicon
excerpt names its targets by, and the codes the answers are read against. All of it as the store
holds it when the stage starts.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.conversion.base import Block
from app.jobs.outcome import PermanentError
from app.llm.client import context_tokens
from app.llm.settings import LLMSettings
from app.pipeline.prefix import Prefix, PrefixPlan, PrefixTooLong, prefix_budget
from app.pipeline.prompts.statements import hint_text, subkind_list
from app.pipeline.unit_prefix import profile_text, sections
from app.pipeline.x1_question import by_label
from app.pipeline.x2_segments import segment_nodes
from app.vocab.graph import Properties
from app.vocab.lookup import concept_texts, notations_by_iri, notations_of, profile_concepts

CV = "https://w3id.org/wlo/curriculum/vocab#"
# the schemes the statement object's enums name (x-cv-scheme), and checkedAbsent's
STATEMENT_SCHEMES = ("StatementKinds", "Addressees", "Obligations", "LayoutMarkers", "DockingPoints")
_PROPERTIES = "SELECT iri, properties FROM vocab_concept WHERE iri = ANY(%s)"


@dataclass(frozen=True)
class StatementLists:
    text: str  # the subkinds as the question lists them (prompts/statements.py)
    keys: dict[str, str]  # their keys, U1 …, with the IRIs they stand for
    refines: Mapping[str, Sequence[str]]  # the profile's subkinds with the core kinds each refines
    names: dict[str, str]  # the lexicon's targets as the question names them: subkinds and node types
    codes: dict[str, dict[str, str]]  # the values of STATEMENT_SCHEMES by notation


async def prefix_plan(
    connection: psycopg.AsyncConnection,
    llm: LLMSettings,
    document_id: UUID,
    blocks: Sequence[Block],
    printed: Sequence[str | None],
    *,
    lists: str,
) -> PrefixPlan:
    """The plan of the prefix of the document of these blocks (all of its conversion's, in order),
    cut by the sections of its tree where it does not fit the model's context whole."""
    nodes = await segment_nodes(connection, document_id, blocks)
    return PrefixPlan(
        blocks,
        printed,
        sections(nodes, len(blocks)),
        profile=await profile_text(connection, document_id),
        lists=lists,
        always=(),  # the table of contents mostly stands in the title pages, which every window keeps
        budget=prefix_budget(context_tokens(llm), llm.llm_max_output_tokens),
    )


def prefix_at(plan: PrefixPlan, position: int) -> Prefix:
    """The prefix of a request about the unit at ``position``; counting is CPU work, run it by
    ``asyncio.to_thread``. PermanentError where no window of the document fits."""
    try:
        return plan.for_position(position)
    except PrefixTooLong as error:
        message = "no window of the document fits the model's context"
        raise PermanentError("prefix_too_long", message) from error


async def statement_lists(connection: psycopg.AsyncConnection, sector: str) -> StatementLists:
    """The lists of the sector's profile (its notation, "school"); a sector without one lists none."""
    values = await profile_concepts(connection, sector)
    subkinds: Mapping[str, Sequence[str]] = values.subkinds if values is not None else {}
    node_types: Mapping[str, Sequence[str]] = values.node_types if values is not None else {}
    texts = await concept_texts(connection, [*subkinds, *node_types])
    kinds = await notations_of(connection, CV + "StatementKinds")
    cursor = await connection.execute(_PROPERTIES, (list(subkinds),))
    properties: dict[str, Properties] = {iri: given for iri, given in await cursor.fetchall()}
    named = {
        value["iri"]
        for given in properties.values()
        for listed in given.values()
        for value in listed
        if "iri" in value
    }
    notations = await notations_by_iri(connection, named)
    hints = {iri: hint_text(given, notations) for iri, given in properties.items()}
    kind_names = {iri: notation for notation, iri in kinds.items()}
    text, keys = subkind_list(by_label(texts, subkinds), kind_names, hints)
    names = {iri: f"{texts[iri].label} ({key})" for key, iri in keys.items()}
    names |= {iri: f"{texts[iri].label} (Gliederungsebene)" for iri in node_types if iri in texts}
    codes = {scheme: await notations_of(connection, CV + scheme) for scheme in STATEMENT_SCHEMES}
    return StatementLists(text, keys, subkinds, names, codes)
