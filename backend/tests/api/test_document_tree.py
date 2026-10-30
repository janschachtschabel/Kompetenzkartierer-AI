"""A document's tree through the API (plan M1 9.2): its nodes and statements with the fields of the editor's
form, their anchors, the findings on each node counted, the nodes and statements counted by review
status, and whether the caller may edit and review them now - not beside an open job, not once the
document is frozen - and, where none may, why. Who may read the document and its entry's content reads it;
to another it is none."""

import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.app import create_app
from app.vocab.forms import NODE_FIELDS, STATEMENT_FIELDS
from tests.api.test_document_findings import finding
from tests.api.test_document_units import a_run
from tests.api.test_documents import PUBLIC, a_conversion, an_account, client, end_job, make, url
from tests.db.l1 import CV, add_node, add_statement
from tests.support import make_settings, selector_client

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents

SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
PROPOSED, CONFIRMED, REJECTED = (CV + "rev_" + status for status in ("proposed", "confirmed", "rejected"))


def a_document(
    client: TestClient,
    url: str,
    *,
    ended: bool = True,
    extracted: bool = True,
    name: str = "Lehrkraft",
    digest: bytes = b"\x01" * 32,
) -> tuple[str, dict[str, str]]:
    """A document of a new account's with that account's header; its extraction ended, unless not, and X4
    done - every package read - unless not."""
    owner, header = an_account(url, name)
    started = make(client, url, header, a_conversion(url, owner, digest))
    if ended:
        end_job(url, started["job"]["id"], "done")
    if extracted:
        a_run(url, started["document"]["id"], "X4")
    return started["document"]["id"], header


def tree(client: TestClient, document: str, header: dict[str, str]) -> dict[str, Any]:
    answer = client.get(f"/api/v1/documents/{document}/tree", headers=header)
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def test_a_document_s_tree_is_read_with_its_form_s_fields_anchors_and_findings(
    client: TestClient, url: str
) -> None:
    document, header = a_document(client, url)
    with psycopg.connect(url, autocommit=True) as connection:
        area = add_node(
            connection, uuid.UUID(document), original_title="Optik", node_type_iri=SCHOOL + "Inhaltsbereich",
            obligation_scheme=CV + "Obligations", obligation_iri=CV + "obl_binding",
        )  # fmt: skip
        unit = add_node(connection, uuid.UUID(document), area, function_iri=CV + "fn_unit", code="1")
        said = add_statement(
            connection, uuid.UUID(document), unit, verbatim="messen Lichtstärken.", lead_in="Die Lernenden",
            details=Jsonb({"codeText": "K1"}), review_status_iri=REJECTED,
        )  # fmt: skip
    finding(url, document, None, "x5.retired_value", "warning", area)
    finding(url, document, None, "x5.wording_not_found", "violation", said)

    read = tree(client, document, header)

    [top] = read["nodes"]
    assert list(top["fields"]) == [field.key for field in NODE_FIELDS]
    assert top["fields"] == {
        "original_title": "Optik", "function": CV + "fn_area", "node_type": SCHOOL + "Inhaltsbereich",
        "code": None, "obligation": CV + "obl_binding",
    }  # fmt: skip
    assert (top["id"], top["position"], top["code_assigned"], top["origin"], top["review_status"]) == (
        str(area), 1, False, CV + "orig_source", PROPOSED,
    )  # fmt: skip
    assert (top["revision"], top["anchors"], top["statements"]) == (1, [], [])
    assert top["findings"] == {"violation": 0, "warning": 1, "info": 0}
    [child] = top["children"]
    assert (child["fields"]["code"], child["findings"], child["children"]) == (
        "1", {"violation": 1, "warning": 0, "info": 0}, [],
    )  # fmt: skip
    [statement] = child["statements"]
    assert list(statement["fields"]) == [field.key for field in STATEMENT_FIELDS]
    assert statement["fields"] == {
        "verbatim": "messen Lichtstärken.", "lead_in": "Die Lernenden",
        "statement_kind": CV + "kind_learningOutcome", "subkind": None, "addressees": [CV + "addr_learner"],
        "obligation": None, "codeText": "K1", "levelText": None, "timeText": None, "contextText": None,
        "referenceMarker": None, "exampleText": None, "purposeText": None,
    }  # fmt: skip
    assert (statement["id"], statement["position"], statement["review_status"], statement["revision"]) == (
        str(said), 1, REJECTED, 1,
    )  # fmt: skip
    assert statement["by_hand"] is False  # a run's: taking it away rejects it
    [anchor] = statement["anchors"]
    assert {key: value for key, value in anchor.items() if key != "id"} == {
        "page_start": 1, "page_end": None, "printed_page": None, "quote": None, "match_kind": None,
        "match_score": None, "blocks": [],
    }  # fmt: skip
    assert read["counts"] == {
        "nodes": {PROPOSED: 2, CONFIRMED: 0, REJECTED: 0},
        "statements": {PROPOSED: 0, CONFIRMED: 0, REJECTED: 1},
    }


