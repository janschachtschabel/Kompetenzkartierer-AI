"""A document's repair through the API (plan M1 8b, F6, F7): its owner starts it once X5 has checked
the document and a work package's findings ask for one - X6 asks those again, X5 checks anew
(app/pipeline/x6_repair.py). It is a model job as an extraction is, admitted alike, and shares the
extraction's key: a start while either waits or runs gives that one back. The findings name the
packages a repair would ask again, to the owner."""

from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.api.test_document_findings import finding
from tests.api.test_document_units import a_run, package
from tests.api.test_documents import (
    PUBLIC,
    a_conversion,
    an_account,
    client,
    end_job,
    make,
    rows,
    spend_all,
    tight,
    url,
)
from tests.db.l1 import add_node
from tests.support import make_settings, selector_client

pytestmark = pytest.mark.pg
__all__ = ["client", "tight", "url"]  # the fixtures, shared with test_documents

REPAIR = "extract.repair"


def extracted(
    client: TestClient, url: str, header: dict[str, str], owner: UUID, digest: bytes = b"\x02" * 32
) -> dict[str, Any]:
    """A document whose extraction has ended: X2 made two packages, X4 did E1 at its node."""
    started = make(client, url, header, a_conversion(url, owner, digest))
    end_job(url, started["job"]["id"], "done")
    document = started["document"]["id"]
    packages = [package("E1", "statements", (2, 2), ("Kompetenzen",)), package("E2", "none", (3, 3), ())]
    a_run(url, document, "X2", {"packages": [item.as_result() for item in packages]})
    x4 = a_run(url, document, "X4")
    with psycopg.connect(url, autocommit=True) as connection:
        node = add_node(connection, UUID(document), original_title="Kompetenzen")
        connection.execute(
            "INSERT INTO extraction_unit (document_id, unit_key, run_id, node_id, statements)"
            " VALUES (%s, 'E1', %s, %s, 0)",
            (document, x4, node),
        )
    return {"id": document, "job": started["job"]["id"], "x4": x4}


def checked(url: str, document: dict[str, Any], *, defect: bool = True) -> None:
    """X5 has checked it; X4's reading of the answer for E1 lost something, where ``defect``."""
    a_run(url, document["id"], "X5")
    if defect:
        finding(url, document["id"], document["x4"], "x4.unknown_block", "warning", document["id"],
                details={"unit": "E1"})  # fmt: skip


def repair(client: TestClient, document: str, header: dict[str, str] | None = None) -> Any:
    return client.post(f"/api/v1/documents/{document}/repair", headers=header or {})


