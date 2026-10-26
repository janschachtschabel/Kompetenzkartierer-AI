"""The first layer of the core, as the pipeline and the editor hand it to the store (plan M1 4.5).

A drafted node holds its statements and its children in their order: their positions are where
they stand, from 1. Every statement keeps its wording, addressees and anchors, as the core's
shapes demand (``cur:verbatim`` 1, ``cur:addressee`` and ``cur:anchor`` one at least); an anchor
names its page, or the page the document prints, and the blocks it was found in - or, for a
wording the blocks hold no passage for (``cv:match_notFound``), its page alone. Values are IRIs:
which ones the vocabularies hold, the store checks. A draft naming a block, an addressee or what
a node applies to twice names it once.

A profile value - a node type, a statement's subkind, a document type - is one of its profile's
and lies under the core value it refines (``skos:broader``): a ``schul:Inhaltsbereich`` is a
``cv:fn_area``. What a profile holds comes from the vocabularies; the check takes it as given.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from app.domain.blocks import BLOCK_ID, CELL_ID

ProfileProblem = Literal["not_in_profile", "wrong_core"]
# what a specification is, as X1 names it (ontology/schemas/x1-dokumentprofil.schema.json)
SpecificationKind = Literal[
    "curriculum", "competencyFramework", "qualificationSpecification", "assessmentSpecification"
]
# what X3 finds in a document's frame besides statements (ontology/schemas/x3-rahmenteile.schema.json)
FramePartKind = Literal["competencyModels", "levelModels", "operators", "crossCuttingLegend", "rules"]
# how grave a finding of X5 is, as SHACL has it (sh:Violation, sh:Warning, sh:Info)
Severity = Literal["violation", "warning", "info"]
# a wording the blocks hold no fitting passage for: anchored at its page alone (plan M1 8.1, 9.4)
MATCH_NOT_FOUND = "https://w3id.org/wlo/curriculum/vocab#match_notFound"
# how far the editors have checked a node or statement (cv:ReviewStatuses; plan M1 9.5)
REVIEW_STATUSES = tuple(
    "https://w3id.org/wlo/curriculum/vocab#rev_" + status for status in ("proposed", "confirmed", "rejected")
)
# a statement's wording fields, kept in its details (X4 reads them, the editor's form offers them)
WORDING_FIELDS = (
    "codeText",
    "levelText",
    "timeText",
    "contextText",
    "referenceMarker",
    "exampleText",
    "purposeText",
)


def _once[T](items: tuple[T, ...]) -> tuple[T, ...]:
    """Each item once, where it first stands: a draft naming one twice means it once."""
    return tuple(dict.fromkeys(items))


def check_profile_value(value: str, core: str, allowed: Mapping[str, Sequence[str]]) -> ProfileProblem | None:
    """Why ``value`` may not stand for ``core``, or None where it may; ``allowed``: the profile's
    values, each with the core values it lies under."""
    if value not in allowed:
        return "not_in_profile"
    if core not in allowed[value]:
        return "wrong_core"
    return None


@dataclass(frozen=True)
class AnchorDraft:
    """Where a value was found: a page or a printed page, and the blocks."""

    block_ids: tuple[str, ...]
    page_start: int | None
    page_end: int | None = None
    printed_page: str | None = None
    quote: str | None = None
    match_kind: str | None = None
    match_score: float | None = None
    table_cell: str | None = None
    char_start: int | None = None
    char_end: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_ids", _once(self.block_ids))
        not_found = self.match_kind == MATCH_NOT_FOUND
        if self.page_start is None and (self.printed_page is None or not_found):
            raise ValueError(
                "an anchor names its page, or the page the document prints where it found the passage"
            )
        if (self.page_start is None and self.page_end is not None) or (
            self.page_start is not None
            and (self.page_start < 1 or (self.page_end is not None and self.page_end < self.page_start))
        ):
            raise ValueError(f"no such page range: {self.page_start} to {self.page_end}")
        if (not self.block_ids and not not_found) or any(
            BLOCK_ID.fullmatch(block) is None for block in self.block_ids
        ):
            raise ValueError(f"an anchor names its blocks as p<page>-b<n>, not {self.block_ids}")
        if self.match_score is not None and not 0 <= self.match_score <= 1:
            raise ValueError(f"a match score lies between 0 and 1, not {self.match_score}")
        if self.table_cell is not None and CELL_ID.fullmatch(self.table_cell) is None:
            raise ValueError(f"a table cell is T<n>:r<i>c<j>, not {self.table_cell!r}")


@dataclass(frozen=True)
class StatementDraft:
    """A statement of a node: its wording as the document gives it, and what it is."""

    verbatim: str
    kind: str
    addressees: tuple[str, ...]
    anchors: tuple[AnchorDraft, ...]
    origin: str
    review_status: str
    language: str = "de"
    lead_in: str | None = None
    subkind: str | None = None
    obligation: str | None = None
    rule_id: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)
    layout_markers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "addressees", _once(self.addressees))
        if not self.verbatim.strip():
            raise ValueError("a statement has a wording")
        try:
            self.verbatim.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("a wording is text: it holds no lone surrogate") from error
        if not self.addressees:
            raise ValueError("a statement has an addressee at least")
        if not self.anchors:
            raise ValueError("a statement has an anchor at least: where in the source it stands")


@dataclass(frozen=True)
class NodeDraft:
    """A node of the document's structure, with its statements and children in their order."""

    function: str
    origin: str
    review_status: str
    node_type: str | None = None
    code: str | None = None
    code_assigned: bool = False
    original_title: str | None = None
    title_language: str = "de"
    obligation: str | None = None
    scope_share: str | None = None
    extraction_depth: str | None = None
    applies_to: tuple[UUID, ...] = ()
    rule_id: str | None = None
    anchors: tuple[AnchorDraft, ...] = ()
    statements: tuple[StatementDraft, ...] = ()
    children: tuple["NodeDraft", ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "applies_to", _once(self.applies_to))
        if self.code_assigned and self.code is None:
            raise ValueError("an assigned code is a code: the node's position")


@dataclass(frozen=True)
class VariantDraft:
    """A variant of a specification (a track, a focus): its key, its label as written, its kind."""

    key: str
    label: str
    kind: str


@dataclass(frozen=True)
class SpecificationDraft:
    """What a document stands for - a subject's curriculum, an occupation's - with its applicability
    (codes as IRIs, wording as written), the blocks it was read from and its variants."""

    key: str
    kind: SpecificationKind
    title: str
    field_text: str | None
    applicability: Mapping[str, Any]
    evidence: tuple[str, ...]
    variants: tuple[VariantDraft, ...] = ()


@dataclass(frozen=True)
class ProfileDraft:
    """A document's profile as X1 reads it: its own values (dates as YYYY, YYYY-MM or YYYY-MM-DD),
    the blocks they were read from, its specifications, and the terms of its own it uses."""

    title: str | None
    document_type: str | None
    legal_form: str | None
    binding: str | None
    lifecycle: str | None
    issuer: str | None
    edition: str | None
    issued: str | None
    valid_from: str | None
    evidence: tuple[str, ...]
    specifications: tuple[SpecificationDraft, ...]
    term_mappings: tuple[Mapping[str, Any], ...]
    new_terms: tuple[Mapping[str, Any], ...]
