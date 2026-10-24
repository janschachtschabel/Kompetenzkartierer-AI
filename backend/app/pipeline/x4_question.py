"""X4's questions of one run (plan M1 7b, F3, F5, F6): a unit's each, behind the prefix they share -
the document, its profile, the choice lists of X3 with the profile's statement subkinds - and what
the answers are read against. Built once a run from the store as it stands after X3; a unit's
prompt is its prefix (one for the whole document where it fits, else its window), a cache
breakpoint, and its task (prompts/x4.py).

The prefix is counted with the tokenizer, CPU work: it runs by ``asyncio.to_thread``, one unit at a
time, so the units asked side by side count the whole document once (the plan keeps each count).
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID

import psycopg
from pydantic_ai.messages import UserContent
from pydantic_ai.models import Model

from app.conversion.base import Block
from app.db.documents import Document
from app.db.findings import Finding
from app.db.frame_parts import frame_parts_of
from app.domain.lexicon import ActiveCue, active_cues
from app.llm.calls import cached_up_to
from app.llm.settings import LLMSettings
from app.pipeline.ground import Ground
from app.pipeline.lexicon_excerpt import lexicon_excerpt
from app.pipeline.prefix import PrefixPlan
from app.pipeline.prompts import x4
from app.pipeline.statement_read import StatementContext
from app.pipeline.toc import OUTSIDE
from app.pipeline.unit_prefix import choice_lists
from app.pipeline.unit_question import StatementLists, prefix_at, prefix_plan, statement_lists
from app.pipeline.x2_segments import WorkPackage
from app.vocab.lookup import concept_texts, notations_by_iri

_NODES = "SELECT id, node_type_iri, function_iri FROM node WHERE document_id = %s"


@dataclass(frozen=True)
class UnitQuestion:
    prompt: str | list[UserContent]
    findings: list[Finding]  # of building it: patterns of the lexicon that took too long


@dataclass
class UnitQuestions:
    document_id: UUID
    blocks: Sequence[Block]
    plan: PrefixPlan
    lists: StatementLists
    cues: list[ActiveCue]
    nodes: Mapping[UUID, str]  # each node's line of the task: its type, else its core function
    model: Model
    statements: StatementContext  # what every unit's answer is read against
    _counting: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def check(self, units: Sequence[WorkPackage]) -> None:
        """Count the prefix of each of ``units``; PermanentError (prefix_too_long) for the first that
        no window fits. Each window is counted once: the questions reuse them."""
        for unit in units:
            async with self._counting:
                await asyncio.to_thread(prefix_at, self.plan, unit.first)

    async def question(self, unit: WorkPackage) -> UnitQuestion:
        """The question for ``unit``; PermanentError (prefix_too_long) where no window fits."""
        async with self._counting:
            prefix = await asyncio.to_thread(prefix_at, self.plan, unit.first)
        texts = [
            self.blocks[at].text
            for at in range(unit.first, unit.last + 1)
            if self.blocks[at].kind not in OUTSIDE
        ]
        excerpt = await asyncio.to_thread(lexicon_excerpt, self.cues, texts, self.lists.names)
        node = "" if unit.node_id is None else self.nodes.get(unit.node_id, "")
        task = x4.unit_task(unit, node, excerpt.text)
        findings = [
            Finding(
                "x4.pattern_timeout", "warning", self.document_id, "a cue's pattern took too long", None,
                {"cue": cue, "unit": unit.key},
            )
            for cue in sorted(excerpt.timeouts)
        ]  # fmt: skip
        return UnitQuestion(cached_up_to(prefix.text, task, self.model), findings)


async def unit_questions(
    connection: psycopg.AsyncConnection,
    llm: LLMSettings,
    document: Document,
    blocks: Sequence[Block],
    printed: Sequence[str | None],
    ground: Ground,
    model: Model,
) -> UnitQuestions:
    """The questions of a run of X4 on the document - as the store holds it after X3 - of these blocks
    (all of its conversion's, in order)."""
    lists = await statement_lists(connection, ground.sector)
    choices = choice_lists(await frame_parts_of(connection, document.id))
    plan = await prefix_plan(
        connection, llm, document.id, blocks, printed, lists=x4.prefix_lists(choices, lists.text)
    )
    cues = active_cues(
        ground.cues, ground.regions, document.document_type_iri, None, wider_regions=ground.wider
    )
    statements = StatementContext("x4", document.id, blocks, printed, lists.keys, lists.refines, lists.codes)
    return UnitQuestions(
        document.id, blocks, plan, lists, cues, await _node_lines(connection, document.id), model, statements
    )


async def _node_lines(connection: psycopg.AsyncConnection, document_id: UUID) -> dict[UUID, str]:
    """Each node's line of a task about one of its units: its type by label and definition, else its
    core function by notation."""
    cursor = await connection.execute(_NODES, (document_id,))
    nodes = await cursor.fetchall()
    types = await concept_texts(connection, {node_type for _, node_type, _ in nodes if node_type})
    functions = await notations_by_iri(connection, {function for _, _, function in nodes})
    lines: dict[UUID, str] = {}
    for node_id, node_type, function in nodes:
        if node_type in types:
            text = types[node_type]
            lines[node_id] = f"Knotentyp: {text.label}" + (f" — {text.definition}" if text.definition else "")
        elif function in functions:
            lines[node_id] = f"Kernfunktion: {functions[function]}"
    return lines
