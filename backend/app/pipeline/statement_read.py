"""Statements as X3 and X4 read them from an answer (plan M1 7b, F9; konzept §7, §13.1), the statement
object both schemas share.

A statement stands in blocks of the document's conversion, and - where the request asked about a
range of them (X4's unit) - of that range; others are left out with a finding, and a statement of
none is. A wording field (the code, level, time, context, reference, example and purpose as written)
holds only where it stands in the statement's own blocks, in any case and spacing: what the model
took from a heading or the surroundings would be inherited (konzept §7), never stored as the
statement's wording. Codes become the vocabularies' IRIs - a statement of a kind or addressee no
active value names is left out, an obligation or layout marker of none unset -, a subkind holds only
by a key the question listed and under the statement's kind. Each is the model's, proposed. They
come in the document's order (by their first block, the answer's among equals), each pointing to the
content statements it names by their place in that order; at most MOST_STATEMENTS of them.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.conversion.base import Block
from app.db.findings import Finding
from app.domain.l1 import AnchorDraft, Severity, StatementDraft, check_profile_value
from app.pipeline.x1_outline import MODEL, PROPOSED

MOST_STATEMENTS = 500
WORDING_FIELDS = (
    "codeText",
    "levelText",
    "timeText",
    "contextText",
    "referenceMarker",
    "exampleText",
    "purposeText",
)
_MOST_VERBATIM, _MOST_TEXT = 20_000, 2_000  # the store's limits (migration l1_nodes)
_CV = "https://w3id.org/wlo/curriculum/vocab#"
_CONTENT = _CV + "kind_content"


@dataclass(frozen=True)
class StatementContext:
    """What answers are read against: the conversion's blocks and printed pages, the question's
    subkind keys, the profile's subkinds with the kinds each refines, the schemes' values by
    notation (StatementKinds, Addressees, Obligations, LayoutMarkers)."""

    stage: str  # "x3", "x4": the findings' rules are named by it
    document_id: UUID
    blocks: Sequence[Block]
    printed: Sequence[str | None]
    subkinds: Mapping[str, str]
    refines: Mapping[str, Sequence[str]]
    codes: Mapping[str, Mapping[str, str]]
    _positions: dict[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_positions", {block.id: at for at, block in enumerate(self.blocks)})

    def position(self, block_id: str) -> int | None:
        """The block's position among the conversion's blocks; None for one it does not hold."""
        return self._positions.get(block_id)


@dataclass(frozen=True)
class ReadStatement:
    draft: StatementDraft
    first: int  # the position of its first block among the conversion's
    targets: tuple[int, ...] = ()  # the content statements it points to, by their place in the list


def read_statements(
    given: Sequence[Mapping[str, Any]], context: StatementContext, *, within: range | None
) -> tuple[list[ReadStatement], list[Finding]]:
    """The statements of an answer (its ``statements``), in the document's order, and the findings
    of reading them; ``within``: the positions of the blocks the request asked about, or None."""
    reading = Reading(context)
    return reading.statements(given, within), reading.findings


class Reading:
    """One answer's statements being read, with the findings they give."""

    def __init__(self, context: StatementContext) -> None:
        self.context = context
        self.findings: list[Finding] = []

    def note(self, rule: str, severity: Severity, path: str, message: str, **details: Any) -> None:
        rule = f"{self.context.stage}.{rule}"
        self.findings.append(Finding(rule, severity, self.context.document_id, message, path, details))

    def statements(self, given: Sequence[Mapping[str, Any]], within: range | None) -> list[ReadStatement]:
        """The statements of an answer, as ``read_statements`` reads them."""
        read: list[tuple[int, ReadStatement, Sequence[int]]] = []
        for at, statement in enumerate(given):
            if len(read) == MOST_STATEMENTS:
                left = len(given) - at
                self.note(
                    "too_many_statements", "warning", "$.statements", f"{left} more left unread", left=left
                )
                break
            found = self.statement(statement, f"$.statements[{at}]", within)
            if found is not None:
                read.append((at, found, statement["targetsContent"]))
        read.sort(key=lambda item: item[1].first)  # stable: the answer's order among equals
        place = {at: index for index, (at, _, _) in enumerate(read)}
        content = {at for at, found, _ in read if found.draft.kind == _CONTENT}
        ordered = []
        for at, found, targets in read:
            kept = []
            for target in targets:
                if target in content:
                    kept.append(place[target])
                else:
                    path = f"$.statements[{at}].targetsContent"
                    self.note("target_not_content", "info", path, "no content statement read", target=target)
            ordered.append(ReadStatement(found.draft, found.first, tuple(kept)))
        return ordered

    def statement(self, given: Mapping[str, Any], path: str, within: range | None) -> ReadStatement | None:
        blocks = self.blocks(given["blockIds"], f"{path}.blockIds", within)
        verbatim = given["verbatim"].strip()
        if not blocks:
            self.note("statement_without_block", "warning", path, "no block of it holds the statement")
            return None
        if not verbatim or len(verbatim) > _MOST_VERBATIM:
            self.note("statement_too_long", "warning", f"{path}.verbatim", "no wording the store holds")
            return None
        kind = self.code("StatementKinds", given["statementKind"], f"{path}.statementKind")
        addressee = self.code("Addressees", given["addressee"], f"{path}.addressee")
        if kind is None or addressee is None:
            return None
        markers = [
            self.code("LayoutMarkers", marker, f"{path}.layoutMarkers[{at}]")
            for at, marker in enumerate(given["layoutMarkers"])
        ]
        draft = StatementDraft(
            verbatim=verbatim,
            kind=kind,
            addressees=(addressee,),
            anchors=(self.anchor(blocks),),
            origin=MODEL,
            review_status=PROPOSED,
            lead_in=self.text(given["leadIn"], f"{path}.leadIn"),
            subkind=self.subkind(given["statementSubkind"], kind, f"{path}.statementSubkind"),
            obligation=self.code("Obligations", given["obligation"], f"{path}.obligation"),
            details=self.details(given, blocks, path),
            layout_markers=tuple(marker for marker in markers if marker is not None),
        )
        return ReadStatement(draft, min(self.position(block) for block in blocks))

    def blocks(self, values: Sequence[str], path: str, within: range | None) -> tuple[str, ...]:
        kept: list[str] = []
        for at, value in enumerate(values):
            position = self.context.position(value)
            if position is None:
                message = "a block the conversion does not hold"
                self.note("unknown_block", "warning", f"{path}[{at}]", message, block=value)
            elif within is not None and position not in within:
                message = "a block outside the unit asked about"
                self.note("block_outside_unit", "warning", f"{path}[{at}]", message, block=value)
            else:
                kept.append(value)
        return tuple(dict.fromkeys(kept))

    def position(self, block_id: str) -> int:
        position = self.context.position(block_id)
        assert position is not None  # noqa: S101 - kept blocks are the conversion's
        return position

    def anchor(self, blocks: tuple[str, ...]) -> AnchorDraft:
        pages = [self.context.blocks[self.position(block)].page for block in blocks]
        first, last = min(pages), max(pages)
        printed = self.context.printed[first - 1] if first - 1 < len(self.context.printed) else None
        return AnchorDraft(
            blocks, page_start=first, page_end=last if last > first else None, printed_page=printed
        )

    def code(self, scheme: str, value: str | None, path: str) -> str | None:
        if value is None:
            return None
        found = self.context.codes.get(scheme, {}).get(value)
        if found is None:
            message = f"no active value {value!r} of {scheme}"
            self.note("unknown_value", "warning", path, message, value=value)
        return found

    def subkind(self, key: str | None, kind: str, path: str) -> str | None:
        if key is None:
            return None
        if (subkind := self.context.subkinds.get(key)) is None:
            self.note("unknown_key", "warning", path, "a key the question did not list", key=key)
            return None
        if (problem := check_profile_value(subkind, kind, self.context.refines)) is not None:
            message = "a subkind not under the statement's kind"
            self.note("subkind_mismatch", "warning", path, message, subkind=subkind, problem=problem)
            return None
        return subkind

    def text(self, value: str | None, path: str) -> str | None:
        """Wording as given, its edges trimmed; None where blank, cut to the store's limit with a finding."""
        value = None if value is None else value.strip()
        if not value:
            return None
        if len(value) > _MOST_TEXT:
            self.note("value_cut", "info", path, f"cut to its {_MOST_TEXT} signs", length=len(value))
            return value[:_MOST_TEXT]
        return value

    def details(self, given: Mapping[str, Any], blocks: Sequence[str], path: str) -> dict[str, Any]:
        # a table's text holds its cells' (app/conversion/assemble.py)
        own = _plain(" ".join(self.context.blocks[self.position(block)].text for block in blocks))
        details: dict[str, Any] = {}
        for name in WORDING_FIELDS:
            if (value := self.text(given[name], f"{path}.{name}")) is None:
                continue
            if _plain(value) in own:
                details[name] = value
            else:
                message = "a value not in the statement's blocks: inherited, not its wording"
                self.note("value_from_surroundings", "info", f"{path}.{name}", message, value=value)
        markers = [marker.strip() for marker in given["crossCuttingMarkers"] if marker.strip()]
        if markers:
            details["crossCuttingMarkers"] = markers
        return details


def _plain(text: str) -> str:
    """Text as wording fields are compared: in one case, each run of space one."""
    return " ".join(text.split()).casefold()
