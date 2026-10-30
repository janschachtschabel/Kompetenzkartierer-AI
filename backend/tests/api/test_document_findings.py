"""A document's findings through the API (plan M1 8b): what the stages found on it, gravest first, each
with the kind and the wording or title of the row it is about, the counts of all beside; who may read
the document reads them, to another the document is none."""

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from tests.api.test_document_units import a_run
from tests.api.test_documents import a_conversion, an_account, client, hidden_from_its_owner, make, url
from tests.db.l1 import add_node, add_statement

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents


def finding(url: str, document: str, run: Any, rule: str, severity: str, focus: Any, **more: Any) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO validation_finding (id, document_id, run_id, rule, severity, focus_id, path,"
            " message, details) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                uuid.uuid4(), document, run, rule, severity, focus, more.get("path"),
                more.get("message", rule), Jsonb(more.get("details", {})),
            ),
        )  # fmt: skip


def test_a_document_s_findings_are_read_gravest_first_with_the_rows_they_are_about(
    client: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    document = make(client, url, header, a_conversion(url, owner))["document"]["id"]
    with psycopg.connect(url, autocommit=True) as connection:
        node = add_node(connection, uuid.UUID(document), original_title="Optik")
        statement = add_statement(connection, uuid.UUID(document), node, verbatim="Die Lernenden messen.")
    x4, x5 = a_run(url, document, "X4"), a_run(url, document, "X5")
    finding(url, document, x5, "x5.unit_without_statements", "info", document, details={"unit": "E3"})
    finding(url, document, x5, "x5.retired_value", "warning", node, path="cur:nodeType")
    finding(url, document, x4, "x4.unknown_block", "warning", document, details={"unit": "E1"})
    finding(url, document, x5, "x5.wording_not_found", "violation", statement, message="not in the blocks")
    finding(url, document, x5, "shacl.StatementShape", "violation", statement,
            message="Aussage ohne Adressat.", details={"lang": "de"})  # fmt: skip

    answer = client.get(f"/api/v1/documents/{document}/findings", headers=header)

    assert answer.status_code == 200, answer.text
    assert answer.json() == {
        "counts": {"violation": 2, "warning": 2, "info": 1},
        "findings": [
            {"rule": "shacl.StatementShape", "severity": "violation", "stage": "X5",
             "focus": {"kind": "statement", "id": str(statement), "label": "Die Lernenden messen."},
             "path": None, "message": "Aussage ohne Adressat.", "message_lang": "de", "unit": None},
            {"rule": "x5.wording_not_found", "severity": "violation", "stage": "X5",
             "focus": {"kind": "statement", "id": str(statement), "label": "Die Lernenden messen."},
             "path": None, "message": "not in the blocks", "message_lang": None, "unit": None},
            {"rule": "x4.unknown_block", "severity": "warning", "stage": "X4",
             "focus": {"kind": "document", "id": document, "label": None},
             "path": None, "message": "x4.unknown_block", "message_lang": None, "unit": "E1"},
            {"rule": "x5.retired_value", "severity": "warning", "stage": "X5",
             "focus": {"kind": "node", "id": str(node), "label": "Optik"},
             "path": "cur:nodeType", "message": "x5.retired_value", "message_lang": None, "unit": None},
            {"rule": "x5.unit_without_statements", "severity": "info", "stage": "X5",
             "focus": {"kind": "document", "id": document, "label": None},
             "path": None, "message": "x5.unit_without_statements", "message_lang": None, "unit": "E3"},
        ],
        "truncated": False,
        "repairable": [],  # X2 parted the document into no packages
    }  # fmt: skip


def test_a_document_nothing_was_found_on_has_no_findings(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    document = make(client, url, header, a_conversion(url, owner))["document"]["id"]

    answer = client.get(f"/api/v1/documents/{document}/findings", headers=header)

    assert (answer.status_code, answer.json()) == (
        200,
        {
            "counts": {"violation": 0, "warning": 0, "info": 0},
            "findings": [],
            "truncated": False,
            "repairable": [],
        },
    )


def test_the_editors_read_a_document_s_findings_and_to_another_it_is_none(
    client: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    document = make(client, url, header, a_conversion(url, owner))["document"]["id"]
    finding(url, document, a_run(url, document, "X5"), "x5.shacl_timeout", "violation", document)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, stranger = an_account(url, "Fremde")

    assert (
        client.get(f"/api/v1/documents/{document}/findings", headers=editor).json()["counts"]["violation"]
        == 1
    )
    assert client.get(f"/api/v1/documents/{document}/findings", headers=stranger).status_code == 404
    assert client.get(f"/api/v1/documents/{document}/findings").status_code == 401


def test_the_findings_of_a_document_whose_entry_is_no_longer_the_owner_s_are_the_editors_alone(
    client: TestClient, url: str
) -> None:
    # a finding names the wording or the title of its row: the entry's content
    owner, header = an_account(url)
    document = make(client, url, header, a_conversion(url, owner))["document"]["id"]
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    hidden_from_its_owner(url, document)

    hidden = client.get(f"/api/v1/documents/{document}/findings", headers=header)

    assert (hidden.status_code, hidden.json()["code"]) == (403, "file_hidden")
    assert client.get(f"/api/v1/documents/{document}/findings", headers=editor).status_code == 200
