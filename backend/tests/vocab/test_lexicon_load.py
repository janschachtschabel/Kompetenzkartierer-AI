"""Loading the lexicon with the vocabularies (plan M1 4.7): in the same release, nothing lost on
change, a cue the files no longer hold retired and revived when it comes back."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.db.migrate import migrate
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.vocab.model import LEXICON_CORE, PROFILE_PREFIXES, SCHOOL_PROFILE, write_model

pytestmark = pytest.mark.pg

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
VOCATIONAL = "https://w3id.org/wlo/curriculum/profile/vocational#"
REGION = "https://w3id.org/wlo/curriculum/region/"
PATTERN_CUE = """
schul:cue-lf a cur:LexicalCue ; cur:pattern "^Lernfeld\\\\s+[0-9]+" ; cur:cueRole cv:role_cue ;
    cur:cueKind cv:ck_headingPattern ; cur:mapsTo schul:dt-Lehrplan .
"""


def fetch(url: str, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


def school(root: Path, *, pattern_cue: bool = True) -> Path:
    profile = (
        SCHOOL_PROFILE
        if pattern_cue
        else SCHOOL_PROFILE.replace(PATTERN_CUE, "").replace(" , schul:cue-lf", "")
    )
    return write_model(root, LEXICON_CORE, {"schule.ttl": profile})


def two_profiles(root: Path, school_sector: str, vocational_sector: str) -> Path:
    """The school's and the vocational profile, of these sectors, with a cue each."""
    cue = "cur:cueRole cv:role_cue ; cur:cueKind cv:ck_term ; cur:mapsTo cur:Curriculum"
    profiles = (
        PROFILE_PREFIXES
        + f"""
@prefix beruf: <{VOCATIONAL}> .
schul:Terminology a cur:TerminologyProfile ; cur:profileScope cv:{school_sector} ;
    cur:hasCue schul:cue-a .
schul:cue-a a cur:LexicalCue ; cur:surfaceForm "Lehrplan" ; {cue} .
beruf:Terminology a cur:TerminologyProfile ; cur:profileScope cv:{vocational_sector} ;
    cur:hasCue beruf:cue-b .
beruf:cue-b a cur:LexicalCue ; cur:surfaceForm "Rahmenlehrplan" ; {cue} .
"""
    )
    return write_model(root, LEXICON_CORE, {"profile.ttl": profiles})


def test_the_ontology_s_profiles_and_cues_load_in_its_release(migrated: str) -> None:
    result = load_vocabulary(migrated, read_vocabulary(ONTOLOGY))

    [(profiles, cues, releases)] = fetch(
        migrated,
        "SELECT (SELECT count(*) FROM terminology_profile WHERE retired_in IS NULL),"
        " (SELECT count(*) FROM lexical_cue WHERE retired_in IS NULL),"
        " (SELECT count(*) FROM vocab_release)",
    )
    assert (profiles, cues, releases) == (5, 1267, 1)
    assert result.changed


def test_a_cue_row_keeps_what_the_files_say(migrated: str) -> None:
    load_vocabulary(migrated, read_vocabulary(ONTOLOGY))

    [row] = fetch(
        migrated,
        "SELECT profile_iri, surface_form, maps_to, scope_regions, strength, verified, occurs_in"
        " FROM lexical_cue WHERE iri = %s",
        SCHOOL + "cue-dt-kernlehrplan",
    )

    assert row == (
        SCHOOL + "Terminology",
        "Kernlehrplan",
        [SCHOOL + "dt-Lehrplan"],
        [REGION + "DE-NW"],
        Decimal("0.95"),
        False,
        ["https://w3id.org/wlo/curriculum/vocab#occ_titlePage"],
    )


def test_a_second_load_of_the_same_files_changes_nothing(migrated: str) -> None:
    vocabulary = read_vocabulary(ONTOLOGY)
    load_vocabulary(migrated, vocabulary)

    again = load_vocabulary(migrated, vocabulary)

    assert not again.changed
    assert fetch(migrated, "SELECT count(*) FROM lexical_cue WHERE retired_in IS NULL") == [(1267,)]


def test_a_cue_the_files_drop_is_retired_by_their_release_and_revived_when_it_returns(
    migrated: str, tmp_path: Path
) -> None:
    load_vocabulary(migrated, read_vocabulary(school(tmp_path / "1")))
    dropped = load_vocabulary(migrated, read_vocabulary(school(tmp_path / "2", pattern_cue=False)))

    retired = fetch(migrated, "SELECT iri, retired_in FROM lexical_cue ORDER BY iri")
    load_vocabulary(migrated, read_vocabulary(school(tmp_path / "3")))
    back = fetch(migrated, "SELECT iri, retired_in FROM lexical_cue ORDER BY iri")

    assert retired == [(SCHOOL + "cue-klp", None), (SCHOOL + "cue-lf", dropped.release_id)]
    assert back == [(SCHOOL + "cue-klp", None), (SCHOOL + "cue-lf", None)]


def test_a_profile_the_files_drop_is_retired_with_its_cues(migrated: str, tmp_path: Path) -> None:
    load_vocabulary(migrated, read_vocabulary(school(tmp_path / "1")))
    dropped = load_vocabulary(migrated, read_vocabulary(write_model(tmp_path / "2", LEXICON_CORE)))

    profiles = fetch(migrated, "SELECT iri, retired_in FROM terminology_profile")
    cues = fetch(migrated, "SELECT DISTINCT retired_in FROM lexical_cue")

    assert profiles == [(SCHOOL + "Terminology", dropped.release_id)]
    assert cues == [(dropped.release_id,)]


def test_two_profiles_swap_their_sectors(migrated: str, tmp_path: Path) -> None:
    # one active profile for each sector, checked row by row: as for a notation, a swap would
    # meet the other profile still active in its old sector
    load_vocabulary(migrated, read_vocabulary(two_profiles(tmp_path / "1", "sec_school", "sec_vocational")))

    load_vocabulary(migrated, read_vocabulary(two_profiles(tmp_path / "2", "sec_vocational", "sec_school")))

    assert fetch(migrated, "SELECT iri, sector_iri, retired_in FROM terminology_profile ORDER BY iri") == [
        (SCHOOL + "Terminology", CV + "sec_vocational", None),
        (VOCATIONAL + "Terminology", CV + "sec_school", None),
    ]
