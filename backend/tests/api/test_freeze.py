"""A document frozen through the API (plan M1 9.6, Paket 9b H5): by the editors alone, once it is ready -
its work, issuer and edition set, X5's check of all it says, its violations accepted - and refused with
the reason why not; frozen, it is edited no more."""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.api.test_document_tree import a_document
from tests.api.test_document_units import a_run
from tests.api.test_documents import PUBLIC, an_account, client, end_job, rows, url
from tests.api.test_node_editing import a_node
from tests.api.test_statement_editing import a_statement
from tests.support import make_settings, selector_client

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents

BASE = "https://example.org/kk/"
DOC = BASE + "doc/de-nw/ministerium/lp-physik/2024"
WORK = {"title": "Lehrplan Physik", "region": "DE-NW", "short_title": "lp-physik"}
AREA_TYPE = "https://w3id.org/wlo/curriculum/profile/school#Inhaltsbereich"


@pytest.fixture
def freezing(url: str, tmp_path: Path) -> Iterator[TestClient]:
    """The service with a base to name what it freezes under."""
    app = create_app(make_settings(database_url=url, storage_dir=tmp_path, iri_base=BASE))
    with selector_client(app, base_url=PUBLIC) as test_client:
        yield test_client


def ready(client: TestClient, url: str, editor: dict[str, str]) -> tuple[str, dict[str, str]]:
    """A document with a node and a statement, its work, issuer and edition set and X5 done after: one to
    freeze; with its owner's header."""
    document, owner = a_document(client, url)
    a_statement(url, document, a_node(url, document, code="LF 1"))
    assert client.patch(f"/api/v1/documents/{document}/work", headers=editor, json=WORK).status_code == 200
    metadata = {"issuer": "Ministerium", "edition": "2024"}
    assert client.patch(f"/api/v1/documents/{document}", headers=editor, json=metadata).status_code == 200
    a_run(url, document, "X5")
    return document, owner


def a_violation(url: str, document: str) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO validation_finding (id, document_id, rule, severity, focus_id, message)"
            " VALUES (gen_random_uuid(), %s, 'shacl.DocumentShape', 'violation', %s, 'Verstoß')",
            (document, document),
        )


def test_an_editor_freezes_a_ready_document_and_its_tree_is_edited_no_more(
    freezing: TestClient, url: str
) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document, _ = ready(freezing, url, editor)

    # accepted, though there is no violation: none is
    answer = freezing.post(
        f"/api/v1/documents/{document}/freeze", headers=editor, json={"accept_violations": True}
    )

    assert (answer.status_code, answer.json()["id"]) == (200, document), answer.text
    assert rows(url, "SELECT iri, frozen_at IS NOT NULL FROM document WHERE id = %s", document) == [
        (DOC, True)
    ]
    assert rows(url, "SELECT iri FROM node WHERE document_id = %s", document) == [(DOC + "/lf-1",)]
    assert rows(url, "SELECT iri FROM statement WHERE document_id = %s", document) == [(DOC + "/lf-1/s-1",)]
    assert rows(url, "SELECT details FROM audit_log WHERE action = 'document.freeze'") == [
        ({"revision": 1, "violations": 0, "accepted": False},)
    ]
    tree = freezing.get(f"/api/v1/documents/{document}/tree", headers=editor).json()
    assert (tree["editable"], tree["reviewable"]) == (False, False)
    [top] = tree["nodes"]
    assert (top["iri"], top["statements"][0]["iri"]) == (DOC + "/lf-1", DOC + "/lf-1/s-1")
    read = freezing.get(f"/api/v1/documents/{document}", headers=editor).json()
    assert {key: read[key] for key in ("iri", "revision", "copy_of", "issuer", "edition")} == {
        "iri": DOC, "revision": 1, "copy_of": None, "issuer": "Ministerium", "edition": "2024",
    }  # fmt: skip
    assert read["frozen_at"] is not None
    assert {key: value for key, value in read["work"].items() if key != "id"} == WORK | {
        "iri": BASE + "work/de-nw/lp-physik"
    }


