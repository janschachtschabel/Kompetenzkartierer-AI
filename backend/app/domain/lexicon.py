"""A document's active profile (konzept §12.2, §12.4, plan M1 4.8): of its sector's cues, those
that hold for its regions, document type and plan generation, the more specific before the
general.

A cue holds where every scope it sets holds: one of its regions is the document's or one the
document's lies in (a cue for all of Germany holds in each country), its document type is the
document's, its plan generation the document's; a cue that sets none holds everywhere. Dates,
subjects, issuers and kinds of institution do not filter: they go to the model as text. Cues
on one word, pattern or layout signal of one kind compete; the first by rank holds - the more
scopes it sets, then checked before unchecked, then the stronger (no strength is none). Where
several share the first rank and point to other targets, all hold as a tie, and the model gets
their rule texts. A negative cue and a homonym compete with none and always hold; a homonym
keeps its other target. The document's own terms (its profile from X1) are laid over this when
the prompt is built (plan M1 6).

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
    scope_regions: frozenset[str] = frozenset()
    scope_document_types: frozenset[str] = frozenset()
    plan_generations: frozenset[str] = frozenset()
    strength: float | None = None
    verified: bool = False
    recognition_hints: tuple[str, ...] = ()
    negative_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActiveCue:
    cue: Cue
    tie: bool  # it shares the first rank on its word with a cue of another target


def active_cues(
    cues: Iterable[Cue], regions: Set[str], document_type: str | None, plan_generation: str | None
) -> list[ActiveCue]:
    """The cues that hold for a document of ``regions`` (with those they lie in), ``document_type``
    and ``plan_generation``, by their IRIs."""
    competing: defaultdict[tuple[str, str], list[Cue]] = defaultdict(list)
    held: list[ActiveCue] = []
    for cue in cues:
        if not _holds(cue, regions, document_type, plan_generation):
            continue
        if cue.role in _ALWAYS:
            held.append(ActiveCue(cue, tie=False))
        else:
            competing[_trigger(cue)].append(cue)
    for group in competing.values():
        best = max(_rank(cue) for cue in group)
        first = [cue for cue in group if _rank(cue) == best]
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


def _holds(cue: Cue, regions: Set[str], document_type: str | None, plan_generation: str | None) -> bool:
    return (
        (not cue.scope_regions or not cue.scope_regions.isdisjoint(regions))
        and (not cue.scope_document_types or document_type in cue.scope_document_types)
        and (not cue.plan_generations or plan_generation in cue.plan_generations)
    )


def _trigger(cue: Cue) -> tuple[str, str]:
    """What cues compete on: their kind and their word (in one case), pattern or layout signal."""
    if cue.surface_form is not None:
        return cue.kind, "word:" + cue.surface_form.casefold()
    if cue.pattern is not None:
        return cue.kind, "pattern:" + cue.pattern
    return cue.kind, "layout:" + str(cue.layout_signal)


def _rank(cue: Cue) -> tuple[int, bool, float]:
    scopes = sum(bool(scope) for scope in (cue.scope_regions, cue.scope_document_types, cue.plan_generations))
    return scopes, cue.verified, cue.strength or 0.0
