"""A document's active profile: the cues that hold for it, the more specific before the general
(konzept §12.2, §12.4, plan M1 4.8), and patterns searched with a time limit."""

from pathlib import Path
from typing import Any

import pytest

from app.domain.lexicon import Cue, PatternTimeout, active_cues, pattern_matches
from app.vocab.loader import read_vocabulary

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
REGION = "https://w3id.org/wlo/curriculum/region/"
NW = frozenset({REGION + "DE-NW", REGION + "DE"})  # a region with those it lies in
CUE = "https://w3id.org/wlo/curriculum/vocab#role_cue"
PREF = "https://w3id.org/wlo/curriculum/vocab#role_pref"
NEGATIVE = "https://w3id.org/wlo/curriculum/vocab#role_negative"
HOMONYM = "https://w3id.org/wlo/curriculum/vocab#role_homonym"
TERM = "https://w3id.org/wlo/curriculum/vocab#ck_term"


def cue(name: str, *, form: str | None = "Kernlehrplan", target: str = "dt-Lehrplan", **changes: Any) -> Cue:
    values: dict[str, Any] = {
        "iri": f"https://example.org/cue/{name}",
        "role": CUE,
        "kind": TERM,
        "maps_to": (target,),
        "surface_form": form,
    } | changes
    return Cue(**values)


def active(
    cues: list[Cue], regions: frozenset[str] = NW, document_type: str | None = None, plan: str | None = None
) -> dict[str, bool]:
    return {
        found.cue.iri.rsplit("/", 1)[-1]: found.tie
        for found in active_cues(cues, regions, document_type, plan)
    }


def test_a_cue_without_a_scope_holds_everywhere_and_a_scoped_one_where_its_scope_does() -> None:
    cues = [
        cue("everywhere", form="Lehrplan"),
        cue("nw", form="Kernlehrplan", scope_regions=frozenset({REGION + "DE-NW"})),
        cue("by", form="LehrplanPLUS", scope_regions=frozenset({REGION + "DE-BY"})),
        cue("germany", form="Bildungsstandards", scope_regions=frozenset({REGION + "DE"})),
        cue("typed", form="Fachlehrplan", scope_document_types=frozenset({"dt-Lehrplan"})),
        cue("generation", form="Bildungsplan", plan_generations=frozenset({"BP2016"})),
    ]

    assert set(active(cues, document_type="dt-Lehrplan", plan="BP2016")) == {
        "everywhere",
        "nw",
        "germany",
        "typed",
        "generation",
    }
    assert set(active(cues, document_type="dt-Rahmenplan", plan="BP2004")) == {"everywhere", "nw", "germany"}
    assert set(active(cues, regions=frozenset(), document_type="dt-Rahmenplan", plan="BP2004")) == {
        "everywhere"
    }


def test_a_cue_of_a_document_type_or_plan_generation_holds_where_the_document_s_is_unknown() -> None:
    # X1 is to tell the plan generation by such cues (Bavaria's "LehrplanPLUS"): none can carry
    # one before, and a document's type may stay unknown
    cues = [
        cue("typed", form="Fachlehrplan", scope_document_types=frozenset({"dt-Lehrplan"})),
        cue("generation", form="LehrplanPLUS", plan_generations=frozenset({"LehrplanPLUS"})),
    ]

    assert active(cues) == {"typed": False, "generation": False}


@pytest.mark.parametrize(
    ("plan", "winner"),
    [(None, "unscoped"), ("BP2016", "generation")],
    ids=["unknown-no-bonus", "known-and-matching-ranks"],
)
def test_a_scope_ranks_a_cue_only_where_it_matches_the_document_s(plan: str | None, winner: str) -> None:
    cues = [
        cue("unscoped", target="dt-Lehrplan", strength=0.8),
        cue("generation", target="dt-Rahmenplan", strength=0.6, plan_generations=frozenset({"BP2016"})),
    ]

    assert active(cues, plan=plan) == {winner: False}


