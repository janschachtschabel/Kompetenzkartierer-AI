"""The editors' review through the API (plan M1 9.5; Paket 9 G1, G8): one status for many nodes and
statements of a document, all or nothing, by the editors alone, audited; a stale row names each that
stands otherwise."""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.test_document_tree import a_document
from tests.api.test_documents import an_account, client, rows, url
from tests.api.test_node_editing import a_node
from tests.api.test_statement_editing import a_statement
from tests.db.l1 import CV

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents


def test_the_editors_confirm_nodes_and_statements_at_once(client: TestClient, url: str) -> None:
    document, _ = a_document(client, url)
    node = a_node(url, document)
    said = a_statement(url, document, node)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    items = [{"kind": "node", "id": node, "revision": 1}, {"kind": "statement", "id": said, "revision": 1}]

    answer = client.post(
        f"/api/v1/documents/{document}/review", headers=editor, json={"status": "confirmed", "items": items}
    )

    assert answer.status_code == 200, answer.text
    assert answer.json() == {"revisions": [{"id": node, "revision": 2}, {"id": said, "revision": 2}]}
    assert rows(
        url, "SELECT review_status_iri FROM node UNION ALL SELECT review_status_iri FROM statement"
    ) == [(CV + "rev_confirmed",), (CV + "rev_confirmed",)]
    assert rows(url, "SELECT action, subject, details FROM audit_log WHERE action = 'review.set'") == [
        ("review.set", f"document:{document}", {"status": "confirmed", "items": 2})
    ]


def test_a_stale_row_leaves_all_and_is_named_with_its_revision(client: TestClient, url: str) -> None:
    document, _ = a_document(client, url)
    node = a_node(url, document)
    _, admin = an_account(url, "Verwaltung", ("admin",))
    gone = str(uuid.uuid4())
    items = [{"kind": "node", "id": node, "revision": 2}, {"kind": "statement", "id": gone, "revision": 1}]

    answer = client.post(
        f"/api/v1/documents/{document}/review", headers=admin, json={"status": "rejected", "items": items}
    )

    assert (answer.status_code, answer.json()["code"]) == (409, "stale_revision")
    assert answer.json()["details"] == {
        "stale": [
            {"kind": "node", "id": node, "current": 1},
            {"kind": "statement", "id": gone, "current": None},
        ]
    }
    assert rows(url, "SELECT revision FROM node") == [(1,)]


def test_the_owner_reviews_not_and_to_another_the_document_is_none(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    node = a_node(url, document)
    _, stranger = an_account(url, "Fremde")
    review = {"status": "confirmed", "items": [{"kind": "node", "id": node, "revision": 1}]}

    by_owner = client.post(f"/api/v1/documents/{document}/review", headers=owner, json=review)
    by_stranger = client.post(f"/api/v1/documents/{document}/review", headers=stranger, json=review)

    assert (by_owner.status_code, by_owner.json()["code"]) == (403, "not_editor")
    assert (by_stranger.status_code, by_stranger.json()["code"]) == (404, "no_document")
    assert client.post(f"/api/v1/documents/{document}/review", json=review).status_code == 401
    assert rows(url, "SELECT revision FROM node") == [(1,)]


def test_a_review_names_a_status_and_a_row_at_least(client: TestClient, url: str) -> None:
    document, _ = a_document(client, url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    node = a_node(url, document)

    for review in (
        {"status": "confirmed", "items": []},
        {"status": "approved", "items": [{"kind": "node", "id": node, "revision": 1}]},
        {"status": "confirmed", "items": [{"kind": "anchor", "id": node, "revision": 1}]},
    ):
        answer = client.post(f"/api/v1/documents/{document}/review", headers=editor, json=review)
        assert (answer.status_code, answer.json()["code"]) == (422, "validation_failed")


def test_no_review_is_set_beside_an_open_job(client: TestClient, url: str) -> None:
    document, _ = a_document(client, url, ended=False)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    node = a_node(url, document)

    answer = client.post(
        f"/api/v1/documents/{document}/review",
        headers=editor,
        json={"status": "confirmed", "items": [{"kind": "node", "id": node, "revision": 1}]},
    )

    assert (answer.status_code, answer.json()["code"], answer.json()["details"]) == (409, "job_open", {})
