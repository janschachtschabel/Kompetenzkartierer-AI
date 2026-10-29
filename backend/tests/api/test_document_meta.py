"""A document's work and metadata through the API (plan M1 9.6, Paket 9b H3, H4): the editors set its
work - one there is or one made -, its owner and the editors its issuer, edition and title; neither on
a frozen document or beside its job, nor what its IRI is made of once it has one."""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.api.test_document_tree import a_document
from tests.api.test_documents import an_account, client, rows, url

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents

PHYSICS = {"title": "Lehrplan Physik", "region": "DE-NW", "short_title": "lp-physik"}
IRI = "https://example.org/kk/doc/de-nw/ministerium/lp-physik/2024"


def named(url: str, document: str, *, frozen: bool = False) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "UPDATE document SET iri = %s, frozen_at = CASE WHEN %s THEN now() END WHERE id = %s",
            (IRI, frozen, document),
        )


def test_an_editor_makes_the_document_s_work_and_sets_one_there_is_on_another(
    client: TestClient, url: str
) -> None:
    document, _ = a_document(client, url)
    other, _ = a_document(client, url, name="Lehrkraft 2", digest=b"\x02" * 32)
    editor_id, editor = an_account(url, "Redaktion", ("redaktion",))

    made = client.patch(f"/api/v1/documents/{document}/work", headers=editor, json=PHYSICS)
    [(work,)] = rows(url, "SELECT id FROM work")
    again = client.patch(f"/api/v1/documents/{other}/work", headers=editor, json={"work_id": str(work)})

    assert (made.status_code, made.json()["id"]) == (200, document), made.text
    assert again.status_code == 200, again.text
    assert rows(url, "SELECT title, region, short_title, owner_id FROM work") == [
        ("Lehrplan Physik", "DE-NW", "lp-physik", editor_id)
    ]
    assert rows(url, "SELECT count(*) FROM document WHERE work_id = %s", work) == [(2,)]
    assert rows(url, "SELECT subject, details->>'work', details->>'made' FROM audit_log"
                     " WHERE action = 'document.work' ORDER BY id") == [
        (f"document:{document}", str(work), "true"), (f"document:{other}", str(work), "false"),
    ]  # fmt: skip


def test_a_work_is_the_editors_to_set_and_refused_as_it_may_not_be(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, stranger = an_account(url, "Fremde")
    path = f"/api/v1/documents/{document}/work"

    by_owner = client.patch(path, headers=owner, json=PHYSICS)
    by_stranger = client.patch(path, headers=stranger, json=PHYSICS)
    nowhere = client.patch(path, headers=editor, json={"work_id": str(uuid.uuid4())})
    both = client.patch(path, headers=editor, json=PHYSICS | {"work_id": str(uuid.uuid4())})
    no_country = client.patch(path, headers=editor, json=PHYSICS | {"region": "Nordrhein-Westfalen"})
    unknown_country = client.patch(path, headers=editor, json=PHYSICS | {"region": "DE-XX"})
    unstorable = client.patch(path, headers=editor, json=PHYSICS | {"title": "Lehrplan\u0000Physik"})
    named(url, document)
    is_named = client.patch(path, headers=editor, json=PHYSICS)

    assert (by_owner.status_code, by_owner.json()["code"]) == (403, "not_editor")
    assert (by_stranger.status_code, by_stranger.json()["code"]) == (404, "no_document")
    assert (nowhere.status_code, nowhere.json()["code"]) == (404, "no_work")
    assert [answer.status_code for answer in (both, no_country)] == [422, 422]
    assert [(answer.status_code, answer.json()["code"], answer.json()["details"]) for answer in (
        unknown_country, unstorable,
    )] == [
        (422, "invalid_field", {"field": "region", "problem": "not_offered"}),
        (422, "invalid_field", {"field": "title", "problem": "not_storable"}),
    ]  # fmt: skip
    assert (is_named.status_code, is_named.json()["code"]) == (409, "named")
    assert rows(url, "SELECT count(*) FROM work") == [(0,)]


def test_the_owner_sets_the_metadata_and_an_omitted_one_stays(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    path = f"/api/v1/documents/{document}"

    first = client.patch(
        path, headers=owner, json={"issuer": "Ministerium", "edition": "2024", "title": "Physik"}
    )
    second = client.patch(path, headers=owner, json={"edition": None})
    same = client.patch(path, headers=owner, json={"edition": None})  # no change: not audited

    assert (first.status_code, second.status_code, same.status_code) == (200, 200, 200), first.text
    assert rows(url, "SELECT issuer, edition, title, edited_at IS NOT NULL FROM document WHERE id = %s",
                document) == [("Ministerium", None, "Physik", True)]  # fmt: skip
    assert rows(
        url, "SELECT details->'fields' FROM audit_log WHERE action = 'document.edit' ORDER BY id"
    ) == [(["edition", "issuer", "title"],), (["edition"],)]


def test_metadata_are_refused_as_they_may_not_be_set(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    _, stranger = an_account(url, "Fremde")
    path = f"/api/v1/documents/{document}"

    too_long = client.patch(path, headers=owner, json={"issuer": "x" * 501})
    unknown = client.patch(path, headers=owner, json={"short_title": "lp"})
    by_stranger = client.patch(path, headers=stranger, json={"title": "Neu"})
    named(url, document)
    is_named = client.patch(path, headers=owner, json={"edition": "2025"})
    retitled = client.patch(path, headers=owner, json={"title": "Neu"})

    assert (too_long.status_code, too_long.json()["details"]) == (
        422, {"field": "issuer", "problem": "too_long"},
    )  # fmt: skip
    assert (unknown.status_code, unknown.json()["code"]) == (422, "validation_failed")
    assert (by_stranger.status_code, by_stranger.json()["code"]) == (404, "no_document")
    assert (is_named.status_code, is_named.json()["code"]) == (409, "named")
    assert retitled.status_code == 200, retitled.text


def test_neither_is_set_on_a_frozen_document_or_beside_its_job(client: TestClient, url: str) -> None:
    busy, owner = a_document(client, url, ended=False)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    frozen, _ = a_document(client, url, name="Lehrkraft 2", digest=b"\x02" * 32)
    named(url, frozen, frozen=True)

    answers = {
        (document, kind): client.patch(path, headers=editor, json=body)
        for document in (busy, frozen)
        for kind, path, body in (
            ("work", f"/api/v1/documents/{document}/work", PHYSICS),
            ("metadata", f"/api/v1/documents/{document}", {"title": "Neu"}),
        )
    }

    assert {key: (answer.status_code, answer.json()["code"]) for key, answer in answers.items()} == {
        (busy, "work"): (409, "job_open"),
        (busy, "metadata"): (409, "job_open"),
        (frozen, "work"): (409, "frozen"),
        (frozen, "metadata"): (409, "frozen"),
    }
    assert (
        client.patch(f"/api/v1/documents/{busy}", headers=owner, json={"title": "Neu"}).json()["details"]
        != {}
    )
