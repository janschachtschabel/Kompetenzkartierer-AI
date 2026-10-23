"""Looking up the vocabularies (plan M1 4.1): a concept, a notation, a profile's values, a region
and those it lies in; retired concepts are read, never chosen."""

from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest

from app.db.migrate import migrate
from app.domain.lexicon import active_cues
from app.vocab.loader import read_vocabulary
from app.vocab.lookup import by_notation, concept, cues_for, profile_concepts, region_with_ancestors
from app.vocab.store import load_vocabulary

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
REGION = "https://w3id.org/wlo/curriculum/region/"


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


@pytest.mark.parametrize(
    ("sector", "counts"),
    [
        ("school", (10, 13, 8)),
        ("elementary", (16, 11, 9)),
        ("vocational", (25, 10, 17)),
        ("higher", (13, 6, 21)),
        ("adult", (14, 12, 12)),
    ],
)
async def test_a_sector_s_profile_holds_its_node_types_subkinds_and_document_types(
    connection: psycopg.AsyncConnection, sector: str, counts: tuple[int, int, int]
) -> None:
    found = await profile_concepts(connection, sector)

    assert found is not None
    assert (len(found.node_types), len(found.subkinds), len(found.document_types)) == counts


async def test_a_profile_value_comes_with_the_core_value_it_refines(
    connection: psycopg.AsyncConnection,
) -> None:
    found = await profile_concepts(connection, "school")

    assert found is not None
    assert found.node_types[SCHOOL + "Inhaltsbereich"] == (CV + "fn_area",)
    assert found.subkinds[SCHOOL + "Kompetenzerwartung"] == (CV + "kind_learningOutcome",)


async def test_a_sector_without_a_profile_has_none(connection: psycopg.AsyncConnection) -> None:
    assert await profile_concepts(connection, "kindergarten") is None


async def test_a_retired_value_is_read_but_never_chosen(connection: psycopg.AsyncConnection) -> None:
    await connection.execute(
        "UPDATE vocab_concept SET retired_in = 1 WHERE iri = ANY(%s)",
        ([SCHOOL + "Inhaltsbereich", CV + "sec_adult"],),
    )

    read = await concept(connection, SCHOOL + "Inhaltsbereich")
    chosen = await profile_concepts(connection, "school")

    assert read is not None and read.retired
    assert chosen is not None and SCHOOL + "Inhaltsbereich" not in chosen.node_types
    assert await by_notation(connection, CV + "EducationSectors", "adult") is None


async def test_a_concept_is_found_by_its_notation_within_its_scheme(
    connection: psycopg.AsyncConnection,
) -> None:
    found = await by_notation(connection, CV + "EducationSectors", "school")

    assert found is not None
    assert (found.iri, found.scheme, found.notation, found.retired) == (
        CV + "sec_school",
        CV + "EducationSectors",
        "school",
        False,
    )
    assert found.pref_labels["de"]


async def test_an_unknown_concept_is_none(connection: psycopg.AsyncConnection) -> None:
    assert await concept(connection, CV + "sec_nowhere") is None
    assert await by_notation(connection, CV + "EducationSectors", "nowhere") is None


async def test_a_sector_s_cues_are_read_for_its_active_profile(connection: psycopg.AsyncConnection) -> None:
    cues = await cues_for(connection, "school")
    regions = await region_with_ancestors(connection, "DE-NW")

    held = [found.cue for found in active_cues(cues, regions, None, None)]
    named = {cue.iri for cue in held}
    kernlehrplan = next(cue for cue in cues if cue.iri == SCHOOL + "cue-dt-kernlehrplan")

    assert len(cues) == 487
    assert SCHOOL + "cue-dt-kernlehrplan" in named  # Nordrhein-Westfalen's
    assert SCHOOL + "cue-dt-lehrplanplus" not in named  # Bavaria's
    assert (kernlehrplan.maps_to, kernlehrplan.scope_regions, kernlehrplan.strength) == (
        (SCHOOL + "dt-Lehrplan",),
        frozenset({REGION + "DE-NW"}),
        0.95,
    )


async def test_a_sector_without_a_profile_has_no_cues(connection: psycopg.AsyncConnection) -> None:
    assert await cues_for(connection, "kindergarten") == []


async def test_a_region_comes_with_those_it_lies_in(connection: psycopg.AsyncConnection) -> None:
    assert await region_with_ancestors(connection, "DE-NW") == frozenset({REGION + "DE-NW", REGION + "DE"})
    assert await region_with_ancestors(connection, "DE") == frozenset({REGION + "DE"})
    assert await region_with_ancestors(connection, "XX") == frozenset()
