"""The lexicon's patterns as a stage searches them (plan M1 6.3): with their time limit, a pattern
that takes too long finding nothing - here and in every later text, so it costs its limit once -
and noted by its cue, for the stage's finding, rather than failing the stage."""

from app.domain.lexicon import Cue, PatternTimeout, pattern_matches


class PatternSearch:
    def __init__(self) -> None:
        self.timeouts: set[str] = set()  # the cues whose pattern took too long

    def found(self, cue: Cue, text: str) -> bool:
        """Whether the cue's pattern finds a match in ``text``; never where it has none."""
        if cue.pattern is None or cue.iri in self.timeouts:
            return False
        try:
            return pattern_matches(cue.pattern, text)
        except PatternTimeout:
            self.timeouts.add(cue.iri)
            return False
