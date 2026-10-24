"""The lexicon excerpt of a request about a unit (plan M1 7b, F6; konzept §12.2): of the document's
active cues (app/domain/lexicon.py), the words and sentence patterns that bear on the unit's text,
each a line of the task - the word or pattern, the targets the task names it by, its rule texts.

A word bears where it stands in one of the texts, in any case and within a longer word too (a
compound, a plural); a pattern where it matches one of them (each a block), searched with its time
limit (app/pipeline/patterns.py). A cue of no target the task names, and one that says what a word
is not, make no line, as in X1's question. The checked come first, then the stronger, then by IRI;
each line once, at most MOST_LINES. Matching is CPU work: a caller in the event loop runs it by
``asyncio.to_thread``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.lexicon import HOMONYM, NEGATIVE, ActiveCue, Cue
from app.pipeline.patterns import PatternSearch

MOST_LINES = 80  # konzept §12.2: some 50 to 80 lines
_CV = "https://w3id.org/wlo/curriculum/vocab#"
_WORD, _SENTENCE = _CV + "ck_term", _CV + "ck_sentencePattern"


@dataclass(frozen=True)
class Excerpt:
    text: str  # its lines, none where no cue bears on the texts
    timeouts: frozenset[str]  # the cues whose pattern took too long


def lexicon_excerpt(cues: Sequence[ActiveCue], texts: Sequence[str], names: Mapping[str, str]) -> Excerpt:
    """The excerpt of ``cues`` for a unit of these ``texts``; ``names`` are the targets the task
    names, each by how it names it ("Kompetenzerwartung (U3)")."""
    search = PatternSearch()
    folded = [text.casefold() for text in texts]
    ranked = sorted(
        (found.cue for found in cues),
        key=lambda cue: (not cue.verified, -(cue.strength or 0.0), cue.iri),
    )
    lines: dict[str, None] = {}
    for cue in ranked:
        if len(lines) == MOST_LINES:
            break
        if (line := _line(cue, names)) is not None and _bears(cue, texts, folded, search):
            lines[line] = None
    return Excerpt("\n".join(lines), frozenset(search.timeouts))


def _bears(cue: Cue, texts: Sequence[str], folded: Sequence[str], search: PatternSearch) -> bool:
    """Whether the cue - one of a line - bears on the texts: its word in one, else its pattern."""
    if cue.kind == _WORD and cue.surface_form is not None:
        word = cue.surface_form.casefold()
        return any(word in text for text in folded)
    return any(search.found(cue, text) for text in texts)


def _line(cue: Cue, names: Mapping[str, str]) -> str | None:
    if cue.role == NEGATIVE or not (targets := [names[iri] for iri in cue.maps_to if iri in names]):
        return None
    if cue.kind == _WORD and cue.surface_form is not None:
        line = f"„{cue.surface_form}“ → {', '.join(targets)}"
    elif cue.kind == _SENTENCE and cue.pattern is not None:
        line = f"Satzmuster /{cue.pattern}/ → {', '.join(targets)}"
    else:
        return None
    others = [names[iri] for iri in cue.also_maps_to if iri in names]
    if cue.role == HOMONYM and others:
        line += f", sonst {', '.join(others)} (je nach Zusammenhang)"
    if cue.recognition_hints:
        line += " — " + " ".join(cue.recognition_hints)
    return line