def test_freezing_is_the_editors_and_violations_are_frozen_with_once_they_accept_them(
    freezing: TestClient, url: str
) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, stranger = an_account(url, "Fremde")
    document, owner = ready(freezing, url, editor)
    path = f"/api/v1/documents/{document}/freeze"
    a_violation(url, document)

    by_owner = freezing.post(path, headers=owner, json={})
    by_stranger = freezing.post(path, headers=stranger, json={})
    held = freezing.post(path, headers=editor, json={})
    accepted = freezing.post(path, headers=editor, json={"accept_violations": True})
    again = freezing.post(path, headers=editor, json={"accept_violations": True})

    assert (by_owner.status_code, by_owner.json()["code"]) == (403, "not_editor")
    assert (by_stranger.status_code, by_stranger.json()["code"]) == (404, "no_document")
    assert (held.status_code, held.json()["code"], held.json()["details"]) == (
        409, "has_violations", {"violations": 1},
    )  # fmt: skip
    assert accepted.status_code == 200, accepted.text
    assert (again.status_code, again.json()["code"]) == (409, "frozen")
    assert rows(url, "SELECT details->>'accepted' FROM audit_log WHERE action = 'document.freeze'") == [
        ("true",)
    ]


def test_a_freeze_without_a_body_accepts_no_violations(freezing: TestClient, url: str) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document, _ = ready(freezing, url, editor)
    a_violation(url, document)
    path = f"/api/v1/documents/{document}/freeze"

    answer = freezing.post(path, headers=editor)
    # accepted in so many words: a "yes" or a 1 is no acceptance
    loose = [freezing.post(path, headers=editor, json={"accept_violations": said}) for said in ("yes", 1)]

    assert (answer.status_code, answer.json()["code"]) == (409, "has_violations"), answer.text
    assert [(said.status_code, said.json()["code"]) for said in loose] == [(422, "validation_failed")] * 2


def test_a_document_not_ready_is_refused_with_what_it_lacks(
    freezing: TestClient, client: TestClient, url: str
) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document, _ = ready(freezing, url, editor)
    path = f"/api/v1/documents/{document}/freeze"

    unnamed = client.post(path, headers=editor, json={})  # a service without IRI_BASE
    freezing.patch(f"/api/v1/documents/{document}", headers=editor, json={"edition": None})
    incomplete = freezing.post(path, headers=editor, json={})
    freezing.patch(f"/api/v1/documents/{document}", headers=editor, json={"edition": "2024"})
    unchecked = freezing.post(path, headers=editor, json={})  # the edits owe X5 a check

    assert (unnamed.status_code, unnamed.json()["code"]) == (409, "no_iri_base")
    assert (incomplete.status_code, incomplete.json()["code"], incomplete.json()["details"]) == (
        409, "incomplete", {"missing": ["edition"]},
    )  # fmt: skip
    assert (unchecked.status_code, unchecked.json()["code"], unchecked.json()["details"]) == (
        409, "check_owed", {"unchecked": 0},
    )  # fmt: skip
    assert rows(url, "SELECT frozen_at FROM document WHERE id = %s", document) == [(None,)]


def test_a_document_beside_its_job_or_before_x4_is_not_frozen(freezing: TestClient, url: str) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    busy, _ = a_document(freezing, url, ended=False)
    early, _ = a_document(freezing, url, extracted=False, name="Lehrkraft 2", digest=b"\x02" * 32)

    beside = freezing.post(f"/api/v1/documents/{busy}/freeze", headers=editor, json={})
    before = freezing.post(f"/api/v1/documents/{early}/freeze", headers=editor, json={})

    assert (beside.status_code, beside.json()["code"]) == (409, "job_open")
    assert (before.status_code, before.json()["code"]) == (409, "not_extracted")


