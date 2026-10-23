"""A document's active profile (konzept §12.2, §12.4, plan M1 4.8): of its sector's cues, those
that hold for its regions, document type and plan generation, the more specific before the
general.

A cue holds where every scope it sets holds: one of its regions is one of the document's own or
one they lie in (a cue for all of Germany holds in each country), its document type is the
document's, its plan generation the document's; a cue that sets none holds everywhere. Where
the document's type or plan generation is not known (None) - X1 is to tell the generation by
such cues, and a document may carry none - a cue of that scope holds, but the scope does not
rank it. Places, dates, subjects, issuers and kinds of institution do not filter: a cue carries
them, with its examples, for the prompt (plan M1 6). Cues on one word, pattern or layout
signal of one kind compete; the first by rank holds - by region first, one of the document's
own before one they lie in before none (a country's cue before Germany's before the sector's,
konzept §12.4), then the more of its document type and plan generation that match the
document's known ones, then checked before unchecked, then the stronger (no strength is none).
Where several share the first rank and point to other targets, all hold as a tie, and the
model gets their rule texts. A negative cue and a homonym compete with none and always hold; a
homonym keeps its other target. The document's own terms (its profile from X1) are laid over
this when the prompt is built (plan M1 6).

A pattern is searched with a time limit, so a pattern that backtracks without end stops.
"""

from collections import defaultdict
from collections.abc import Iterable, Set
from dataclasses import dataclass

import regex

PATTERN_TIMEOUT_S = 0.05
NEGATIVE = "https://w3id.org/wlo/curriculum/vocab#role_negative"
HOMONYM = "https://w3id.org/wlo/curriculum/vocab#role_homonym"
# Cues that warn of a reading rather than offer one: lost to a stronger cue on their word, the
# model would lose the warning - a homonym's other target and the rule that tells them apart
_ALWAYS = frozenset({NEGATIVE, HOMONYM})


class PatternTimeout(Exception):
    """A pattern took longer than its time limit on a text."""


@dataclass(frozen=True)
class Cue:
    iri: str
    role: str
    kind: str
    maps_to: tuple[str, ...]
    surface_form: str | None = None
    pattern: str | None = None
    layout_signal: str | None = None
    also_maps_to: tuple[str, ...] = ()
    occurs_in: frozenset[str] = frozenset()
    scope_regions: frozenset[str] = frozenset()
    scope_document_types: frozenset[str] = frozenset()
    scope_institution_types: frozenset[str] = frozenset()
    scope_subjects: frozenset[str] = frozenset()
    scope_issuers: frozenset[str] = frozenset()
    plan_generations: frozenset[str] = frozenset()
    valid_from: str | None = None  # as written: YYYY, YYYY-MM or YYYY-MM-DD
    valid_until: str | None = None
    strength: float | None = None
    verified: bool = False
    recognition_hints: tuple[str, ...] = ()
    negative_hints: tuple[str, ...] = ()
    positive_examples: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActiveCue:
    cue: Cue
    tie: bool  # it shares the first rank on its word with a cue of another target


def active_cues(
    cues: Iterable[Cue],
    regions: Set[str],
    document_type: str | None,
    plan_generation: str | None,
    *,
    wider_regions: Set[str] = frozenset(),
) -> list[ActiveCue]:
    """The cues that hold for a document of ``regions`` - its own, a country - and the
    ``wider_regions`` they lie in (Germany), of ``document_type`` and ``plan_generation`` (None
    where unknown), by their IRIs."""
    document = _Document(frozenset(regions), frozenset(wider_regions), document_type, plan_generation)
    competing: defaultdict[tuple[str, str], list[Cue]] = defaultdict(list)
    held: list[ActiveCue] = []
    for cue in cues:
        if not _holds(cue, document):
            continue
        if cue.role in _ALWAYS:
            held.append(ActiveCue(cue, tie=False))
        else:
            competing[_trigger(cue)].append(cue)
    for group in competing.values():
        ranks = {cue.iri: _rank(cue, document) for cue in group}
        best = max(ranks.values())
        first = [cue for cue in group if ranks[cue.iri] == best]
        tie = len({cue.maps_to for cue in first}) > 1
        held.extend(ActiveCue(cue, tie) for cue in first)
    return sorted(held, key=lambda found: found.cue.iri)


def pattern_matches(pattern: str, text: str, timeout: float = PATTERN_TIMEOUT_S) -> bool:
    """Whether ``pattern`` (the syntax of Python's re) finds a match in ``text``; PatternTimeout
    where it takes longer than ``timeout`` seconds."""
    try:
        return regex.search(pattern, text, flags=regex.V0, timeout=timeout) is not None
    except TimeoutError as error:
        raise PatternTimeout(f"{pattern!r} took longer than {timeout} s") from error


@dataclass(frozen=True)
class _Document:
    regions: frozenset[str]
    wider_regions: frozenset[str]
    document_type: str | None
    plan_generation: str | None


def _holds(cue: Cue, document: _Document) -> bool:
    return (
        (not cue.scope_regions or _region_rank(cue, document) > 0)
        and _open_to(cue.scope_document_types, document.document_type)
        and _open_to(cue.plan_generations, document.plan_generation)
    )


def _open_to(scope: frozenset[str], value: str | None) -> bool:
    """Whether a scope lets its cue hold for a document's ``value``: it sets none, the value is
    unknown, or it is one of them."""
    return not scope or value is None or value in scope


def _trigger(cue: Cue) -> tuple[str, str]:
    """What cues compete on: their kind and their word (in one case), pattern or layout signal."""
    if cue.surface_form is not None:
        return cue.kind, "word:" + cue.surface_form.casefold()
    if cue.pattern is not None:
        return cue.kind, "pattern:" + cue.pattern
    return cue.kind, "layout:" + str(cue.layout_signal)


def _region_rank(cue: Cue, document: _Document) -> int:
    """2 where one of the cue's regions is one of the document's own, 1 where it is one they lie
    in, 0 where it names neither (or none)."""
    if not cue.scope_regions.isdisjoint(document.regions):
        return 2
    return 1 if not cue.scope_regions.isdisjoint(document.wider_regions) else 0


def _rank(cue: Cue, document: _Document) -> tuple[int, int, bool, float]:
    # a scope ranks a cue only where it is known to match: unknown, it neither excludes nor ranks
    matching = (document.document_type in cue.scope_document_types) + (
        document.plan_generation in cue.plan_generations
    )
    return _region_rank(cue, document), matching, cue.verified, cue.strength or 0.0
