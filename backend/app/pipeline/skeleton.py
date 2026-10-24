"""A document's skeleton without the model (plan M1 6.3): its headings, their levels and parents,
their codes, and the node type a strong pattern of the lexicon gives a heading.

A heading is a text block of 200 signs and three lines at most that ends in no full stop, comma or
semicolon, is no list (two lines numbered) and is one of these: a pattern of the document's active
cues for headings or codes finds it that names a node type of the profile; it is numbered and set
bold or larger; the contents name it (app/pipeline/toc.py); it is set larger than the body by
LARGER; it is bold, 80 signs at most, and the text after it is not. What layout alone makes a
heading is none on the first page of a document of more pages - the title page, its title set
larger than any heading - and nothing before the contents is a heading: the title pages. A table
is a heading where a pattern finds its first cell (a learning field set as a table, "Lernfeld 5:
…"); its content is never one. Headers and footers are no text.
The level is the depth of a heading's numbering, else its entry's in the contents, else the rank
of its size among those of the larger headings (the largest first), else - bold, a table, the
contents naming it - one below the smallest of them. A heading lies under the last one before it
of a smaller level; its level as the skeleton gives it is its depth in that tree, from 1.
A strong cue - of STRONG at least, a threshold not yet measured (konzept §20.6) - types a heading
where all such cues that find it name one node type, and no homonym finds it: the node then
comes from a rule, the cue's IRI its rule. Cues tied for their word name other targets, so they
type nothing unless those agree on the node type. Any other heading's type is left to the model
(X1, plan M1 6.4).
A heading's code is its numbering, else - where a pattern found it - the number behind the word
that leads it ("Lernfeld 5:" 5, "Kompetenzbereich III" III), else its place among its siblings,
assigned (app/domain/iris.py). Its title is its wording, its lines joined by a space.
"""

import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, replace

from app.conversion.base import Block
from app.domain.iris import assign_code
from app.domain.lexicon import HOMONYM, NEGATIVE, ActiveCue
from app.pipeline.patterns import PatternSearch
from app.pipeline.toc import (
    OUTSIDE,
    Contents,
    TocEntry,
    find_contents,
    leading_number,
    number_depth,
    title_key,
)

STRONG = 0.9
LARGER = 1.15  # times the body's size
LONGEST = 200
MOST_LINES = 3
LONGEST_BOLD = 80
_CV = "https://w3id.org/wlo/curriculum/vocab#"
_PATTERN_KINDS = frozenset({_CV + "ck_headingPattern", _CV + "ck_codePattern"})
_IN_CONTENTS = _CV + "occ_toc"
_SENTENCE_ENDS = (".", ",", ";")
# The code behind the word that leads a heading: "Lernfeld 13GH:", "Teil A", "§ 8", "CE01"
_DESIGNATOR = re.compile(r"(?:[^\W\d_]+\.?|§)\s*(\d+(?:\.\d+)*[A-Z]*|[IVX]+\b|[A-Z]\b)")


@dataclass(frozen=True)
class Heading:
    key: str  # H1, H2, … in reading order
    position: int  # of its block among the conversion's blocks
    block_id: str
    page: int
    level: int  # its depth in the tree, 1 at the top
    parent: str | None  # the key of the heading it lies under
    title: str
    code: str
    code_assigned: bool
    node_type: str | None
    rule_id: str | None  # the cue that typed it


@dataclass(frozen=True)
class Skeleton:
    headings: tuple[Heading, ...]
    contents: Contents
    body_size: float | None
    timeouts: frozenset[str]  # the cues whose pattern took too long


@dataclass(frozen=True)
class _Found:
    position: int
    block: Block
    title: str
    number: str | None
    entry: TocEntry | None
    large: bool
    matched: tuple[ActiveCue, ...]  # the cues for headings that found it


def build_skeleton(
    blocks: Sequence[Block], cues: Iterable[ActiveCue], node_types: Collection[str]
) -> Skeleton:
    """The skeleton of the blocks (all of a conversion's, in order) by the document's active cues
    and the node types of its profile."""
    held = list(cues)
    search = PatternSearch()
    contents = find_contents(
        blocks, [found.cue for found in held if _IN_CONTENTS in found.cue.maps_to], search
    )
    body = body_size(blocks)
    heading_cues = [
        found
        for found in held
        if found.cue.kind in _PATTERN_KINDS
        and found.cue.role != NEGATIVE
        and any(target in node_types for target in found.cue.maps_to)
    ]
    found = _candidates(blocks, contents, body, heading_cues, search)
    headings = _tree(found, _raw_levels(found))
    typed = [_with_type(heading, item, node_types) for heading, item in zip(headings, found, strict=True)]
    return Skeleton(tuple(typed), contents, body, frozenset(search.timeouts))


