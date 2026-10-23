"""Reading the lexicon - each sector's terminology profile and its cues - with the vocabularies
(plan M1 4.7, konzept §12.1), without a database."""

from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.vocab.lexicon import LexicalCue, TerminologyProfile
from app.vocab.loader import VocabularyError, read_vocabulary
from tests.vocab.model import LEXICON_CORE as CORE
from tests.vocab.model import PROFILE_PREFIXES as PREFIXES
from tests.vocab.model import SCHOOL_PROFILE, write_model

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
CUR = "https://w3id.org/wlo/curriculum/core#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
LAND = "https://w3id.org/wlo/curriculum/region/"


def read(root: Path, profiles: dict[str, str]) -> tuple[dict[str, TerminologyProfile], dict[str, LexicalCue]]:
    vocabulary = read_vocabulary(write_model(root, CORE, profiles))
    return vocabulary.profiles, vocabulary.cues


def test_a_profile_is_read_with_its_sector_namespace_and_labels(tmp_path: Path) -> None:
    profiles, _ = read(tmp_path, {"schule.ttl": SCHOOL_PROFILE})

    assert profiles == {
        SCHOOL + "Terminology": TerminologyProfile(
            iri=SCHOOL + "Terminology",
            namespace=SCHOOL,
            sector=CV + "sec_school",
            labels={"de": "Terminologie Schule"},
        )
    }


def test_a_cue_is_read_with_every_field_konzept_names_and_the_rest_as_properties(tmp_path: Path) -> None:
    _, cues = read(tmp_path, {"schule.ttl": SCHOOL_PROFILE})

    assert cues[SCHOOL + "cue-klp"] == LexicalCue(
        iri=SCHOOL + "cue-klp",
        profile=SCHOOL + "Terminology",
        surface_form="Kernlehrplan",
        pattern=None,
        layout_signal=None,
        role=CV + "role_homonym",
        kind=CV + "ck_term",
        maps_to=[CUR + "Curriculum", SCHOOL + "dt-Kernlehrplan"],
        also_maps_to=[SCHOOL + "dt-Lehrplan"],
        occurs_in=[CV + "occ_titlePage"],
        scope_regions=[LAND + "DE", LAND + "DE-NW"],
        scope_document_types=[SCHOOL + "dt-Lehrplan"],
        scope_institution_types=[],
        scope_subjects=[],
        scope_issuers=["MSB NRW"],
        plan_generations=["G9"],
        valid_from="2023-08-01",
        valid_until=None,
        strength=Decimal("0.9"),
        verified=True,
        recognition_hints={"de": ["NRW: Kernlehrplan der Sekundarstufe I."]},
        negative_hints={"de": ["Nicht der KMK-Plan."]},
        positive_examples=["Kernlehrplan Mathematik"],
        negative_examples=["Lehrplan"],
        properties={"http://www.w3.org/ns/prov#wasDerivedFrom": [{"iri": "https://example.org/quelle"}]},
    )


def test_a_cue_unsaid_verified_is_unchecked_and_without_strength_has_none(tmp_path: Path) -> None:
    _, cues = read(tmp_path, {"schule.ttl": SCHOOL_PROFILE})

    cue = cues[SCHOOL + "cue-lf"]
    assert (cue.pattern, cue.verified, cue.strength) == (r"^Lernfeld\s+[0-9]+", False, None)


def test_a_country_s_cues_in_a_folder_of_the_profiles_are_read_too(tmp_path: Path) -> None:
    country = (
        PREFIXES
        + """
schul:Terminology cur:hasCue schul:cue-nw .
schul:cue-nw a cur:LexicalCue ; cur:surfaceForm "Kernlehrplan" ; cur:cueRole cv:role_cue ;
    cur:cueKind cv:ck_term ; cur:mapsTo schul:dt-Kernlehrplan ; cur:scopeRegion land:DE-NW .
"""
    )
    vocabulary = read_vocabulary(
        write_model(tmp_path, CORE, {"schule.ttl": SCHOOL_PROFILE, "laender/schule-DE-NW.ttl": country})
    )

    assert vocabulary.cues[SCHOOL + "cue-nw"].profile == SCHOOL + "Terminology"
    assert "profile/laender/schule-DE-NW.ttl" in vocabulary.files


def with_cue(cue: str, *, listed: bool = True) -> str:
    listing = "schul:Terminology cur:hasCue schul:cue-x ." if listed else ""
    return SCHOOL_PROFILE + "\n" + listing + "\nschul:cue-x a cur:LexicalCue ; " + cue + " .\n"


