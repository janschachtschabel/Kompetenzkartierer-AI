"""A document's profile as X1 read it, written to the first layer (plan M1 6.2): its own values, its
specifications with their variants and anchors, the terms of its own; a document type set before
stays, and a work of the same title and region is only suggested."""

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from app.conversion.base import Block
from app.db.documents import Document, set_document_type
from app.db.migrate import migrate
from app.db.profile import suggest_work, write_profile, x1_state
from app.db.runs import RunStart, finish_run, start_run
from app.domain.l1 import ProfileDraft, SpecificationDraft, VariantDraft
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


def block(block_id: str, words: str) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id,
        page=page,
        kind="text",
        text=words,
        bbox=(0, 0, 1, 1),
        font_size=10,
        bold=False,
        italic=False,
    )


@pytest.fixture
async def document(connection: psycopg.AsyncConnection) -> Document:
    blocks = [block("p1-b1", "Kernlehrplan Physik"), block("p1-b2", "Ministerium"), block("p2-b1", "Inhalt")]
    return await document_of(connection, blocks)


def draft(**changes: Any) -> ProfileDraft:
    values: dict[str, Any] = {
        "title": "Kernlehrplan Physik",
        "document_type": SCHOOL + "dt-Lehrplan",
        "legal_form": CV + "lf_administrativeRegulation",
        "binding": CV + "bind_binding",
        "lifecycle": CV + "life_inForce",
        "issuer": "Ministerium für Schule und Bildung",
        "edition": "Fassung 2019",
        "issued": "2019-06",
        "valid_from": "2019-08-01",
        "evidence": ("p1-b1", "p2-b1"),
        "specifications": (
            SpecificationDraft(
                key="S1",
                kind="curriculum",
                title="Physik",
                field_text="Physik",
                applicability={"sector": CV + "sec_school", "timeText": "Klassen 5 bis 10"},
                evidence=("p1-b1",),
                variants=(VariantDraft("V1", "G9", CV + "var_track"),),
            ),
        ),
        "term_mappings": (
            {"documentTerm": "Inhaltsfeld", "mapsTo": SCHOOL + "Inhaltsbereich", "evidenceBlockId": "p2-b1"},
        ),
        "new_terms": (
            {"documentTerm": "Schwerpunkt", "suggestedFunction": CV + "fn_grouping", "evidenceBlockId": None},
        ),
    } | changes
    return ProfileDraft(**values)


async def rows(connection: psycopg.AsyncConnection, query: str, *params: Any) -> list[dict[str, Any]]:
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        return await cursor.fetchall()


async def test_a_profile_is_written_to_its_document(
    connection: psycopg.AsyncConnection, document: Document
) -> None:
    async with connection.transaction():
        keys, notes = await write_profile(connection, document.id, draft())

    [written] = await rows(
        connection,
        "SELECT title, document_type_iri, legal_form_scheme, legal_form_iri, binding_iri, lifecycle_iri,"
        " issuer, edition, issued, valid_from FROM document WHERE id = %s",
        document.id,
    )
    assert written == {
        "title": "Kernlehrplan Physik",
        "document_type_iri": SCHOOL + "dt-Lehrplan",
        "legal_form_scheme": CV + "LegalForms",
        "legal_form_iri": CV + "lf_administrativeRegulation",
        "binding_iri": CV + "bind_binding",
        "lifecycle_iri": CV + "life_inForce",
        "issuer": "Ministerium für Schule und Bildung",
        "edition": "Fassung 2019",
        "issued": "2019-06",
        "valid_from": "2019-08-01",
    }
    [profile] = await rows(
        connection,
        "SELECT term_mappings, new_terms FROM document_profile WHERE document_id = %s",
        document.id,
    )
    assert profile["term_mappings"] == [
        {"documentTerm": "Inhaltsfeld", "mapsTo": SCHOOL + "Inhaltsbereich", "evidenceBlockId": "p2-b1"}
    ]
    assert profile["new_terms"][0]["suggestedFunction"] == CV + "fn_grouping"
    [specification] = await rows(
        connection,
        "SELECT id, key, spec_kind, title, field_text, applicability FROM specification"
        " WHERE document_id = %s",
        document.id,
    )
    assert keys == {"S1": specification["id"]}
    assert (specification["key"], specification["spec_kind"], specification["title"]) == (
        "S1",
        "curriculum",
        "Physik",
    )
    assert specification["applicability"] == {"sector": CV + "sec_school", "timeText": "Klassen 5 bis 10"}
    [variant] = await rows(
        connection,
        "SELECT key, label, variant_kind_iri FROM variant WHERE specification_id = %s",
        specification["id"],
    )
    assert variant == {"key": "V1", "label": "G9", "variant_kind_iri": CV + "var_track"}
    assert notes == []


