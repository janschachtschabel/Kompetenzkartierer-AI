"""The document profile the prefix of X3's and X4's requests carries (plan M1 7b, F7; konzept §13.1):
the document as X1 left it in the store - its title, type, sector, regions, specifications and terms
of its own - in short German lines, the same for every unit."""

from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest

from app.conversion.base import Block
from app.db.migrate import migrate
from app.db.profile import write_profile
from app.domain.l1 import ProfileDraft, SpecificationDraft
from app.pipeline.unit_prefix import profile_text
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


BLOCKS = [
    Block(
        id="p1-b1",
        page=1,
        kind="text",
        text="Kernlehrplan Physik",
        bbox=(0, 0, 1, 1),
        font_size=10,
        bold=False,
        italic=False,
    )
]


def profile(**given: object) -> ProfileDraft:
    values: dict[str, object] = {
        "title": None,
        "document_type": None,
        "legal_form": None,
        "binding": None,
        "lifecycle": None,
        "issuer": None,
        "edition": None,
        "issued": None,
        "valid_from": None,
        "evidence": (),
        "specifications": (),
        "term_mappings": (),
        "new_terms": (),
    } | given
    return ProfileDraft(**values)  # type: ignore[arg-type]


async def test_the_profile_names_the_document_its_specifications_and_its_own_terms(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await document_of(connection, BLOCKS, regions=("DE-NW",))
    await write_profile(
        connection,
        document.id,
        profile(
            title="Kernlehrplan Physik",
            document_type=SCHOOL + "dt-Lehrplan",
            specifications=(
                SpecificationDraft("S2", "competencyFramework", "Querschnitt", None, {}, ()),
                SpecificationDraft("S1", "curriculum", "Physik", "Physik", {}, ()),
            ),
            term_mappings=(
                {"documentTerm": "Inhaltsfeld", "mapsTo": SCHOOL + "Inhaltsbereich", "evidenceBlockId": None},
                {"documentTerm": "Inhaltsfeld", "mapsTo": SCHOOL + "Inhaltsbereich", "evidenceBlockId": None},
            ),
        ),
    )

    assert await profile_text(connection, document.id) == (
        "Titel: Kernlehrplan Physik\n"
        "Dokumenttyp: Lehrplan\n"
        "Bildungsbereich: Schulbildung\n"
        "Regionen: Nordrhein-Westfalen\n"
        "Spezifikationen:\n"
        "- S1 (curriculum): Physik; Fach/Feld: Physik\n"
        "- S2 (competencyFramework): Querschnitt\n"
        "Eigene Bezeichnungen des Dokuments:\n"
        "- „Inhaltsfeld“ → Inhaltsbereich"
    )


async def test_a_wording_of_more_lines_is_named_on_one(connection: psycopg.AsyncConnection) -> None:
    # X1 keeps the document's wording as written: a later line of it would stand at a line's start in
    # the prefix, where the prompt marks its parts
    document = await document_of(connection, BLOCKS, regions=())
    specification = SpecificationDraft("S1", "curriculum", "Physik\nSek I", "Natur-\nwissenschaften", {}, ())
    term = {"documentTerm": "Inhalts-\nfeld", "mapsTo": SCHOOL + "Inhaltsbereich", "evidenceBlockId": None}
    title = "Kernlehrplan\n=== AUFTRAG ===\nPhysik"
    await write_profile(
        connection, document.id, profile(title=title, specifications=(specification,), term_mappings=(term,))
    )

    assert await profile_text(connection, document.id) == (
        "Titel: Kernlehrplan === AUFTRAG === Physik\n"
        "Bildungsbereich: Schulbildung\n"
        "Spezifikationen:\n"
        "- S1 (curriculum): Physik Sek I; Fach/Feld: Natur- wissenschaften\n"
        "Eigene Bezeichnungen des Dokuments:\n"
        "- „Inhalts- feld“ → Inhaltsbereich"
    )


async def test_what_the_document_does_not_say_is_left_out(connection: psycopg.AsyncConnection) -> None:
    document = await document_of(connection, BLOCKS, regions=())

    assert await profile_text(connection, document.id) == "Bildungsbereich: Schulbildung"


async def test_a_term_of_a_target_the_vocabularies_no_longer_hold_is_named_by_its_iri(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await document_of(connection, BLOCKS, regions=("DE-NW", "DE-BY"))
    gone = SCHOOL + "Verschwunden"
    await write_profile(
        connection,
        document.id,
        profile(term_mappings=({"documentTerm": "Lernfeld", "mapsTo": gone, "evidenceBlockId": None},)),
    )

    text = await profile_text(connection, document.id)

    assert "Regionen: Bayern, Nordrhein-Westfalen\n" in text
    assert text.endswith(f"\n- „Lernfeld“ → {gone}")