BASE = "cur:cueRole cv:role_cue ; cur:cueKind cv:ck_term ; cur:mapsTo schul:dt-Lehrplan"
KIND_AS_ROLE = 'cur:surfaceForm "Plan" ; cur:cueRole cv:ck_term ; cur:cueKind cv:ck_term ; cur:mapsTo schul:x'


@pytest.mark.parametrize(
    ("profile", "fault"),
    [
        (with_cue('cur:surfaceForm "Plan" ; ' + BASE, listed=False), "in no profile"),
        (
            with_cue('cur:surfaceForm "Plan" ; ' + BASE)
            + "schul:Other a cur:TerminologyProfile ; cur:profileScope cv:sec_school ;"
            + " cur:hasCue schul:cue-x .",
            "more than one profile",
        ),
        (SCHOOL_PROFILE + "schul:Terminology cur:hasCue schul:nothing .", "no cue"),
        (with_cue(BASE), "no form"),
        (with_cue('cur:surfaceForm "Plan" ; cur:pattern "(unclosed" ; ' + BASE), "pattern"),
        (with_cue("cur:surfaceForm schul:dt-Lehrplan ; " + BASE), "text belongs"),
        (with_cue('cur:surfaceForm "Plan" , "Lehrplan" ; ' + BASE), "more than one"),
        (with_cue('cur:surfaceForm "Plan" ; cur:cueKind cv:ck_term ; cur:mapsTo schul:dt-Lehrplan'), "role"),
        (
            with_cue(KIND_AS_ROLE),
            "role",
        ),
        (with_cue('cur:surfaceForm "Plan" ; cur:cueRole cv:role_cue ; cur:cueKind cv:ck_term'), "target"),
        (with_cue('cur:surfaceForm "Plan" ; ' + BASE + " , schul:nowhere"), "nowhere"),
        (with_cue('cur:surfaceForm "Plan" ; cur:mapsTo "Lehrplan" ; ' + BASE), "IRI"),
        (with_cue('cur:surfaceForm "Plan" ; cur:strength "stark" ; ' + BASE), "strength"),
        (with_cue('cur:surfaceForm "Plan" ; cur:validFrom "ab 2023" ; ' + BASE), "date"),
    ],
    ids=[
        "in-no-profile",
        "in-two-profiles",
        "listed-but-no-cue",
        "no-form",
        "bad-pattern",
        "form-as-iri",
        "two-forms",
        "no-role",
        "role-of-another-scheme",
        "no-target",
        "target-not-in-the-model",
        "target-as-text",
        "strength-as-text",
        "date-as-prose",
    ],
)
def test_a_cue_the_tables_cannot_hold_as_it_is_is_refused(tmp_path: Path, profile: str, fault: str) -> None:
    with pytest.raises(VocabularyError, match=fault):
        read(tmp_path, {"schule.ttl": profile})


@pytest.mark.parametrize(
    ("scope", "fault"),
    [
        ("", "sector"),
        ("cur:profileScope cv:sec_school , cv:role_cue ;", "sector"),
        ("cur:profileScope cv:role_cue ;", "education sector"),
    ],
    ids=["no-sector", "two-sectors", "not-a-sector"],
)
def test_a_profile_names_one_education_sector(tmp_path: Path, scope: str, fault: str) -> None:
    profile = SCHOOL_PROFILE.replace("cur:profileScope cv:sec_school ;", scope)

    with pytest.raises(VocabularyError, match=fault):
        read(tmp_path, {"schule.ttl": profile})


def test_the_ontology_s_lexicon_holds_five_profiles_and_their_1267_cues() -> None:
    vocabulary = read_vocabulary(ONTOLOGY)

    by_profile = Counter(cue.profile.split("#")[0].rsplit("/", 1)[-1] for cue in vocabulary.cues.values())
    sectors = sorted(profile.sector.removeprefix(CV) for profile in vocabulary.profiles.values())
    assert sectors == ["sec_adult", "sec_elementary", "sec_higher", "sec_school", "sec_vocational"]
    assert len(vocabulary.cues) == 1267
    assert by_profile == {
        "school": 487,
        "early-childhood": 273,
        "vocational": 55,
        "higher-education": 416,
        "adult-education": 36,
    }
    assert sum(cue.pattern is not None for cue in vocabulary.cues.values()) == 86
