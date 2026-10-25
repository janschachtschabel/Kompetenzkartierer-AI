"""The word-for-word stages of checking a wording against the text of its anchor's blocks (plan M1
8.1), after the old app's search (ce_api/services/extraction/anchors.py): exact, then with each run of
whitespace counted as one, then with the gaps the wording marks ("…", "[...]") - each fragment between
them word for word, in order, close after the one before.

The text is the anchor's blocks, one line end between two (app/pipeline/anchor_check.py), not the
whole document: the old app's search from where a parent stands, and its preference for a heading line,
have nothing to do here.
"""

import re
from typing import Literal, NamedTuple

# How far apart the fragments of an elided wording may stand: a model leaves out a clause or the middle
# of a list, a few lines. Further apart, they are words of two passages, and the span would claim all
# between them (old app, measured on no live data).
ELIDED_GAP = 400

Kind = Literal["exact", "whitespace", "elided", "normalized", "fuzzy"]

# A word as wording and document are compared by: a run of letters and digits. A soft hyphen and the
# space a conversion put after it ("Fertig\xad keiten") do not part one.
_TOKEN = re.compile(r"\w+")
_SOFT_HYPHEN = re.compile("\xad\\s*")

# A mark of words left out: an ellipsis, three dots or more, alone or in brackets ("[…]", "(...)").
_OMISSION = r"[\[(]\s*(?:…|\.{3,})\s*[\])]|…|\.{3,}"
_GAP = re.compile(_OMISSION)
_CUT = re.compile(rf"^(?:{_OMISSION})|(?:{_OMISSION})$")


class Hit(NamedTuple):
    """A span of the text searched and how it was found; a fuzzy one's likeness."""

    start: int
    end: int
    kind: Kind
    score: float | None = None


def words(text: str) -> list[str]:
    """The words of ``text`` as wording and document are compared by, as they are written."""
    return _TOKEN.findall(_SOFT_HYPHEN.sub("", text))


def needle(wording: str) -> str:
    """The wording as it is looked for: without the whitespace around it, and without a mark of a gap
    at either end - "… können …" says only where the model began or stopped quoting."""
    found = wording.strip()
    while (cut := _CUT.sub("", found).strip()) != found:
        found = cut
    return found


def verbatim(target: str, text: str) -> Hit | None:
    """The first place ``text`` holds the wording as it stands, else with any run of whitespace."""
    at = text.find(target)
    if at != -1:
        return Hit(at, at + len(target), "exact")
    flexible = _flexible(target).search(text)
    if flexible:
        return Hit(flexible.start(), flexible.end(), "whitespace")
    return None


def elided(target: str, text: str) -> Hit | None:
    """The passage from the wording's first fragment to its last, where each fragment between its marks
    of a gap stands word for word (whitespace-flexible) after the one before."""
    parts = _fragments(target)
    if len(parts) < 2:
        return None
    chain = _chain(parts, text)
    return None if chain is None else Hit(*chain, "elided")


def _flexible(text: str) -> re.Pattern[str]:
    """``text`` with any run of whitespace where it has one. Built from the words: re.escape escapes a
    space too, and a whitespace pattern put into the escaped text asked for a literal backslash (the old
    app's stage was dead for that)."""
    return re.compile(r"\s+".join(re.escape(word) for word in text.split()))


def _fragments(target: str) -> list[str]:
    """The parts of the wording between its marks of a gap; a part without a letter or digit - the full
    stop of "...." - carries nothing to find."""
    return [part.strip() for part in _GAP.split(target) if re.search(r"\w", part)]


def _chain(fragments: list[str], text: str) -> tuple[int, int] | None:
    """The first place where ``fragments`` stand in order, each no more than ``ELIDED_GAP`` characters
    after the one before: where the first begins and the last ends.

    The first fragment counts where it stands last before the second: a common opening - "Die
    Schülerinnen und Schüler" - stands before every sentence, and taken where it first stood, the
    passage began a sentence early and claimed it (old app, review of package 1).
    """
    first, *rest = [_flexible(fragment) for fragment in fragments]
    for found in first.finditer(text):
        end = found.end()
        followers: list[re.Match[str]] = []
        for pattern, fragment in zip(rest, fragments[1:], strict=True):
            # twice the fragment's length: a whitespace-flexible match may run longer
            after = pattern.search(text, end, min(len(text), end + ELIDED_GAP + 2 * len(fragment)))
            if after is None or after.start() - end > ELIDED_GAP:
                break
            followers.append(after)
            end = after.end()
        else:
            start = found.start()
            for later in first.finditer(text, found.end(), followers[0].start()):
                start = later.start()
            return start, end
    return None