async def test_the_document_and_its_specifications_are_anchored_at_their_blocks(
    connection: psycopg.AsyncConnection, document: Document
) -> None:
    async with connection.transaction():
        keys, _ = await write_profile(connection, document.id, draft())

    anchors = await rows(
        connection,
        "SELECT a.specification_id, a.node_id, a.page_start, a.page_end,"
        " array_agg(b.block_id ORDER BY b.block_id) AS blocks"
        " FROM anchor a JOIN anchor_block b ON b.anchor_id = a.id WHERE a.document_id = %s"
        " GROUP BY a.id ORDER BY a.specification_id NULLS FIRST",
        document.id,
    )  # fmt: skip
    assert anchors == [
        {
            "specification_id": None,
            "node_id": None,
            "page_start": 1,
            "page_end": 2,
            "blocks": ["p1-b1", "p2-b1"],
        },
        {
            "specification_id": keys["S1"],
            "node_id": None,
            "page_start": 1,
            "page_end": None,
            "blocks": ["p1-b1"],
        },
    ]


async def test_nothing_read_from_no_block_is_anchored(
    connection: psycopg.AsyncConnection, document: Document
) -> None:
    async with connection.transaction():
        await write_profile(connection, document.id, draft(evidence=(), specifications=(), legal_form=None))

    assert await rows(connection, "SELECT id FROM anchor WHERE document_id = %s", document.id) == []
    [values] = await rows(
        connection, "SELECT legal_form_scheme, legal_form_iri FROM document WHERE id = %s", document.id
    )
    assert values == {
        "legal_form_scheme": None,
        "legal_form_iri": None,
    }  # a value not read leaves its scheme out


async def test_a_document_type_set_before_stays_and_another_read_is_a_note(
    connection: psycopg.AsyncConnection, document: Document
) -> None:
    await set_document_type(connection, document.id, SCHOOL + "dt-Handreichung")

    async with connection.transaction():
        _, notes = await write_profile(connection, document.id, draft())

    [kept] = await rows(connection, "SELECT document_type_iri FROM document WHERE id = %s", document.id)
    assert kept["document_type_iri"] == SCHOOL + "dt-Handreichung"
    assert [(note.rule, note.severity, note.path, dict(note.details)) for note in notes] == [
        (
            "x1.document_type_differs",
            "info",
            "$.document.documentType",
            {"found": SCHOOL + "dt-Lehrplan", "document": SCHOOL + "dt-Handreichung"},
        )
    ]


async def add_work(connection: psycopg.AsyncConnection, title: str, region: str | None) -> UUID:
    [made] = await rows(
        connection, "INSERT INTO entity (id, kind) VALUES (gen_random_uuid(), 'work') RETURNING id"
    )
    await connection.execute(
        "INSERT INTO work (id, title, region) VALUES (%s, %s, %s)", (made["id"], title, region)
    )
    return UUID(str(made["id"]))


async def test_a_work_of_the_same_title_and_region_is_suggested(connection: psycopg.AsyncConnection) -> None:
    work = await add_work(connection, "Kernlehrplan  Physik", "DE-NW")
    await add_work(connection, "Kernlehrplan Physik", "DE-HE")

    assert await suggest_work(connection, "kernlehrplan physik", ("DE-NW",)) == work
    for edged in ("Kernlehrplan Physik\n", "\tKernlehrplan Physik"):  # a title copied with its line's edge
        assert await suggest_work(connection, edged, ("DE-NW",)) == work
    assert await suggest_work(connection, "Kernlehrplan Chemie", ("DE-NW",)) is None
    assert await suggest_work(connection, "Kernlehrplan Physik", ("DE-BY",)) is None
    assert await suggest_work(connection, "Kernlehrplan Physik", ()) is None


class CommitsAfterTheFirst:
    """A connection on which, right after its first statement, another transaction commits."""

    def __init__(self, connection: psycopg.AsyncConnection, then: Callable[[], Awaitable[None]]) -> None:
        self._connection, self._then, self._first = connection, then, True

    async def execute(self, *given: Any, **named: Any) -> Any:
        cursor = await self._connection.execute(*given, **named)
        if self._first:
            self._first = False
            await self._then()
        return cursor


async def test_where_x1_stands_is_read_at_one_moment(
    connection: psycopg.AsyncConnection, document: Document, database_url: str
) -> None:
    # another job's X1 commits its profile and its run's end at once: a look sees both or neither,
    # never the profile without the run (a tree no extraction wrote)
    async def x1_of_another_job() -> None:
        async with await psycopg.AsyncConnection.connect(database_url) as other, other.transaction():
            await write_profile(other, document.id, draft())
            run = await start_run(other, RunStart(document.id, None, None, "X1", None, None, None, None))
            await finish_run(other, run, "done", {})

    looked = await x1_state(cast(Any, CommitsAfterTheFirst(connection, x1_of_another_job)), document.id)

    assert looked == "open"  # as it stood at the look
    assert await x1_state(connection, document.id) == "done"


async def test_a_profile_no_run_of_x1_wrote_is_a_tree_x1_does_not_write_onto(
    connection: psycopg.AsyncConnection, document: Document
) -> None:
    # specifications without a node: a second profile would meet the first one's keys
    await write_profile(connection, document.id, draft())

    assert await x1_state(connection, document.id) == "tree"
