"""The lexicon's tables (migration lexicon, plan M1 4.7): a profile for each sector, cues that
name a form and a target, their role and kind from the core's schemes."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from app.db.migrate import migrate

pytestmark = pytest.mark.pg

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
CONCEPTS = {
    "EducationSectors": ["sec_school", "sec_vocational"],
    "CueRoles": ["role_cue"],
    "CueKinds": ["ck_term"],
    "Stages": ["stage_X1"],  # a concept of another scheme
}


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        for scheme, concepts in CONCEPTS.items():
            opened.execute(
                "INSERT INTO vocab_scheme (iri, types, pref_labels, properties)"
                " VALUES (%s, '{}', '{}', '{}')",
                (CV + scheme,),
            )
            for concept in concepts:
                opened.execute(
                    "INSERT INTO vocab_concept (iri, scheme_iri, types, pref_labels, alt_labels, definitions,"
                    " broader, properties) VALUES (%s, %s, '{}', '{}', '{}', '{}', '{}', '{}')",
                    (CV + concept, CV + scheme),
                )
        opened.execute("INSERT INTO vocab_release (content_hash, files) VALUES (%s, '{}')", ("0" * 64,))
        yield opened


def add_profile(connection: psycopg.Connection, iri: str = SCHOOL + "Terminology", **columns: Any) -> None:
    values = {"namespace": SCHOOL, "sector_scheme": CV + "EducationSectors", "sector_iri": CV + "sec_school"}
    values |= columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO terminology_profile (iri, {names}) VALUES (%s, {marks})",  # noqa: S608 - the test's names
        (iri, *values.values()),
    )


def add_cue(connection: psycopg.Connection, iri: str = SCHOOL + "cue-1", **columns: Any) -> None:
    values = {
        "profile_iri": SCHOOL + "Terminology",
        "surface_form": "Kernlehrplan",
        "role_scheme": CV + "CueRoles",
        "role_iri": CV + "role_cue",
        "kind_scheme": CV + "CueKinds",
        "kind_iri": CV + "ck_term",
        "maps_to": [SCHOOL + "dt-Lehrplan"],
    }
    values |= columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO lexical_cue (iri, {names}) VALUES (%s, {marks})",  # noqa: S608 - the test's names
        (iri, *values.values()),
    )


def test_a_cue_of_a_profile_is_stored_with_its_defaults(connection: psycopg.Connection) -> None:
    add_profile(connection)
    add_cue(connection)

    row = connection.execute(
        "SELECT verified, also_maps_to, scope_regions, properties, retired_in FROM lexical_cue"
    ).fetchone()

    assert row == (False, [], [], {}, None)


def test_a_sector_has_one_active_profile_and_a_retired_one_beside_it(connection: psycopg.Connection) -> None:
    add_profile(connection)
    connection.execute("UPDATE terminology_profile SET retired_in = 1")
    add_profile(connection, SCHOOL + "Terminology2")

    with pytest.raises(errors.UniqueViolation):
        add_profile(connection, SCHOOL + "Terminology3")


@pytest.mark.parametrize(
    ("iri", "columns"),
    [
        (SCHOOL + "Terminology", {"namespace": "https://w3id.org/wlo/curriculum/profile/vocational#"}),
        (SCHOOL + "Terminology", {"namespace": "https://w3id.org/wlo/curriculum/profile/school"}),
        (SCHOOL, {}),  # the namespace alone names no profile
    ],
    ids=["outside-its-namespace", "namespace-not-ending-a-path", "no-name-of-its-own"],
)
def test_a_profile_is_named_within_its_namespace(
    connection: psycopg.Connection, iri: str, columns: dict[str, str]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_profile(connection, iri, **columns)


def test_a_profile_s_sector_is_an_education_sector(connection: psycopg.Connection) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        add_profile(connection, sector_iri=CV + "stage_X1")


@pytest.mark.parametrize(
    "columns",
    [
        {"surface_form": None},  # no form at all
        {"maps_to": []},
        {"strength": 1.5},
        {"valid_from": "1. August 2023"},
        {"valid_until": "2023-8-1"},
        {"recognition_hints": Jsonb(["a hint"])},  # by language, an object
    ],
    ids=["no-form", "no-target", "strength", "valid-from", "valid-until", "hints"],
)
def test_a_cue_names_a_form_and_a_target_and_values_in_range(
    connection: psycopg.Connection, columns: dict[str, Any]
) -> None:
    add_profile(connection)

    with pytest.raises(errors.CheckViolation):
        add_cue(connection, **columns)


@pytest.mark.parametrize("form", ["pattern", "layout_signal"])
def test_a_cue_of_a_pattern_or_a_layout_signal_alone_is_one(
    connection: psycopg.Connection, form: str
) -> None:
    add_profile(connection)

    add_cue(connection, surface_form=None, **{form: "^Lernfeld [0-9]+"})

    assert connection.execute("SELECT count(*) FROM lexical_cue").fetchone() == (1,)


@pytest.mark.parametrize(("column", "iri"), [("role_iri", "stage_X1"), ("kind_iri", "role_cue")])
def test_a_cue_s_role_and_kind_come_from_their_schemes(
    connection: psycopg.Connection, column: str, iri: str
) -> None:
    add_profile(connection)

    with pytest.raises(errors.ForeignKeyViolation):
        add_cue(connection, **{column: CV + iri})


def test_a_cue_belongs_to_a_profile(connection: psycopg.Connection) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        add_cue(connection)
