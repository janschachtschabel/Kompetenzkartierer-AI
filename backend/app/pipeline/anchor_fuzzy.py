"""The fuzzy stage of checking a wording against the text of its anchor's blocks (plan M1 8.1), after
the old app's ce_api/services/extraction/anchors.py: the passage most like the wording, among the places
its rare words lead to, tightened to what the two share (app/pipeline/anchor_passage.py). Normalized
where the document's words there are the wording's - case, marks, spacing and soft hyphens aside -
else fuzzy with its likeness: no proof of the wording (konzept §5.1).

difflib is pure Python and its cost grows with both lengths: over a long text it once took 22 s (old
app, audit E-20). So the wording's opening is aligned at no more than ``FUZZY_PLACES`` places, where one
of its words stands that the text holds at most ``FUZZY_RARE`` times (or its rarest), and the caller
gives no wording longer than ``anchor_check.MAX_FUZZY``. A table block of a whole plan stays bounded so.
"""

import difflib
import re

from app.pipeline.anchor_match import Hit, words
from app.pipeline.anchor_passage import candidates

FUZZY_QUOTE = 300  # the wording's opening the places are looked for with
FUZZY_PLACES = 32
FUZZY_RARE = 4
_WORD = re.compile(r"\w{3,}")
# The likeness asked of a passage, and how much less a passage tightened from the window may score
# before the window is the better passage (old app, live replay 2026-10-04).
MIN_RATIO = 0.8
CLEARLY_WORSE = 0.05
# How far past the window its passage may run: a wording that left out words before the longest shared
# stretch starts the window late by as many characters; 24 hold the two or three words it drops.
TIGHTEN_MARGIN = 24


def fuzzy(target: str, text: str) -> Hit | None:
    """The passage most like the wording, with ``normalized`` or ``fuzzy``; None under ``MIN_RATIO``."""
    window = _fuzzy_span(target, text)
    if window is None:
        return None
    low, high, likeness = window
    start, end, score = _passage(text, low, high, target, likeness)
    found = text[start:end]
    if [word.casefold() for word in words(found)] == [word.casefold() for word in words(target)]:
        return Hit(start, end, "normalized")
    return Hit(start, end, "fuzzy", round(score, 3))


def _fuzzy_span(target: str, text: str) -> tuple[int, int, float] | None:
    """The window most like the wording among its rare words' places, and how alike: the opening is
    aligned on the longest stretch it shares there, the best score wins (the earliest among equals), and
    the whole wording then has to match a window of its own length - an opening the text holds does not
    carry an invented rest."""
    probe = target[:FUZZY_QUOTE]
    best: tuple[float, int] | None = None
    for low, high in _places(probe, text):
        found = _aligned(probe, text, low, high)
        if found is not None and (best is None or found[0] > best[0]):
            best = found
    if best is None or best[0] < MIN_RATIO:
        return None
    likeness, start = best
    end = min(len(text), start + len(target))
    if len(target) > len(probe):
        likeness = ratio(text[start:end], target)
        if likeness < MIN_RATIO:
            return None
    return start, end, likeness


def _places(probe: str, text: str) -> list[tuple[int, int]]:
    """Stretches of ``text`` where ``probe`` would stand if one of its rare words stood there - one the
    text holds at most ``FUZZY_RARE`` times, or its rarest where none is that rare: the rarest words
    first, at most ``FUZZY_PLACES`` stretches, half the probe's length to spare on either side,
    overlapping ones merged, in the text's order. A commoner word leads to every passage that shares
    only a plan's recurring wording ("Lernfeld", "Zeitrichtwert")."""
    offsets: dict[str, int] = {}
    for match in _WORD.finditer(probe):
        offsets.setdefault(match.group(), match.start())
    counted = sorted((text.count(word), at, word) for word, at in offsets.items())
    counted = [entry for entry in counted if entry[0]]
    rare = max(FUZZY_RARE, counted[0][0]) if counted else 0
    spare = len(probe) // 2
    stretches: list[tuple[int, int]] = []
    for count, offset, word in counted:
        if count > rare or len(stretches) == FUZZY_PLACES:
            break
        at = text.find(word)
        while at != -1 and len(stretches) < FUZZY_PLACES:
            begin = at - offset
            stretches.append((max(0, begin - spare), min(len(text), begin + len(probe) + spare)))
            at = text.find(word, at + 1)
    merged: list[tuple[int, int]] = []
    for low, high in sorted(stretches):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


def _aligned(probe: str, text: str, low: int, high: int) -> tuple[float, int] | None:
    """How alike the window of the probe's length is where the probe aligns on the longest stretch it
    shares with ``text[low:high]``, and where that window starts."""
    region = text[low:high]
    matcher = difflib.SequenceMatcher(None, region, probe, autojunk=False)
    block = matcher.find_longest_match(0, len(region), 0, len(probe))
    if block.size == 0:
        return None
    start = max(0, low + block.a - block.b)
    return ratio(text[start : start + len(probe)], probe), start


def _passage(text: str, low: int, high: int, target: str, likeness: float) -> tuple[int, int, float]:
    """The first passage ``candidates`` offers that is no worse than the window: not clearly less alike
    than ``MIN_RATIO`` or the window's likeness, or holding all of the wording but that much and no less
    than the window - then the rest of it is what the wording left out (a parenthesis: 0.78 against
    0.86). The window itself where none is."""
    floor = max(MIN_RATIO, likeness) - CLEARLY_WORSE
    whole = max(_held(likeness, high - low, target), 1 - CLEARLY_WORSE)
    for start, end in candidates(text, low, high, target, margin=TIGHTEN_MARGIN):
        score = ratio(text[start:end], target)
        if score >= floor or _held(score, end - start, target) >= whole:
            break
    return start, end, score


def _held(likeness: float, length: int, target: str) -> float:
    """How much of the wording a passage of ``length`` holds, from their ratio: twice the characters the
    two share over both lengths."""
    return likeness * (length + len(target)) / (2 * max(len(target), 1))


def ratio(text: str, target: str) -> float:
    return difflib.SequenceMatcher(None, text, target, autojunk=False).ratio()
