"""An editor's changes to a document's nodes through the API (plan M1 9.3; Paket 9 G1-G6): a node's fields
set on the revision it was read at, a node added after its siblings, a node dropped with its subtree - by
the document's owner and the editors, each audited; refused with the stored state for a stale revision,
with the field and why for a value the form does not take, beside an open job and once frozen."""

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.api.edit_answers import FieldKey
from app.vocab.forms import NODE_FIELDS, STATEMENT_FIELDS
from tests.api.test_document_tree import a_document
from tests.api.test_documents import an_account, client, hidden_from_its_owner, rows, url
from tests.db.l1 import CV, add_node, add_statement

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents

HUMAN, PROPOSED = CV + "orig_human", CV + "rev_proposed"


def a_node(url: str, document: str, **columns: Any) -> str:
    with psycopg.connect(url, autocommit=True) as connection:
        return str(add_node(connection, uuid.UUID(document), original_title="Optik", **columns))


def test_the_owner_edits_a_node_and_reads_it_back_as_the_tree_has_it(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    made = a_node(url, document)

    answer = client.patch(
        f"/api/v1/nodes/{made}", headers=owner, json={"expected_revision": 1, "fields": {"code": "2"}}
    )

    assert answer.status_code == 200, answer.text
    row = answer.json()
    assert (row["id"], row["revision"], row["origin"], row["review_status"]) == (made, 2, HUMAN, PROPOSED)
    assert row["fields"] == {
        "original_title": "Optik", "function": CV + "fn_area", "node_type": None, "code": "2",
        "obligation": None,
    }  # fmt: skip
    assert set(row) == {
        "id", "position", "fields", "code_assigned", "origin", "review_status", "revision", "findings",
        "anchors", "iri",
    }  # fmt: skip
    assert row["iri"] is None  # given when the document is frozen
    assert rows(
        url, "SELECT action, subject, details->>'document' FROM audit_log WHERE action LIKE 'node.%%'"
    ) == [("node.edit", f"node:{made}", document)]


def test_an_edit_of_a_stale_revision_is_refused_with_the_node_as_it_stands(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    made = a_node(url, document)
    client.patch(
        f"/api/v1/nodes/{made}", headers=owner, json={"expected_revision": 1, "fields": {"code": "2"}}
    )

    answer = client.patch(
        f"/api/v1/nodes/{made}", headers=owner, json={"expected_revision": 1, "fields": {"code": "3"}}
    )

    assert (answer.status_code, answer.json()["code"]) == (409, "stale_revision")
    current = answer.json()["details"]["current"]
    assert (current["revision"], current["fields"]["code"]) == (2, "2")


def test_a_field_the_node_may_not_take_is_refused_with_the_field_and_why(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    made = a_node(url, document)

    answer = client.patch(
        f"/api/v1/nodes/{made}",
        headers=owner,
        json={"expected_revision": 1, "fields": {"original_title": ""}},
    )

    assert (answer.status_code, answer.json()["code"]) == (422, "invalid_field")
    assert answer.json()["details"] == {"field": "original_title", "problem": "required"}


def test_a_text_no_store_keeps_and_a_key_no_form_has_are_refused_not_failed_on(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    made = a_node(url, document)
    path = f"/api/v1/nodes/{made}"
    raw = {**owner, "content-type": "application/json"}

    surrogate = client.patch(
        path, headers=raw, content=b'{"expected_revision": 1, "fields": {"original_title": "a\\ud800"}}'
    )
    nul = client.patch(
        path, headers=owner, json={"expected_revision": 1, "fields": {"original_title": "a\x00"}}
    )
    long_key = client.patch(path, headers=owner, json={"expected_revision": 1, "fields": {"t" * 5000: "a"}})
    odd_key = client.patch(
        path, headers=raw, content=b'{"expected_revision": 1, "fields": {"\\ud800a": "a"}}'
    )
    signs_key = client.patch(
        path, headers=owner, json={"expected_revision": 1, "fields": {"code\x1b[2J": "a"}}
    )
    both_wrong = client.patch(path, headers=owner, json={"expected_revision": 1, "fields": {"t" * 5000: 1}})

    for answer in (surrogate, nul):
        assert (answer.status_code, answer.json()["details"]) == (
            422, {"field": "original_title", "problem": "not_storable"},
        )  # fmt: skip
    for answer in (long_key, odd_key, signs_key):
        assert (answer.status_code, answer.json()["code"]) == (422, "validation_failed")
        assert [fault["loc"] for fault in answer.json()["details"]["errors"]] == [
            ["body", "fields", "_", "[key]"]
        ]
    # its value wrong as well, the key stands in the value's faults too: masked there alike
    faults = [fault["loc"] for fault in both_wrong.json()["details"]["errors"]]
    assert len(faults) > 1 and all(loc[:3] == ["body", "fields", "_"] for loc in faults), faults
    assert max(len(long_key.content), len(both_wrong.content)) < 500  # the key not given back
    assert rows(url, "SELECT revision FROM node") == [(1,)]


def test_every_key_of_the_forms_is_one_the_api_takes() -> None:
    keys = TypeAdapter(FieldKey)
    for field in (*NODE_FIELDS, *STATEMENT_FIELDS):
        assert keys.validate_python(field.key) == field.key


def test_a_node_taken_away_on_a_stale_revision_stays_and_comes_back_as_it_stands(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    made = a_node(url, document)

    answer = client.delete(f"/api/v1/nodes/{made}", headers=owner, params={"expected_revision": 2})

    assert (answer.status_code, answer.json()["code"]) == (409, "stale_revision")
    assert answer.json()["details"]["current"]["revision"] == 1
    assert rows(url, "SELECT count(*) FROM node") == [(1,)]


def test_a_node_is_added_after_its_siblings_and_dropped_with_its_subtree(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    top = a_node(url, document)
    with psycopg.connect(url, autocommit=True) as connection:
        add_statement(connection, uuid.UUID(document), uuid.UUID(top))
    fields = {"original_title": "Licht", "function": CV + "fn_unit"}

    added = client.post(
        f"/api/v1/documents/{document}/nodes", headers=owner, json={"parent_id": top, "fields": fields}
    )

    assert added.status_code == 201, added.text
    child = added.json()
    assert (child["position"], child["revision"], child["fields"]["original_title"]) == (1, 1, "Licht")
    dropped = client.delete(f"/api/v1/nodes/{top}", headers=owner, params={"expected_revision": 1})
    assert (dropped.status_code, dropped.json()) == (200, {"nodes": 2, "statements": 1})
    assert rows(url, "SELECT action FROM audit_log WHERE action LIKE 'node.%%' ORDER BY id") == [
        ("node.add",),
        ("node.drop",),
    ]


def test_a_new_node_needs_its_form_s_fields_and_a_parent_of_its_document(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    nodes = f"/api/v1/documents/{document}/nodes"

    missing = client.post(nodes, headers=owner, json={"fields": {"function": CV + "fn_area"}})
    nowhere = client.post(
        nodes, headers=owner, json={"parent_id": str(uuid.uuid4()), "fields": {"original_title": "Licht",
                                                                                 "function": CV + "fn_area"}},
    )  # fmt: skip

    assert (missing.status_code, missing.json()["details"]) == (
        422, {"field": "original_title", "problem": "required"},
    )  # fmt: skip
    assert (nowhere.status_code, nowhere.json()["code"]) == (404, "no_node")


def test_no_node_is_changed_before_the_extraction_has_read_every_package(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url, extracted=False)
    made = a_node(url, document)

    answer = client.patch(
        f"/api/v1/nodes/{made}", headers=owner, json={"expected_revision": 1, "fields": {"code": "2"}}
    )

    assert (answer.status_code, answer.json()["code"]) == (409, "not_extracted")
    assert rows(url, "SELECT revision FROM node") == [(1,)]


def test_no_node_is_changed_beside_an_open_job_or_once_the_document_is_frozen(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url, ended=False)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, admin = an_account(url, "Verwaltung", ("admin",))
    made = a_node(url, document)
    job = rows(url, "SELECT id FROM job WHERE payload->>'document_id' = %s", document)[0][0]
    edit = {"expected_revision": 1, "fields": {"code": "2"}}

    to_owner = client.patch(f"/api/v1/nodes/{made}", headers=owner, json=edit)
    to_admin = client.patch(f"/api/v1/nodes/{made}", headers=admin, json=edit)
    to_editor = client.patch(f"/api/v1/nodes/{made}", headers=editor, json=edit)

    for answer in (to_owner, to_admin):
        assert (answer.status_code, answer.json()["code"], answer.json()["details"]) == (
            409, "job_open", {"job_id": str(job)},
        )  # fmt: skip
    assert (to_editor.status_code, to_editor.json()["details"]) == (409, {})  # another's job, unnamed
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE job SET status = 'done', finished_at = now() WHERE id = %s", (job,))
        connection.execute(
            "UPDATE document SET iri = 'https://example.org/curriculum/1', frozen_at = now() WHERE id = %s",
            (document,),
        )
    for answer in (
        client.patch(f"/api/v1/nodes/{made}", headers=owner, json=edit),
        client.delete(f"/api/v1/nodes/{made}", headers=owner, params={"expected_revision": 1}),
        client.post(f"/api/v1/documents/{document}/nodes", headers=owner,
                    json={"fields": {"original_title": "Licht", "function": CV + "fn_area"}}),
    ):  # fmt: skip
        assert (answer.status_code, answer.json()["code"]) == (409, "frozen")
    assert rows(url, "SELECT revision FROM node") == [(1,)]


def test_the_editors_edit_any_node_and_to_another_it_is_none(client: TestClient, url: str) -> None:
    document, _ = a_document(client, url)
    made = a_node(url, document)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, stranger = an_account(url, "Fremde")
    edit = {"expected_revision": 1, "fields": {"code": "2"}}

    assert client.patch(f"/api/v1/nodes/{made}", headers=editor, json=edit).status_code == 200
    for answer in (
        client.patch(f"/api/v1/nodes/{made}", headers=stranger, json=edit),
        client.delete(f"/api/v1/nodes/{made}", headers=stranger, params={"expected_revision": 2}),
    ):
        assert (answer.status_code, answer.json()["code"]) == (404, "no_node")
    added = client.post(f"/api/v1/documents/{document}/nodes", headers=stranger,
                        json={"fields": {"original_title": "Licht", "function": CV + "fn_area"}})  # fmt: skip
    assert (added.status_code, added.json()["code"]) == (404, "no_document")
    assert client.patch(f"/api/v1/nodes/{made}", json=edit).status_code == 401
    assert client.delete(f"/api/v1/nodes/{made}", headers=editor).status_code == 422  # no revision named


def test_a_node_whose_entry_is_no_longer_the_owner_s_to_read_is_changed_by_the_editors_alone(
    client: TestClient, url: str
) -> None:
    # its fields are the entry's content in the document's words: no answer gives them, not even a stale one's
    document, owner = a_document(client, url)
    made = a_node(url, document)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    hidden_from_its_owner(url, document)
    stale = {"expected_revision": 9, "fields": {}}

    answers = [
        client.patch(f"/api/v1/nodes/{made}", headers=owner, json=stale),
        client.post(f"/api/v1/documents/{document}/nodes", headers=owner,
                    json={"fields": {"original_title": "Licht", "function": CV + "fn_area"}}),
        client.delete(f"/api/v1/nodes/{made}", headers=owner, params={"expected_revision": 9}),
    ]  # fmt: skip

    assert [(answer.status_code, answer.json()["code"]) for answer in answers] == [(403, "file_hidden")] * 3
    assert "details" not in answers[0].json() or not answers[0].json()["details"]
    edited = client.patch(
        f"/api/v1/nodes/{made}", headers=editor, json={"expected_revision": 1, "fields": {"code": "2"}}
    )
    assert edited.status_code == 200, edited.text