def body_size(blocks: Sequence[Block]) -> float | None:
    """The size most of the text is set in: the median of the text blocks' sizes, by their signs."""
    sized = sorted(
        (block.font_size, len(block.text)) for block in blocks if block.kind == "text" and block.font_size
    )
    half, counted = sum(signs for _, signs in sized) / 2, 0
    for size, signs in sized:
        counted += signs
        if counted >= half:
            return size
    return None


def _candidates(
    blocks: Sequence[Block],
    contents: Contents,
    body: float | None,
    cues: Sequence[ActiveCue],
    search: PatternSearch,
) -> list[_Found]:
    order = [position for position, block in enumerate(blocks) if block.kind not in OUTSIDE]
    start = min(contents.positions, default=0)
    entries = {title_key(entry.title): entry for entry in contents.entries}
    pages = max((block.page for block in blocks), default=1)
    found: list[_Found] = []
    for at, position in enumerate(order):
        block = blocks[position]
        if position < start or position in contents.positions:
            continue
        lines = [line.strip() for line in _wording(block).splitlines() if line.strip()]
        title = " ".join(lines)
        if not _shaped(title, lines):
            continue
        matched = tuple(cue for cue in cues if search.found(cue.cue, title))
        if block.kind == "table":
            if matched:
                found.append(_Found(position, block, title, leading_number(title), None, False, matched))
            continue
        number, entry = leading_number(title), entries.get(title_key(title))
        large = body is not None and block.font_size is not None and block.font_size >= LARGER * body
        after = blocks[order[at + 1]] if at + 1 < len(order) else None
        bold = block.bold and len(title) <= LONGEST_BOLD and not (after is not None and after.bold)
        by_layout = (large or bold) and not (pages > 1 and block.page == 1)
        if matched or entry is not None or (number is not None and (large or block.bold)) or by_layout:
            found.append(_Found(position, block, title, number, entry, large, matched))
    return found


def _wording(block: Block) -> str:
    """A text block's text; a table's first cell."""
    if block.kind != "table":
        return block.text
    return next((cell.text for cell in block.cells if (cell.row, cell.column) == (1, 1)), "")


def _shaped(title: str, lines: Sequence[str]) -> bool:
    numbered = sum(leading_number(line) is not None for line in lines)
    return (
        bool(title)
        and len(title) <= LONGEST
        and len(lines) <= MOST_LINES
        and not title.endswith(_SENTENCE_ENDS)
        and numbered < 2
    )


def _raw_levels(found: Sequence[_Found]) -> list[int]:
    """Each heading's level as the document sets it, before the tree makes it a depth."""
    sizes = sorted({_size_class(item.block) for item in found if item.large}, reverse=True)
    below = len(sizes) + 1
    levels: list[int] = []
    for item in found:
        if item.number is not None:
            levels.append(number_depth(item.number))
        elif item.entry is not None and item.entry.level is not None:
            levels.append(item.entry.level)
        elif item.large:
            levels.append(sizes.index(_size_class(item.block)) + 1)
        else:
            levels.append(below)
    return levels


def _size_class(block: Block) -> float:
    """A size to half a point: sizes creep a little from line to line and heading to heading."""
    return round((block.font_size or 0) * 2) / 2


def _tree(found: Sequence[_Found], levels: Sequence[int]) -> list[Heading]:
    """The headings with their parents, depths and codes."""
    stack: list[tuple[int, Heading]] = []  # the open headings with their raw levels
    siblings: dict[str | None, int] = {}
    headings: list[Heading] = []
    for number, (item, level) in enumerate(zip(found, levels, strict=True), start=1):
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        key = None if parent is None else parent.key
        siblings[key] = siblings.get(key, 0) + 1
        code = _printed_code(item)
        heading = Heading(
            key=f"H{number}",
            position=item.position,
            block_id=item.block.id,
            page=item.block.page,
            level=1 if parent is None else parent.level + 1,
            parent=key,
            title=item.title,
            code=code if code is not None else assign_code(siblings[key]),
            code_assigned=code is None,
            node_type=None,
            rule_id=None,
        )
        stack.append((level, heading))
        headings.append(heading)
    return headings


def _printed_code(item: _Found) -> str | None:
    if item.number is not None:
        return item.number
    designated = _DESIGNATOR.match(item.title) if item.matched else None
    return None if designated is None else designated[1]


def _with_type(heading: Heading, item: _Found, node_types: Collection[str]) -> Heading:
    if any(found.cue.role == HOMONYM for found in item.matched):
        return heading  # the word means more than one thing here: the model tells which
    strong = [found for found in item.matched if (found.cue.strength or 0.0) >= STRONG]
    targets = {target for found in strong for target in found.cue.maps_to if target in node_types}
    if len(targets) != 1:
        return heading
    rule = min(found.cue.iri for found in strong)
    return replace(heading, node_type=targets.pop(), rule_id=rule)
