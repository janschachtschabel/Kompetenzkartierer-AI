"""X1's outline (plan M1 6.4): the headings a strong pattern left untyped, asked in batches of
OUTLINE_BATCH (prompts/x1_outline.py); the decision for every heading of the skeleton; the tree.

A heading a pattern typed is the rule's (``cv:orig_rule``, the cue its rule). One the model typed
takes the core function its type refines; one it gave no type takes the function it gave (both
``cv:orig_model``). One the answer leaves out is a grouping where it holds headings and a unit
where it does not, untyped, a rule's (``x1.outline_unanswered``) - and a finding. What the answer
names that was not asked or listed is a finding and no value; of two answers for one heading the
first holds. The schema cannot reject a heading the skeleton took wrongly: it becomes a node for
the editors (plan M1 6, Grenzen). Every node is anchored at its heading's block, its code and
title the skeleton's; its depth is left to its type, or to its function, where it is read (X2).
"""

from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.conversion.base import Block
from app.db.findings import Finding
from app.domain.l1 import AnchorDraft, NodeDraft
from app.pipeline.skeleton import Heading, Skeleton
from app.pipeline.toc import OUTSIDE

OPENING_SIGNS = 300
OUTLINE_BATCH = 50  # headings a question: some 80 answer tokens each, far within the cap
UNANSWERED = "x1.outline_unanswered"
_CV = "https://w3id.org/wlo/curriculum/vocab#"
MODEL, RULE, PROPOSED = _CV + "orig_model", _CV + "orig_rule", _CV + "rev_proposed"
_PATH = " / "


@dataclass(frozen=True)
class OutlineItem:
    key: str
    level: int
    path: str  # the titles from the top down to it
    opening: str  # the first OPENING_SIGNS of its own text


@dataclass(frozen=True)
class OutlineContext:
    """What answers are read against: the call's node type keys, each profile node type's core
    function, the schemes' values by notation (NodeFunctions, ScopeShares), X1's specification keys."""

    document_id: UUID
    types: Mapping[str, str]
    functions_of: Mapping[str, str]
    codes: Mapping[str, Mapping[str, str]]
    specifications: Collection[str]


@dataclass(frozen=True)
class Decision:
    node_type: str | None
    function: str
    applies_to: tuple[str, ...]  # specification keys
    scope_share: str | None
    origin: str
    rule_id: str | None


def outline_items(skeleton: Skeleton, blocks: Sequence[Block]) -> list[OutlineItem]:
    """The headings left untyped, as the question lists them."""
    by_key = {heading.key: heading for heading in skeleton.headings}
    starts = [heading.position for heading in skeleton.headings]
    items: list[OutlineItem] = []
    for at, heading in enumerate(skeleton.headings):
        if heading.node_type is not None:
            continue
        end = starts[at + 1] if at + 1 < len(starts) else len(blocks)
        own = " ".join(
            block.text for block in blocks[heading.position + 1 : end] if block.kind not in OUTSIDE
        )
        items.append(OutlineItem(heading.key, heading.level, _path(heading, by_key), own[:OPENING_SIGNS]))
    return items


def batches(items: Sequence[OutlineItem]) -> list[list[OutlineItem]]:
    return [list(items[at : at + OUTLINE_BATCH]) for at in range(0, len(items), OUTLINE_BATCH)]


