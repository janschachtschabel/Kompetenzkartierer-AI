"""An editor's changes to a document's statements through the API (plan M1 9.4; Paket 9 G2-G7): fields,
addressees and anchors set on the revision they were read at, a statement added with an anchor at least,
a statement taken away - rejected where a run wrote it, deleted where an editor did -, each audited."""

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.api.test_document_tree import a_document
from tests.api.test_documents import an_account, client, rows, url
from tests.api.test_node_editing import a_node
from tests.db.l1 import CV, add_run, add_statement

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents

HUMAN, MODEL = CV + "orig_human", CV + "orig_model"
LEARNER, EDUCATOR = CV + "addr_learner", CV + "addr_educator"
NEW = {"verbatim": "Sie prüfen.", "statement_kind": CV + "kind_learningOutcome", "addressees": [LEARNER]}


def a_statement(url: str, document: str, node: str, **columns: Any) -> str:
    with psycopg.connect(url, autocommit=True) as connection:
        return str(add_statement(connection, uuid.UUID(document), uuid.UUID(node), **columns))


def a_run_s_statement(url: str, document: str, node: str) -> str:
    with psycopg.connect(url, autocommit=True) as connection:
        run = add_run(connection, uuid.UUID(document))
    return a_statement(url, document, node, origin_iri=MODEL, run_id=run)


def test_a_statement_s_fields_and_anchors_are_set_and_read_back(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    said = a_statement(url, document, a_node(url, document))
    edit = {
        "expected_revision": 1,
        "fields": {"lead_in": "Die Lernenden", "codeText": "K1", "addressees": [LEARNER, EDUCATOR]},
        "anchors": [{"blocks": ["p2-b1", "p1-b1"]}, {"page": 2}],
    }

    answer = client.patch(f"/api/v1/statements/{said}", headers=owner, json=edit)

    assert answer.status_code == 200, answer.text
    row = answer.json()
    assert (row["id"], row["revision"], row["origin"]) == (said, 2, HUMAN)
    assert (row["fields"]["lead_in"], row["fields"]["codeText"], row["fields"]["addressees"]) == (
        "Die Lernenden", "K1", [EDUCATOR, LEARNER],
    )  # fmt: skip
    assert [(anchor["page_start"], anchor["page_end"], anchor["match_kind"], anchor["blocks"])
            for anchor in row["anchors"]] == [
        (1, 2, None, ["p1-b1", "p2-b1"]), (2, None, CV + "match_notFound", []),
    ]  # fmt: skip
    assert rows(url, "SELECT action, subject FROM audit_log WHERE action LIKE 'statement.%%'") == [
        ("statement.edit", f"statement:{said}")
    ]


def test_a_stale_revision_and_an_anchor_of_no_block_are_refused(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    said = a_statement(url, document, a_node(url, document))

    stale = client.patch(
        f"/api/v1/statements/{said}", headers=owner, json={"expected_revision": 2, "fields": {}}
    )
    nowhere = client.patch(
        f"/api/v1/statements/{said}", headers=owner,
        json={"expected_revision": 1, "fields": {}, "anchors": [{"blocks": ["p9-b9"]}]},
    )  # fmt: skip

    assert (stale.status_code, stale.json()["code"]) == (409, "stale_revision")
    current = stale.json()["details"]["current"]
    assert (current["id"], current["revision"], current["fields"]["verbatim"]) == (
        said, 1, "Die Lernenden planen ihre Arbeit.",
    )  # fmt: skip
    assert (nowhere.status_code, nowhere.json()["code"], nowhere.json()["details"]) == (
        422, "invalid_field", {"field": "anchors", "problem": "unknown_block"},
    )  # fmt: skip
    assert client.patch(f"/api/v1/statements/{said}", headers=owner,
                        json={"expected_revision": 1, "fields": {}, "anchors": [{"blocks": ["b1"]}]}
                        ).status_code == 422  # fmt: skip


def test_a_new_statement_comes_with_an_anchor_at_least(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    node = a_node(url, document)
    a_statement(url, document, node)
    statements = f"/api/v1/nodes/{node}/statements"

    without = client.post(statements, headers=owner, json={"fields": NEW, "anchors": []})
    added = client.post(statements, headers=owner, json={"fields": NEW, "anchors": [{"blocks": ["p1-b1"]}]})

    assert (without.status_code, without.json()["code"]) == (422, "anchor_missing")
    assert added.status_code == 201, added.text
    row = added.json()
    assert (row["position"], row["revision"], row["origin"], row["fields"]["verbatim"]) == (
        2, 1, HUMAN, "Sie prüfen.",
    )  # fmt: skip
    nowhere = client.post(f"/api/v1/nodes/{uuid.uuid4()}/statements", headers=owner,
                          json={"fields": NEW, "anchors": [{"page": 1}]})  # fmt: skip
    assert (nowhere.status_code, nowhere.json()["code"]) == (404, "no_node")
    assert rows(url, "SELECT action FROM audit_log WHERE action LIKE 'statement.%%'") == [("statement.add",)]


def test_a_run_s_statement_taken_away_is_rejected_and_an_editor_s_deleted(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    node = a_node(url, document)
    by_run = a_run_s_statement(url, document, node)
    by_hand = client.post(
        f"/api/v1/nodes/{node}/statements", headers=owner, json={"fields": NEW, "anchors": [{"page": 1}]}
    ).json()["id"]

    rejected = client.delete(f"/api/v1/statements/{by_run}", headers=owner, params={"expected_revision": 1})
    deleted = client.delete(f"/api/v1/statements/{by_hand}", headers=owner, params={"expected_revision": 1})

    assert (rejected.status_code, rejected.json()) == (200, {"outcome": "rejected"})
    assert (deleted.status_code, deleted.json()) == (200, {"outcome": "deleted"})
    assert rows(url, "SELECT review_status_iri FROM statement") == [(CV + "rev_rejected",)]
    assert rows(url, "SELECT action FROM audit_log WHERE action LIKE 'statement.%%' ORDER BY id") == [
        ("statement.add",),
        ("statement.reject",),
        ("statement.delete",),
    ]


def test_to_another_a_statement_is_none_and_beside_an_open_job_it_stays(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url, ended=False)
    node = a_node(url, document)
    said = a_statement(url, document, node)
    _, stranger = an_account(url, "Fremde")

    for answer in (
        client.patch(
            f"/api/v1/statements/{said}", headers=stranger, json={"expected_revision": 1, "fields": {}}
        ),
        client.delete(f"/api/v1/statements/{said}", headers=stranger, params={"expected_revision": 1}),
    ):
        assert (answer.status_code, answer.json()["code"]) == (404, "no_statement")
    busy = client.patch(
        f"/api/v1/statements/{said}",
        headers=owner,
        json={"expected_revision": 1, "fields": {"lead_in": "Sie"}},
    )
    assert (busy.status_code, busy.json()["code"]) == (409, "job_open")
    assert client.delete(f"/api/v1/statements/{said}", params={"expected_revision": 1}).status_code == 401
