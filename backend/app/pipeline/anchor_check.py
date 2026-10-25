"""A wording checked against the text of the blocks its anchor names (plan M1 8.1; konzept §13.1:
"gegen genau diese Blöcke"): how it stands there - its match kind (cv:MatchKinds) - and the document's
text at the place, which the anchor keeps as its quote (cur:quote).

The text is the blocks' texts in reading order, one line end between two; an anchor's character span
counts in it. The stages: word for word, across whitespace, with the gaps the wording marks
(app/pipeline/anchor_match.py), then normalized or fuzzy (app/pipeline/anchor_fuzzy.py). A wording none
of them finds is ``notFound``. CPU work: a caller in the event loop runs this by ``asyncio.to_thread``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.pipeline.anchor_fuzzy import fuzzy
from app.pipeline.anchor_match import elided, needle, verbatim

# The longest wording the fuzzy stage takes, as long as the old app's quotes could be: difflib's work
# grows with the wording's square, and a longer one is checked word for word (with its gaps) only.
MAX_FUZZY = 2_000

MatchKind = Literal["exact", "whitespace", "elided", "normalized", "fuzzy", "notFound"]


@dataclass(frozen=True)
class AnchorMatch:
    kind: MatchKind  # the notation in cv:MatchKinds
    score: float | None = None  # a fuzzy quote's likeness, 0..1, perhaps under MIN_RATIO
    quote: str | None = None  # the document's text at the place
    start: int | None = None  # the place in the text of the blocks
    end: int | None = None


NOT_FOUND = AnchorMatch("notFound")


def check_wording(wording: str, texts: Sequence[str]) -> AnchorMatch:
    """How ``wording`` stands in the text of ``texts`` (the anchor's blocks, in order)."""
    text = "\n".join(texts)
    target = needle(wording)
    if not target or not text:
        return NOT_FOUND
    hit = verbatim(target, text) or elided(target, text)
    if hit is None and len(target) <= MAX_FUZZY:
        hit = fuzzy(target, text)
    if hit is None:
        return NOT_FOUND
    return AnchorMatch(hit.kind, hit.score, text[hit.start : hit.end], hit.start, hit.end)
