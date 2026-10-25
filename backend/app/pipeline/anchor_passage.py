"""Where a fuzzy match's passage begins and ends (plan M1 8.1), after the old app's
ce_api/services/extraction/anchor_passage.py.

The fuzzy search (app/pipeline/anchor_fuzzy.py) scores a window as long as the wording, aligned on the
longest stretch the two share. Scored, that is fair; as the document's wording at the anchor - the
anchor's quote - it is not (old app, audit 2026-10-03 F01). This narrows the window to the stretches the
wording's words match and widens it to whole words, and offers the alternatives too, the window last,
for the search to take the first that is no worse than the window (``candidates``).

The text is the anchor's blocks, one line end between two: a line break ends a word, and the old app's
moves off a markdown heading line have no heading to move off.
"""

import difflib
import re
from collections.abc import Iterator
from typing import NamedTuple

# How far past the passage the wording's last words may stand: what the wording left out before them -
# a parenthesis, a clause - as far as the gap of an elided wording may run (old app, live replay
# 2026-10-04: windows ending inside a parenthesis scored 0.73 and 0.79).
TAIL_REACH = 400

# The end of a sentence: its mark, perhaps a closing quotation mark or bracket, and the space after it.
# Not the full stop of a number or a single letter: "1." numbers a list, "z. B." abbreviates.
_SENTENCE_END = re.compile(r"(?<!\d)(?<!\b\w)[.!?][\"'“”»)\]]*\s")


class _Shared(NamedTuple):
    """A stretch wording and text share: where it stands in each."""

    start: int
    end: int
    wording_start: int
    wording_end: int


def candidates(text: str, low: int, high: int, target: str, *, margin: int) -> Iterator[tuple[int, int]]:
    """The passages ``text[low:high]`` - give or take ``margin`` - may stand for, best first.

    First the window tightened to the stretches of one sentence that the wording's words match, widened
    to whole words and to the document's words where the wording's first or last words differ; then the
    same over every stretch; last the window itself on whole words: a tightening can go wrong, and the
    window the search accepted is then the better passage (a numbered list read as sentences kept one
    item of five, 0.42).
    """
    shared = _shared(text, low, high, target, margin)
    if shared:
        kept = _one_passage(text, target, shared)
        yield _span(text, target, kept)
        if shared != kept:
            yield _span(text, target, shared)
    yield _whole_words(text, low, high)


def _shared(text: str, low: int, high: int, target: str, margin: int) -> list[_Shared]:
    begin = max(0, low - margin)
    region = text[begin : min(len(text), high + margin)]
    matcher = difflib.SequenceMatcher(None, region, target, autojunk=False)
    return [
        _Shared(begin + block.a, begin + block.a + block.size, block.b, block.b + block.size)
        for block in matcher.get_matching_blocks()
        if _says_something(region[block.a : block.a + block.size])
    ]


def _span(text: str, target: str, shared: list[_Shared]) -> tuple[int, int]:
    """From the first to the last of ``shared``, on whole words. A word the wording replaced at either
    end is the very difference a reader has to see - the operator last in a German sentence, the number
    a reference ends on - so the document's word there is taken in; where the wording's last words stand
    further on, past what it left out, the passage runs on to them."""
    first, last = shared[0], shared[-1]
    start, end = _whole_words(text, first.start, last.end)
    start = _words_before(
        text, start, _edge_words(target[: first.wording_start], target[first.wording_start :])
    )
    further = _last_words_after(text, end, _rest_of(target, last.wording_end))
    if further is not None:
        end = further
    else:
        end = _words_after(
            text, end, _edge_words(target[last.wording_end :][::-1], target[: last.wording_end][::-1])
        )
    # the wording's closing mark, where the document closes the passage with it
    if target[-1] in ".,;:!?)" and text[end : end + 1] == target[-1]:
        end += 1
    return start, end


def _rest_of(target: str, at: int) -> str:
    """The wording after its last stretch, without the rest of a word the stretch cut."""
    rest = target[at:]
    return re.sub(r"^\w+", "", rest) if target[at - 1 : at].isalnum() else rest


