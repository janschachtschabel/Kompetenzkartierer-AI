"""The prefix every request about a document's units shares (plan M1 6.1, Lesekontext; konzept §13.1).

It holds the document as its blocks - each led by its id, a table's rows by theirs, the pages
marked, headers and footers left out - then the document profile from X1 and the choice lists from
X3, in that order; the cache breakpoint goes behind it (app/llm/calls.py, ``cached_up_to``) and the
task of a unit after it. While the whole fits, the prefix is the same bytes for every unit of the
document. Where it does not fit, each unit reads a window: the title pages, the table of contents
and the frame parts, the outline of all sections by title, and the unit's section with its
neighbours - one level down where even that is too long. The prefix is then the same for every
unit of one window. What fits is counted (tiktoken), never guessed.
"""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from app.conversion.base import Block
from app.llm.budget import RESERVE_TOKENS, count_tokens
from app.llm.metering import MARGIN

WHOLE = "whole"  # the window of a prefix that holds the whole document
_OUTSIDE = frozenset({"page_header", "page_footer"})
_GAP = "[…]"


class PrefixTooLong(ValueError):
    """Not even the unit's section alone fits beside the title pages and the frame parts."""


@dataclass(frozen=True)
class Section:
    """A node's span in the reading order, its heading to its last descendant's block: ``first``
    and ``last`` are positions among the conversion's blocks (all of them, in order)."""

    key: str
    title: str
    level: int  # 1 for a section of the top level
    first: int
    last: int
    frame: bool = False  # a frame part (the function frame): every window keeps it


@dataclass(frozen=True)
class Prefix:
    text: str
    window: str  # WHOLE, or the key of the section the window is cut around


def prefix_budget(context_tokens: int, max_output_tokens: int) -> int:
    """The tokens a prefix may hold: the model's window less the rest of a request (RESERVE_TOKENS)
    and the answer's cap, a tenth beside for another tokenizer (MARGIN)."""
    return int((context_tokens - RESERVE_TOKENS - max_output_tokens) / MARGIN)


def render_blocks(blocks: Sequence[Block], printed_pages: Sequence[str | None]) -> str:
    """The blocks as the prefix writes them, every one of them."""
    return render_positions(blocks, range(len(blocks)), printed_pages)


class PrefixPlan:
    """The prefixes of one document's units: ``for_position`` gives the one a unit beginning at
    that block reads. ``always`` are positions every window keeps (the table of contents).

    Counting is CPU work (the tokenizer over the whole document, then over windows): a caller
    in the event loop runs ``for_position`` by ``asyncio.to_thread``. Each text is counted once.
    """

    def __init__(
        self,
        blocks: Sequence[Block],
        printed_pages: Sequence[str | None],
        sections: Sequence[Section],
        *,
        profile: str,
        lists: str,
        always: Collection[int],
        budget: int,
        count: Callable[[str], int] = count_tokens,
    ) -> None:
        self._blocks = blocks
        self._printed = printed_pages
        self._sections = sorted(sections, key=lambda section: (section.first, section.level))
        self._tail = _tail(profile, lists)
        self._budget = budget
        self._count = count
        start = min((section.first for section in self._sections), default=len(blocks))
        self._head = set(always) | set(range(start))
        for section in self._sections:
            if section.frame:
                self._head |= set(range(section.first, section.last + 1))
        self._whole: Prefix | None = None
        self._windows: dict[str, Prefix] = {}
        self._fitting: dict[str, bool] = {}  # by text

    def for_position(self, position: int) -> Prefix:
        """The prefix of a unit at ``position``; PrefixTooLong where no window fits."""
        if self._whole is None:
            body = render_positions(self._blocks, range(len(self._blocks)), self._printed)
            self._whole = Prefix(f"=== DOKUMENT ===\n{body}{self._tail}", WHOLE)
        if self._fits(self._whole.text):
            return self._whole
        return self._window(position)

    def _window(self, position: int) -> Prefix:
        parent: Section | None = None
        own: set[int] = set()
        level = 1
        while True:
            siblings = [
                section for section in self._sections if section.level == level and _within(section, parent)
            ]
            if not siblings:
                raise PrefixTooLong(f"no window around block {position} fits {self._budget} tokens")
            at = _containing(siblings, position)
            chosen = siblings[at]
            prefix = self._cut(chosen, siblings[max(at - 1, 0) : at + 2], own)
            if self._fits(prefix.text):
                return prefix
            children = [
                section
                for section in self._sections
                if section.level == level + 1 and _within(section, chosen)
            ]
            if not children:
                alone = self._cut(chosen, [chosen], own)
                if self._fits(alone.text):
                    return alone
                raise PrefixTooLong(f"section {chosen.key!r} alone does not fit {self._budget} tokens")
            own |= set(range(chosen.first, children[0].first))  # the parent's own text before its children
            parent, level = chosen, level + 1

    def _cut(self, chosen: Section, window: Sequence[Section], own: set[int]) -> Prefix:
        if (cached := self._windows.get(_window_key(chosen, window))) is not None:
            return cached
        kept = self._head | own
        for section in window:
            kept |= set(range(section.first, section.last + 1))
        outline = "".join("  " * (section.level - 1) + section.title + "\n" for section in self._sections)
        neighbours = " mit seinen Nachbarn" if len(window) > 1 else ""
        text = (
            "=== DOKUMENT (gekürzt) ===\n"
            "Hier stehen die Titelei, das Verzeichnis, die Rahmenteile und der Abschnitt"
            f" „{chosen.title}“{neighbours}; die übrigen Abschnitte nennt die Gliederung.\n"
            f"{render_positions(self._blocks, sorted(kept), self._printed)}"
            f"=== GLIEDERUNG ===\n{outline}{self._tail}"
        )
        prefix = Prefix(text, chosen.key)
        self._windows[_window_key(chosen, window)] = prefix
        return prefix

    def _fits(self, text: str) -> bool:
        if (known := self._fitting.get(text)) is None:
            known = self._fitting[text] = self._count(text) <= self._budget
        return known


