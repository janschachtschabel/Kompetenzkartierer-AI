"""The lexicon excerpt a request about a unit carries in its task (plan M1 7b, F6; konzept §12.2): of
the document's active cues, the words and sentence patterns that point to a target the task names and
bear on the unit's text - a word in it, in any case, a pattern matching one of its blocks - with
their rule texts, the checked and stronger first, at most MOST_LINES of them."""

from app.domain.lexicon import HOMONYM, NEGATIVE, ActiveCue, Cue
from app.pipeline.lexicon_excerpt import MOST_LINES, lexicon_excerpt

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
TERM, SENTENCE, HEADING = CV + "ck_term", CV + "ck_sentencePattern", CV + "ck_headingPattern"
EXPECTATION, CROSS = SCHOOL + "Kompetenzerwartung", SCHOOL + "Querschnittsbereich"
NAMES = {EXPECTATION: "Kompetenzerwartung (U1)", CROSS: "Querschnittsbereich (U2)"}
TEXTS = ["Die Schülerinnen und Schüler beschreiben Licht.", "Leitperspektive BNE"]


def cue(name: str, kind: str = TERM, maps_to: str = EXPECTATION, **given: object) -> ActiveCue:
    values: dict[str, object] = {
        "iri": SCHOOL + name,
        "role": CV + "role_cue",
        "kind": kind,
        "maps_to": (maps_to,),
    }
    return ActiveCue(Cue(**(values | given)), tie=False)  # type: ignore[arg-type]


def test_a_word_in_the_unit_s_text_in_any_case_and_a_pattern_matching_a_block_are_listed() -> None:
    cues = [
        cue("leitperspektive", maps_to=CROSS, surface_form="LEITPERSPEKTIVE"),
        cue(
            "satzstamm",
            kind=SENTENCE,
            pattern=r"^(Die )?(Schülerinnen und Schüler|Lernenden)\b",
            recognition_hints=("Satzstamm als leadIn speichern.",),
        ),
        cue("basiscurriculum", maps_to=CROSS, surface_form="Basiscurriculum"),
        cue("kann", kind=SENTENCE, pattern=r"^Kann\b"),
    ]

    excerpt = lexicon_excerpt(cues, TEXTS, NAMES)

    assert excerpt.text.splitlines() == [
        "„LEITPERSPEKTIVE“ → Querschnittsbereich (U2)",
        "Satzmuster /^(Die )?(Schülerinnen und Schüler|Lernenden)\\b/ → Kompetenzerwartung (U1)"
        " — Satzstamm als leadIn speichern.",
    ]
    assert excerpt.timeouts == frozenset()


def test_cues_of_other_kinds_of_no_named_target_or_saying_what_a_word_is_not_are_left_out() -> None:
    cues = [
        cue("ueberschrift", kind=HEADING, pattern="Leitperspektive"),
        cue("fremd", maps_to=SCHOOL + "Inhaltsbereich", surface_form="Licht"),
        cue("nicht", role=NEGATIVE, surface_form="Licht"),
    ]

    assert lexicon_excerpt(cues, TEXTS, NAMES).text == ""


def test_a_homonym_names_its_other_reading() -> None:
    cues = [cue("licht", role=HOMONYM, surface_form="Licht", also_maps_to=(CROSS,))]

    assert lexicon_excerpt(cues, TEXTS, NAMES).text == (
        "„Licht“ → Kompetenzerwartung (U1), sonst Querschnittsbereich (U2) (je nach Zusammenhang)"
    )


def test_the_checked_and_stronger_come_first_up_to_most_lines_each_once() -> None:
    words = [f"Wort{number:03}" for number in range(MOST_LINES + 5)]
    cues = [cue(word, surface_form=word, strength=0.5) for word in words]
    cues += [
        cue("stark", surface_form=words[-1], strength=0.9),
        cue("geprueft", surface_form="Wort001", verified=True),
    ]

    lines = lexicon_excerpt(cues, [" ".join(words)], NAMES).text.splitlines()

    assert len(lines) == MOST_LINES
    assert lines[:3] == [
        "„Wort001“ → Kompetenzerwartung (U1)",
        f"„{words[-1]}“ → Kompetenzerwartung (U1)",
        "„Wort000“ → Kompetenzerwartung (U1)",
    ]


def test_a_pattern_that_takes_too_long_is_noted_and_lists_nothing() -> None:
    # 0.2 s on 190 signs, four times the limit (tests/pipeline/test_skeleton.py)
    slow = cue("langsam", kind=SENTENCE, pattern=r"(x+x+x+x+)+y")

    excerpt = lexicon_excerpt([slow], ["x" * 190], NAMES)

    assert (excerpt.text, excerpt.timeouts) == ("", frozenset({SCHOOL + "langsam"}))