def test_an_editor_copies_a_frozen_document_as_its_next_revision(freezing: TestClient, url: str) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document, owner = ready(freezing, url, editor)
    assert freezing.post(f"/api/v1/documents/{document}/freeze", headers=editor, json={}).status_code == 200
    path = f"/api/v1/documents/{document}/draft-copy"

    by_owner = freezing.post(path, headers=owner)
    copied = freezing.post(path, headers=editor)
    again = freezing.post(path, headers=editor)

    assert (by_owner.status_code, by_owner.json()["code"]) == (403, "not_editor")
    assert copied.status_code == 201, copied.text
    copy = copied.json()["id"]
    assert copy != document
    assert (again.status_code, again.json()["code"], again.json()["details"]) == (
        409, "draft_open", {"document_id": copy},
    )  # fmt: skip
    assert rows(url, "SELECT iri, revision, copy_of::text, frozen_at FROM document WHERE id = %s", copy) == [
        (DOC, 2, document, None)
    ]
    body = copied.json()
    assert (body["iri"], body["revision"], body["copy_of"], body["frozen_at"]) == (DOC, 2, document, None)
    assert rows(url, "SELECT subject, details FROM audit_log WHERE action = 'document.copy'") == [
        (f"document:{document}", {"copy": copy, "revision": 2})
    ]


def test_a_draft_is_not_copied(freezing: TestClient, url: str) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document, _ = ready(freezing, url, editor)

    answer = freezing.post(f"/api/v1/documents/{document}/draft-copy", headers=editor)

    assert (answer.status_code, answer.json()["code"]) == (409, "not_frozen")
    assert rows(url, "SELECT count(*) FROM document") == [(1,)]


def test_a_copy_today_s_vocabulary_refuses_is_refused_with_the_check_it_fails(
    freezing: TestClient, url: str
) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document, _ = ready(freezing, url, editor)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE node SET node_type_iri = %s WHERE code = 'LF 1'", (AREA_TYPE,))
    assert freezing.post(f"/api/v1/documents/{document}/freeze", headers=editor, json={}).status_code == 200
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE vocab_concept SET broader = '{}' WHERE iri = %s", (AREA_TYPE,))

    answer = freezing.post(f"/api/v1/documents/{document}/draft-copy", headers=editor)

    assert (answer.status_code, answer.json()["code"], answer.json()["details"]) == (
        409, "vocabulary_changed", {"check": "node_type_fits"},
    )  # fmt: skip
    assert rows(url, "SELECT count(*) FROM audit_log WHERE action = 'document.copy'") == [(0,)]


def test_a_copy_is_edited_and_checked_and_neither_it_nor_a_frozen_one_extracted_again(
    freezing: TestClient, url: str
) -> None:
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    document, owner = ready(freezing, url, editor)
    assert freezing.post(f"/api/v1/documents/{document}/freeze", headers=editor, json={}).status_code == 200
    copy = freezing.post(f"/api/v1/documents/{document}/draft-copy", headers=editor).json()["id"]

    tree = freezing.get(f"/api/v1/documents/{copy}/tree", headers=editor).json()
    check = freezing.post(f"/api/v1/documents/{copy}/check", headers=editor)  # no X5 of its own yet
    end_job(url, check.json()["id"], "done")
    starts = {
        (name, kind): freezing.post(f"/api/v1/documents/{target}/{kind}", headers=owner)
        for name, target in (("copy", copy), ("frozen", document))
        for kind in ("extraction", "repair")
    }

    assert (tree["editable"], tree["reviewable"]) == (True, True)
    assert (check.status_code, check.json()["kind"]) == (202, "extract.check")
    assert {key: (answer.status_code, answer.json()["code"]) for key, answer in starts.items()} == {
        ("copy", "extraction"): (409, "not_extractable"),
        ("copy", "repair"): (409, "not_extractable"),
        ("frozen", "extraction"): (409, "frozen"),
        ("frozen", "repair"): (409, "frozen"),
    }