def _window_key(chosen: Section, window: Sequence[Section]) -> str:
    return chosen.key + "|" + ",".join(section.key for section in window)


def _within(section: Section, parent: Section | None) -> bool:
    return parent is None or (
        parent.first <= section.first and section.last <= parent.last and section is not parent
    )


def _containing(siblings: Sequence[Section], position: int) -> int:
    """The sibling the position lies in; before all of them the first, between two the one before."""
    at = 0
    for index, section in enumerate(siblings):
        if section.first <= position:
            at = index
    return at


def _tail(profile: str, lists: str) -> str:
    parts = [
        f"=== DOKUMENTPROFIL ===\n{profile}\n" if profile else "",
        f"=== AUSWAHLLISTEN ===\n{lists}\n" if lists else "",
    ]
    return "".join(parts) + "=== ENDE DES DOKUMENTS ===\n"


def render_positions(
    blocks: Sequence[Block], positions: Sequence[int] | range, printed: Sequence[str | None]
) -> str:
    """The blocks at ``positions`` (in order) as the prefix writes them, a gap marked where they
    leave text out, before the first of them too."""
    lines: list[str] = []
    page = 0
    previous = -1
    chosen = set(positions)
    for position in positions:
        block = blocks[position]
        if block.kind in _OUTSIDE:
            continue
        skipped = any(
            blocks[between].kind not in _OUTSIDE
            for between in range(previous + 1, position)
            if between not in chosen
        )
        if skipped:
            lines.append(_GAP)
        previous = position
        if block.page != page:
            page = block.page
            shown = printed[page - 1] if page - 1 < len(printed) else None
            lines.append(f"— Seite {page} (gedruckt {shown}) —" if shown else f"— Seite {page} —")
        lines.extend(_lines(block))
    return "".join(line + "\n" for line in lines)


def _lines(block: Block) -> list[str]:
    if block.kind != "table":
        return [f"[{block.id}] {block.text}"]
    rows: dict[str, list[str]] = {}
    for cell in sorted(block.cells, key=lambda cell: (cell.row, cell.column)):
        rows.setdefault(cell.id[: cell.id.rindex("c")], []).append(cell.text)
    return [f"[{block.id}] Tabelle", *(f"[{row}] {' | '.join(values)}" for row, values in rows.items())]
