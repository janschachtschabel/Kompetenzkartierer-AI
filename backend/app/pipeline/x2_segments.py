"""X2's work packages (plan M1 6.5): the document cut into what the later stages read, from its tree
and its blocks, without the model.

The blocks before the first heading are the title pages (E0, typed: X3 reads them for the frame).
Each node's own text runs from its heading's block to the next heading - its first child's, its
sibling's or one further up - so the text between a section's heading and its first subsection is
read once, with the section. A node's depth is the one set at it (the editors'), else its type's
(``cur:extractionDepth``), else its
function's - a frame part typed, a non-curricular part skipped, any other read in full - and a
section skipped takes its sections with it (a foreword's, an appendix's parts). The depth names
the package's job: statements (full), frame (typed), none (skip); a package of a heading alone
has nothing to read either, and stays a package, so every block of the text lies in exactly one.
A package over MOST_PAGES pages is parted at page boundaries, never within a block: a node's own
text holds no subsection to part it at, those follow it (konzept: page ranges, never fixed token
counts; 15 is not measured, a point of Paket 11). A document without headings is one package,
read in full. The keys - E0, E1, … in the document's order - are the run's (plan M1 6, Festlegung 3).
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import psycopg

from app.conversion.base import Block
from app.db.headings import node_headings
from app.pipeline.toc import OUTSIDE
from app.vocab.lookup import ConceptText, concept_texts

MOST_PAGES = 15
Depth = Literal["full", "typed", "skip"]
Job = Literal["statements", "frame", "none"]
_CV = "https://w3id.org/wlo/curriculum/vocab#"
_JOBS: dict[Depth, Job] = {"full": "statements", "typed": "frame", "skip": "none"}
_BY_FUNCTION: dict[str, Depth] = {_CV + "fn_frame": "typed", _CV + "fn_nonCurricular": "skip"}


@dataclass(frozen=True)
class SegmentNode:
    id: UUID
    parent_id: UUID | None
    position: int  # of its heading's block among the conversion's blocks
    depth: Depth  # its own: its type's or its function's (depth_of)
    title: str


@dataclass(frozen=True)
class WorkPackage:
    key: str
    node_id: UUID | None  # none for the title pages, and for a document without headings
    first: int  # positions of its first and last blocks of the text among the conversion's blocks
    last: int
    first_block: str
    last_block: str
    pages: tuple[int, int]
    path: tuple[str, ...]  # the titles from the top down to its node
    depth: Depth
    job: Job

    def as_result(self) -> dict[str, Any]:
        """The package as the run keeps it (its result, JSON)."""
        return {
            "key": self.key,
            "node_id": None if self.node_id is None else str(self.node_id),
            "first": self.first,
            "last": self.last,
            "first_block": self.first_block,
            "last_block": self.last_block,
            "pages": list(self.pages),
            "path": list(self.path),
            "depth": self.depth,
            "job": self.job,
        }


def depth_of(type_depth: str | None, function: str) -> Depth:
    """A node's own depth: its type's where it has one (a notation: full, typed, skip), else its
    function's."""
    if type_depth in _JOBS:
        return type_depth
    return _BY_FUNCTION.get(function, "full")


def segments(blocks: Sequence[Block], nodes: Sequence[SegmentNode]) -> list[WorkPackage]:
    """The work packages of the blocks (all of a conversion's, in order) by the document's nodes."""
    text = [at for at, block in enumerate(blocks) if block.kind not in OUTSIDE]
    if not text:
        return []
    ordered = sorted(nodes, key=lambda node: node.position)
    if not ordered:
        return [_package(blocks, "E1", None, text, (), "full")]
    by_id = {node.id: node for node in ordered}
    packages: list[WorkPackage] = []
    before = [at for at in text if at < ordered[0].position]
    if before:
        packages.append(_package(blocks, "E0", None, before, (), "typed"))
    number = 0
    for at, node in enumerate(ordered):
        end = ordered[at + 1].position if at + 1 < len(ordered) else len(blocks)
        own = [place for place in text if node.position <= place < end]
        path = tuple(reversed([up.title for up in _up(node, by_id)]))
        depth: Depth = "skip" if any(up.depth == "skip" for up in _up(node, by_id)) else node.depth
        for part in _by_pages(blocks, own):
            number += 1
            # a heading alone - its first child follows at once - leaves nothing to ask about
            job: Job | None = "none" if part == [node.position] else None
            packages.append(_package(blocks, f"E{number}", node.id, part, path, depth, job))
    return packages


async def work_packages(
    connection: psycopg.AsyncConnection, document_id: UUID, blocks: Sequence[Block]
) -> list[WorkPackage]:
    """The work packages of the document as its tree stands: its nodes at their headings in the
    store, their types' depths from the vocabularies; ``blocks`` are its conversion's, in order."""
    headings = await node_headings(connection, document_id)
    texts = await concept_texts(connection, sorted({h.node_type_iri for h in headings if h.node_type_iri}))
    positions = {block.id: at for at, block in enumerate(blocks)}
    nodes = [
        SegmentNode(
            heading.id,
            heading.parent_id,
            positions[heading.block_id],
            depth_of(heading.depth or _type_depth(texts, heading.node_type_iri), heading.function_iri),
            heading.title,
        )
        for heading in headings
        if heading.block_id in positions
    ]
    return segments(blocks, nodes)


def _type_depth(texts: Mapping[str, ConceptText], node_type: str | None) -> str | None:
    found = texts.get(node_type) if node_type is not None else None
    return None if found is None else found.depth


def _package(
    blocks: Sequence[Block],
    key: str,
    node_id: UUID | None,
    part: Sequence[int],
    path: tuple[str, ...],
    depth: Depth,
    job: Job | None = None,
) -> WorkPackage:
    first, last = blocks[part[0]], blocks[part[-1]]
    return WorkPackage(
        key,
        node_id,
        part[0],
        part[-1],
        first.id,
        last.id,
        (first.page, last.page),
        path,
        depth,
        job or _JOBS[depth],
    )


def _by_pages(blocks: Sequence[Block], own: Sequence[int]) -> Iterator[list[int]]:
    """The positions parted where they would run past MOST_PAGES pages."""
    part: list[int] = []
    for place in own:
        if part and blocks[place].page >= blocks[part[0]].page + MOST_PAGES:
            yield part
            part = []
        part.append(place)
    if part:
        yield part


def _up(node: SegmentNode, by_id: dict[UUID, SegmentNode]) -> Iterator[SegmentNode]:
    """The node and those it lies under, from it up."""
    current: SegmentNode | None = node
    while current is not None:
        yield current
        current = by_id.get(current.parent_id) if current.parent_id is not None else None