@pytest.mark.parametrize(
    ("first", "second", "winner"),
    [
        (
            {"strength": 0.9, "verified": True},
            {"strength": 0.6, "scope_regions": frozenset({REGION + "DE-NW"})},
            "second",
        ),  # the more specific, however weak
        (
            {"strength": 0.9, "scope_regions": frozenset({REGION + "DE-NW"})},
            {"strength": 0.6, "verified": True, "scope_regions": frozenset({REGION + "DE-NW"})},
            "second",
        ),  # checked before unchecked
        ({"strength": 0.6}, {"strength": 0.8}, "second"),  # then the stronger
        ({"strength": None}, {"strength": 0.1}, "second"),  # no strength is none
    ],
    ids=["specific", "verified", "strength", "no-strength"],
)
def test_of_cues_on_one_word_for_other_targets_the_first_by_rank_holds(
    first: dict[str, Any], second: dict[str, Any], winner: str
) -> None:
    cues = [cue("first", target="dt-Lehrplan", **first), cue("second", target="dt-Rahmenplan", **second)]

    assert active(cues) == {winner: False}


def test_cues_on_one_word_that_rank_alike_both_hold_as_a_tie_for_another_target() -> None:
    cues = [
        cue("lehrplan", target="dt-Lehrplan", strength=0.8),
        cue("rahmenplan", form="KERNLEHRPLAN", target="dt-Rahmenplan", strength=0.8),
        cue("again", target="dt-Lehrplan", strength=0.8, form="Lehrplan"),
        cue("same", target="dt-Lehrplan", strength=0.8, form="Lehrplan"),
    ]

    assert active(cues) == {"lehrplan": True, "rahmenplan": True, "again": False, "same": False}


def test_a_negative_cue_holds_beside_a_stronger_one_on_its_word() -> None:
    cues = [cue("plan", strength=0.95), cue("not", role=NEGATIVE, strength=0.5, target="dt-Rahmenplan")]

    assert active(cues) == {"plan": False, "not": False}


def test_a_homonym_holds_with_its_other_target() -> None:
    homonym = cue("homonym", also_maps_to=("dt-Rahmenplan",))

    [found] = active_cues([homonym], NW, None, None)

    assert found.cue.also_maps_to == ("dt-Rahmenplan",)


def test_a_homonym_holds_beside_a_stronger_cue_on_its_word() -> None:
    # "Verwendbarkeit des Moduls": a checked homonym beside a stronger preferred term
    cues = [
        cue("pref", role=PREF, strength=0.9, verified=True, target="cur:Placement"),
        cue("homonym", role=HOMONYM, strength=0.5, also_maps_to=("dt-Rahmenplan",)),
        cue("weaker", role=PREF, strength=0.3, target="dt-Rahmenplan"),
    ]

    assert active(cues) == {"pref": False, "homonym": False}


def test_cues_of_a_pattern_and_a_word_alike_do_not_compete() -> None:
    cues = [
        cue("word", form="Lernfeld", strength=0.9),
        cue("pattern", form=None, pattern="Lernfeld", strength=0.5),
    ]

    assert active(cues) == {"word": False, "pattern": False}


def test_a_pattern_is_searched_in_a_text() -> None:
    assert pattern_matches(r"^Lernfeld\s+[0-9]+", "Lernfeld 5: Kunden beraten")
    assert not pattern_matches(r"^Lernfeld\s+[0-9]+", "Das Lernfeld 5")


def test_a_pattern_that_takes_too_long_is_stopped() -> None:
    # regex optimises the classic ones away; this one takes it more than 5 s on 1000 signs
    with pytest.raises(PatternTimeout):
        pattern_matches(r"(x+x+)+y", "x" * 1000, timeout=0.01)


def test_the_lexicon_s_patterns_find_their_positive_examples_and_none_of_their_negative_ones() -> None:
    cues = [found for found in read_vocabulary(ONTOLOGY).cues.values() if found.pattern is not None]

    misses = [
        (found.iri, example)
        for found in cues
        for example in found.positive_examples
        if found.pattern is not None and not pattern_matches(found.pattern, example)
    ]
    hits = [
        (found.iri, example)
        for found in cues
        for example in found.negative_examples
        if found.pattern is not None and pattern_matches(found.pattern, example)
    ]

    assert len(cues) == 86
    assert (misses, hits) == ([], [])