def test_the_owner_starts_the_repair_of_a_checked_document(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    document = extracted(client, url, header, owner)
    checked(url, document)

    started = repair(client, document["id"], header)

    assert started.status_code == 202, started.text
    assert (started.json()["kind"], started.json()["status"]) == (REPAIR, "queued")
    assert rows(url, "SELECT kind, payload->>'document_id' FROM job WHERE id = %s", started.json()["id"]) == [
        (REPAIR, document["id"])
    ]
    read = client.get(f"/api/v1/documents/{document['id']}", headers=header).json()
    assert read["extraction"] == {
        "job_id": started.json()["id"],
        "kind": REPAIR,
        "status": "queued",
        "error_code": None,
    }
    audited = rows(url, "SELECT subject, details->>'job' FROM audit_log WHERE action = 'repair.start'")
    assert audited == [(f"document:{document['id']}", started.json()["id"])]


def test_a_repair_asked_while_the_extraction_or_a_repair_waits_or_runs_gives_that_one_back(
    client: TestClient, url: str
) -> None:
    # one job on a document's extraction at a time, whichever kind; following it asks for nothing more
    owner, header = an_account(url)
    waiting = make(client, url, header, a_conversion(url, owner))
    document = extracted(client, url, header, owner)
    checked(url, document)
    first = repair(client, document["id"], header).json()["id"]
    spend_all(url, owner)

    during_extraction = repair(client, waiting["document"]["id"], header)
    during_repair = repair(client, document["id"], header)
    extraction_during_repair = client.post(f"/api/v1/documents/{document['id']}/extraction", headers=header)

    assert (during_extraction.status_code, during_extraction.json()["id"]) == (200, waiting["job"]["id"])
    assert (during_repair.status_code, during_repair.json()["id"]) == (200, first)
    assert (extraction_during_repair.status_code, extraction_during_repair.json()["id"]) == (200, first)


def test_a_document_not_checked_or_with_nothing_to_repair_is_refused_and_no_job_made(
    client: TestClient, url: str
) -> None:
    # the document's reason comes before the admission's: the budget spent too is not said instead
    owner, header = an_account(url)
    unchecked = extracted(client, url, header, owner)
    sound = extracted(client, url, header, owner, b"\x03" * 32)
    checked(url, sound, defect=False)
    spend_all(url, owner)

    before_x5, nothing = repair(client, unchecked["id"], header), repair(client, sound["id"], header)

    assert (before_x5.status_code, before_x5.json()["code"]) == (409, "not_checked")
    assert (nothing.status_code, nothing.json()["code"]) == (409, "nothing_to_repair")
    assert rows(url, "SELECT count(*) FROM job WHERE kind = %s", REPAIR) == [(0,)]


def test_only_the_owner_starts_a_repair(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, admin = an_account(url, "Admin", ("admin",))
    _, stranger = an_account(url, "Fremde")
    document = extracted(client, url, header, owner)
    checked(url, document)

    by_editor, by_admin = repair(client, document["id"], editor), repair(client, document["id"], admin)
    by_stranger = repair(client, document["id"], stranger)

    assert (by_editor.status_code, by_editor.json()["code"]) == (403, "not_owner")
    assert (by_admin.status_code, by_admin.json()["code"]) == (403, "not_owner")  # charged to the owner
    assert (by_stranger.status_code, by_stranger.json()["code"]) == (404, "no_document")
    assert repair(client, document["id"]).status_code == 401
    assert rows(url, "SELECT count(*) FROM job WHERE kind = %s", REPAIR) == [(0,)]


def test_a_repair_is_admitted_as_any_model_job(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    document = extracted(client, url, header, owner)
    checked(url, document)
    spend_all(url, owner)

    refused = repair(client, document["id"], header)

    assert (refused.status_code, refused.json()["code"]) == (403, "no_budget")
    assert rows(url, "SELECT count(*) FROM job WHERE kind = %s", REPAIR) == [(0,)]


def test_a_repair_past_the_starts_a_minute_is_refused(tight: TestClient, url: str) -> None:
    owner, header = an_account(url)
    document = extracted(tight, url, header, owner)  # its extraction took the minute's one start
    checked(url, document)

    refused = repair(tight, document["id"], header)

    assert (refused.status_code, refused.json()["code"]) == (429, "too_many_starts")
    assert "Retry-After" in refused.headers


def test_a_repair_needs_the_entry_s_content_still_readable_by_its_owner(
    client: TestClient, url: str, tmp_path: Path
) -> None:
    # made while the content of entries of no account was open to accounts; closed since
    owner, header = an_account(url)
    made = a_conversion(url, owner)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE source SET owner_id = NULL WHERE id = %s", (made["source"],))
    opened = make_settings(database_url=url, storage_dir=tmp_path, third_party_markdown="accounts")
    with selector_client(create_app(opened), base_url=PUBLIC) as while_open:
        started = make(while_open, url, header, made)
    end_job(url, started["job"]["id"], "done")
    document = started["document"]["id"]
    a_run(url, document, "X5")

    refused = repair(client, document, header)

    assert (refused.status_code, refused.json()["code"]) == (403, "file_hidden")


def test_the_findings_name_the_packages_a_repair_would_ask_again_to_the_owner(
    client: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document = extracted(client, url, header, owner)
    finding(url, document["id"], document["x4"], "x4.unknown_block", "warning", document["id"],
            details={"unit": "E1"})  # fmt: skip
    path = f"/api/v1/documents/{document['id']}/findings"

    before_x5 = client.get(path, headers=header).json()["repairable"]
    a_run(url, document["id"], "X5")
    to_owner, to_editor = client.get(path, headers=header).json(), client.get(path, headers=editor).json()

    assert before_x5 == []  # a repair is refused until X5 has checked the document
    assert to_owner["repairable"] == ["E1"]
    assert to_editor["repairable"] == []  # only the owner starts one
    assert to_owner["findings"] == to_editor["findings"]