def decide(
    skeleton: Skeleton, asked: Collection[str], answers: Sequence[Mapping[str, Any]], context: OutlineContext
) -> tuple[dict[str, Decision], list[Finding]]:
    """The decision for every heading of the skeleton by the headings the answers (all batches') give,
    with the findings of reading them."""
    findings: list[Finding] = []

    def note(rule: str, path: str, message: str, **details: Any) -> None:
        findings.append(Finding(rule, "warning", context.document_id, message, path, details))

    decisions: dict[str, Decision] = {}
    functions = context.codes.get("NodeFunctions", {})
    for at, given in enumerate(answers):
        key = given["headingId"]
        if key not in asked:
            note(
                "x1.unknown_key",
                f"$.headings[{at}].headingId",
                "a heading the question did not list",
                key=key,
            )
            continue
        if key in decisions:
            note("x1.duplicate_key", f"$.headings[{at}].headingId", "a heading answered before", key=key)
            continue
        decisions[key] = _decision(given, at, context, note)
    parents = {heading.parent for heading in skeleton.headings}
    for heading in skeleton.headings:
        if heading.node_type is not None:
            core = context.functions_of.get(heading.node_type, _CV + "fn_unit")
            decisions[heading.key] = Decision(heading.node_type, core, (), None, RULE, heading.rule_id)
        elif heading.key not in decisions:
            default = "grouping" if heading.key in parents else "unit"
            note(UNANSWERED, f"$.headings[{heading.key}]", "the answer left the heading out", key=heading.key)
            decisions[heading.key] = Decision(
                None, functions.get(default, _CV + "fn_" + default), (), None, RULE, UNANSWERED
            )
    return decisions, findings


def _decision(
    given: Mapping[str, Any], at: int, context: OutlineContext, note: Callable[..., None]
) -> Decision:
    """The model's decision for one heading, what it names wrongly noted."""
    functions = context.codes.get("NodeFunctions", {})
    node_type = None
    if given["nodeType"] is not None:
        node_type = context.types.get(given["nodeType"])
        if node_type is None:
            note(
                "x1.unknown_key",
                f"$.headings[{at}].nodeType",
                "a type the question did not list",
                key=given["nodeType"],
            )
    function = context.functions_of.get(node_type) if node_type else functions.get(given["nodeFunction"])
    applies_to = []
    for place, specification in enumerate(given["appliesTo"]):
        if specification in context.specifications:
            applies_to.append(specification)
        else:
            path = f"$.headings[{at}].appliesTo[{place}]"
            note("x1.unknown_key", path, "a specification the profile does not hold", key=specification)
    share = given["scopeShare"]
    return Decision(
        node_type,
        function or functions.get("unit", _CV + "fn_unit"),
        tuple(dict.fromkeys(applies_to)),
        None if share is None else context.codes.get("ScopeShares", {}).get(share),
        MODEL,
        None,
    )


def build_tree(
    skeleton: Skeleton, decisions: Mapping[str, Decision], specifications: Mapping[str, UUID]
) -> list[NodeDraft]:
    """The document's top nodes, each with its children, by the decisions; ``specifications`` are the
    ids X1's specifications were written with, by their keys."""
    children: dict[str | None, list[Heading]] = {}
    for heading in skeleton.headings:
        children.setdefault(heading.parent, []).append(heading)

    def node(heading: Heading) -> NodeDraft:
        decision = decisions[heading.key]
        return NodeDraft(
            function=decision.function,
            origin=decision.origin,
            review_status=PROPOSED,
            node_type=decision.node_type,
            code=heading.code,
            code_assigned=heading.code_assigned,
            original_title=heading.title,
            scope_share=decision.scope_share,
            applies_to=tuple(specifications[key] for key in decision.applies_to if key in specifications),
            rule_id=decision.rule_id,
            anchors=(
                AnchorDraft(block_ids=(heading.block_id,), page_start=heading.page, quote=heading.title),
            ),
            children=tuple(node(child) for child in children.get(heading.key, [])),
        )

    return [node(heading) for heading in children.get(None, [])]


def _path(heading: Heading, by_key: Mapping[str, Heading]) -> str:
    titles = list(_up(heading, by_key))
    return _PATH.join(reversed(titles))


def _up(heading: Heading, by_key: Mapping[str, Heading]) -> Iterator[str]:
    current: Heading | None = heading
    while current is not None:
        yield current.title
        current = by_key.get(current.parent) if current.parent is not None else None
