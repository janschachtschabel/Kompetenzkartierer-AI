"""A document checked again through the API (plan M1 9; Paket 9 G9): POST /documents/{id}/check starts the
job extract.check - X5 again, no model, so no model job's admission - by the owner or the editors, once
X5 has checked the document; beside a job waiting or running it gives back that one, to whom may follow
it."""

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.api.test_document_units import a_run
from tests.api.test_documents import (
    a_conversion,
    an_account,
    client,
    end_job,
    make,
    rows,
    spend_all,
    started_beside_an_edit,
    url,
)

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents


def checked_once(client: TestClient, url: str) -> tuple[str, dict[str, str], UUID]:
    """A document X5 has checked, its extraction ended: its id, its owner's header and id."""
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    end_job(url, started["job"]["id"], "done")
    a_run(url, started["document"]["id"], "X5")
    return started["document"]["id"], header, owner


def test_the_owner_checks_the_document_again_with_no_budget_left(client: TestClient, url: str) -> None:
    document, header, owner = checked_once(client, url)
    spend_all(url, owner)  # a model job would be refused now

    answer = client.post(f"/api/v1/documents/{document}/check", headers=header)

    assert answer.status_code == 202, answer.text
    job = answer.json()
    assert (job["kind"], job["status"]) == ("extract.check", "queued")
    assert rows(url, "SELECT payload->>'document_id', unique_key FROM job WHERE id = %s", job["id"]) == [
        (document, f"extract.run:{document}")
    ]
    assert rows(url, "SELECT action, subject FROM audit_log WHERE action = 'check.start'") == [
        ("check.start", f"document:{document}")
    ]


def test_an_editor_checks_another_s_document_and_to_a_stranger_it_is_none(
    client: TestClient, url: str
) -> None:
    document, _, _ = checked_once(client, url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, stranger = an_account(url, "Fremde")

    by_editor = client.post(f"/api/v1/documents/{document}/check", headers=editor)
    by_stranger = client.post(f"/api/v1/documents/{document}/check", headers=stranger)

    assert (by_editor.status_code, by_editor.json()["kind"]) == (202, "extract.check")
    assert (by_stranger.status_code, by_stranger.json()["code"]) == (404, "no_document")
    assert client.post(f"/api/v1/documents/{document}/check").status_code == 401


def test_a_check_waits_for_the_tree_an_edit_holds(client: TestClient, url: str, tmp_path: Path) -> None:
    document, header, _ = checked_once(client, url)

    started = started_beside_an_edit(url, tmp_path, f"/api/v1/documents/{document}/check", header, document)

    assert started.status_code == 202, started.text


def test_a_document_x5_has_not_checked_is_left_to_its_extraction(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    end_job(url, started["job"]["id"], "failed")

    answer = client.post(f"/api/v1/documents/{started['document']['id']}/check", headers=header)

    assert (answer.status_code, answer.json()["code"]) == (409, "not_checked")


def test_beside_an_open_job_that_one_is_given_back_to_whom_may_follow_it(
    client: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))  # its extraction waits
    document = started["document"]["id"]
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, admin = an_account(url, "Verwaltung", ("admin",))

    to_owner = client.post(f"/api/v1/documents/{document}/check", headers=header)
    to_admin = client.post(f"/api/v1/documents/{document}/check", headers=admin)
    to_editor = client.post(f"/api/v1/documents/{document}/check", headers=editor)

    assert (to_owner.status_code, to_owner.json()["id"]) == (200, started["job"]["id"])
    assert (to_admin.status_code, to_admin.json()["id"]) == (200, started["job"]["id"])
    assert (to_editor.status_code, to_editor.json()["code"], to_editor.json()["details"]) == (
        409, "job_open", {},
    )  # fmt: skip
    assert rows(url, "SELECT count(*) FROM job WHERE kind = 'extract.check'") == [(0,)]