def test_the_owner_edits_a_tree_and_the_editors_edit_and_review_it(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, admin = an_account(url, "Verwaltung", ("admin",))

    assert {key: tree(client, document, owner)[key] for key in ("editable", "reviewable", "closed")} == {
        "editable": True,
        "reviewable": False,
        "closed": None,
    }
    for header in (editor, admin):
        read = tree(client, document, header)
        assert (read["editable"], read["reviewable"]) == (True, True)


def test_a_tree_beside_an_open_job_is_edited_and_reviewed_by_none(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url, ended=False)
    _, editor = an_account(url, "Redaktion", ("redaktion",))

    for header in (owner, editor):
        read = tree(client, document, header)
        assert (read["editable"], read["reviewable"], read["closed"]) == (False, False, "job_open")


def test_a_tree_whose_extraction_has_not_read_every_package_is_edited_by_none(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url, extracted=False)  # X4 still writes at its nodes
    _, editor = an_account(url, "Redaktion", ("redaktion",))

    for header in (owner, editor):
        read = tree(client, document, header)
        assert (read["editable"], read["reviewable"], read["closed"]) == (False, False, "not_extracted")


def test_a_frozen_document_s_tree_is_edited_and_reviewed_by_none(client: TestClient, url: str) -> None:
    document, owner = a_document(client, url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "UPDATE document SET iri = 'https://example.org/curriculum/1', frozen_at = now() WHERE id = %s",
            (document,),
        )

    for header in (owner, editor):
        read = tree(client, document, header)
        assert (read["editable"], read["reviewable"], read["closed"]) == (False, False, "frozen")


def test_a_tree_closed_for_several_reasons_names_the_one_that_lasts_longest(
    client: TestClient, url: str
) -> None:
    # frozen stays; a job ends soon and may be the extraction that has yet to read every package
    running, owner = a_document(client, url, ended=False, extracted=False)
    frozen, other = a_document(client, url, ended=False, name="Andere", digest=b"\x02" * 32)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "UPDATE document SET iri = 'https://example.org/curriculum/2', frozen_at = now() WHERE id = %s",
            (frozen,),
        )

    assert tree(client, running, owner)["closed"] == "job_open"
    assert tree(client, frozen, other)["closed"] == "frozen"


def test_a_tree_whose_entry_is_no_longer_the_owner_s_to_read_is_refused_to_the_owner_alone(
    client: TestClient, url: str, tmp_path: Path
) -> None:
    # made while THIRD_PARTY_MARKDOWN opened an entry of no account to every account, read while hidden:
    # its statements are the entry's content in the document's words
    owner, header = an_account(url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    made = a_conversion(url, owner)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE source SET owner_id = NULL WHERE id = %s", (made["source"],))
    opened = make_settings(database_url=url, storage_dir=tmp_path, third_party_markdown="accounts")
    with selector_client(create_app(opened), base_url=PUBLIC) as while_open:
        started = make(while_open, url, header, made)
    end_job(url, started["job"]["id"], "done")
    path = f"/api/v1/documents/{started['document']['id']}/tree"

    hidden = client.get(path, headers=header)

    assert (hidden.status_code, hidden.json()["code"]) == (403, "file_hidden")
    assert client.get(path, headers=editor).status_code == 200


def test_a_tree_without_nodes_is_empty_and_to_another_the_document_is_none(
    client: TestClient, url: str
) -> None:
    document, owner = a_document(client, url)
    _, stranger = an_account(url, "Fremde")

    read = tree(client, document, owner)

    assert (read["nodes"], read["counts"]["nodes"][PROPOSED]) == ([], 0)
    answer = client.get(f"/api/v1/documents/{document}/tree", headers=stranger)
    assert (answer.status_code, answer.json()["code"]) == (404, "no_document")
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/tree", headers=owner).status_code == 404
    assert client.get(f"/api/v1/documents/{document}/tree").status_code == 401