def _last_words_after(text: str, end: int, rest: str) -> int | None:
    """Where the wording's last words end, if they stand on after ``end``: the longest run of them, two
    words at least, word for word (whitespace-flexible) within ``TAIL_REACH`` characters and in the same
    sentence. None where they do not."""
    tokens = rest.split()
    if tokens:
        tokens[0] = re.sub(r"^\W+", "", tokens[0])
        tokens[-1] = re.sub(r"\W+$", "", tokens[-1])
    tokens = [token for token in tokens if token]
    reach = min(len(text), end + TAIL_REACH + 2 * len(rest))
    for first in range(len(tokens) - 1):
        found = re.compile(r"\s+".join(re.escape(token) for token in tokens[first:])).search(text, end, reach)
        if found is None or found.start() - end > TAIL_REACH:
            continue
        if _SENTENCE_END.search(text[end : found.start()] + " ") is None:
            return found.end()
    return None


def _says_something(stretch: str) -> bool:
    """Whether a shared stretch is more than chance: four characters and more, three letters or digits
    of them in a row. "e", "en " or "be" are shared by any two German sentences."""
    return len(stretch) >= 4 and re.search(r"\w{3}", stretch) is not None


def _one_passage(text: str, target: str, shared: list[_Shared]) -> list[_Shared]:
    """``shared`` without the stretches beyond the end of a sentence the document has between two
    stretches and the wording has not; the longest stretch decides which sentence is the passage."""
    core = max(range(len(shared)), key=lambda index: shared[index].end - shared[index].start)
    first = last = core
    while first > 0 and not _parted(text, target, shared[first - 1], shared[first]):
        first -= 1
    while last < len(shared) - 1 and not _parted(text, target, shared[last], shared[last + 1]):
        last += 1
    return shared[first : last + 1]


def _parted(text: str, target: str, before: _Shared, after: _Shared) -> bool:
    """Whether a sentence ends between two stretches in the document and not in the wording; one
    character more of each, for the space after a mark."""
    in_document = _SENTENCE_END.search(text[before.end : after.start + 1])
    return (
        in_document is not None
        and _SENTENCE_END.search(target[before.wording_end : after.wording_start + 1]) is None
    )


def _edge_words(unmatched: str, matched: str) -> int:
    """How many whole words the wording has at one end beyond its stretches, ``unmatched`` read from the
    outside in; a word the stretch cut ("beurteil|en") is not one."""
    count = len(re.findall(r"\w+", unmatched))
    cut = unmatched[-1:].isalnum() and matched[:1].isalnum()
    return count - 1 if cut else count


def _words_before(text: str, start: int, count: int) -> int:
    """``start`` moved back over up to ``count`` more words of its line, not past a sentence's end."""
    line = text.rfind("\n", 0, start) + 1
    for _ in range(count):
        word_end = start
        while word_end > line and not text[word_end - 1].isalnum():
            word_end -= 1
        if word_end == line or re.search(r"[.!?]", text[word_end:start]):
            break
        while word_end > line and text[word_end - 1].isalnum():
            word_end -= 1
        start = word_end
    return start


def _words_after(text: str, end: int, count: int) -> int:
    """``end`` moved on over up to ``count`` more words of its line, not past a sentence's end - nor at
    all where the passage ends one."""
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    for _ in range(count):
        if text[end - 1 : end] in (".", "!", "?"):
            break
        word_start = end
        while word_start < line_end and not text[word_start].isalnum():
            word_start += 1
        if word_start == line_end or re.search(r"[.!?]", text[end:word_start]):
            break
        while word_start < line_end and text[word_start].isalnum():
            word_start += 1
        end = word_start
    return end


def _whole_words(text: str, start: int, end: int) -> tuple[int, int]:
    """``text[start:end]`` without whitespace at either end, widened so that it cuts no word; never
    across a line: a line break ends a word."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    while 0 < start < end and text[start - 1].isalnum() and text[start].isalnum():
        start -= 1
    while start < end < len(text) and text[end - 1].isalnum() and text[end].isalnum():
        end += 1
    return start, end
