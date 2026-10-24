"""A document's units through the API (plan M1 7b, F13): X2's work packages of the document, each with
how far X4 has come - done with its statements counted, open, read typed by X3 (frame) or not read
(none); none before X2. Who may read the document reads them; to another the document is none."""

from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.pipeline.x2_segments import WorkPackage
from tests.api.test_documents import a_conversion, an_account, client, make, url
from tests.db.l1 import CV, add_entity

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents


def package(key: str, job: Any, pages: tuple[int, int], path: tuple[str, ...]) -> WorkPackage:
    depth: Any = {"statements": "full", "frame": "typed", "none": "skip"}[job]
    return WorkPackage(key, None, 0, 0, f"p{pages[0]}-b1", f"p{pages[1]}-b1", pages, path, depth, job)


PACKAGES = [
    package("E0", "frame", (1, 1), ()),
    package("E1", "statements", (2, 3), ("Kompetenzen",)),
    package("E2", "none", (4, 4), ("Anhang",)),
    package("E3", "statements", (5, 6), ("Kompetenzen", "Optik")),
]


def a_run(url: str, document: str, stage: str, result: dict[str, Any] | None = None) -> UUID:
    with psycopg.connect(url, autocommit=True) as connection:
        run = add_entity(connection, "extraction_run")
        connection.execute(
            "INSERT INTO extraction_run (id, document_id, stage_scheme, stage_iri, outcome, finished_at,"
            " result) VALUES (%s, %s, %s, %s, 'done', now(), %s)",
            (run, document, CV + "Stages", CV + "stage_" + stage, Jsonb(result or {})),
        )
    return run


def test_a_document_s_units_are_read_with_how_far_x4_has_come(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    document = make(client, url, header, a_conversion(url, owner))["document"]["id"]
    a_run(url, document, "X2", {"packages": [item.as_result() for item in PACKAGES]})
    x4 = a_run(url, document, "X4")
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO extraction_unit (document_id, unit_key, run_id, statements)"
            " VALUES (%s, 'E1', %s, 3)",
            (document, x4),
        )

    answer = client.get(f"/api/v1/documents/{document}/units", headers=header)

    assert answer.status_code == 200, answer.text
    assert answer.json() == [
        {"key": "E0", "path": [], "pages": [1, 1], "state": "frame", "statements": None},
        {"key": "E1", "path": ["Kompetenzen"], "pages": [2, 3], "state": "done", "statements": 3},
        {"key": "E2", "path": ["Anhang"], "pages": [4, 4], "state": "none", "statements": None},
        {"key": "E3", "path": ["Kompetenzen", "Optik"], "pages": [5, 6], "state": "open", "statements": None},
    ]


def test_a_document_before_x2_has_no_units(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    document = make(client, url, header, a_conversion(url, owner))["document"]["id"]

    answer = client.get(f"/api/v1/documents/{document}/units", headers=header)

    assert (answer.status_code, answer.json()) == (200, [])


def test_to_one_who_may_not_read_the_document_its_units_are_none(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    document = make(client, url, header, a_conversion(url, owner))["document"]["id"]
    _, stranger = an_account(url, "Fremde")

    assert client.get(f"/api/v1/documents/{document}/units", headers=stranger).status_code == 404
    assert client.get(f"/api/v1/documents/{document}/units").status_code == 401
