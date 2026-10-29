"""The blocks of a document's own conversion, a page at a time (plan M1 9.9, Paket 9c J3): what its anchors
name, though the entry's file was fetched again since; read as the document is, its content as the entry's."""

from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.app import create_app
from app.core.ids import new_id
from tests.api.test_document_tree import a_document
from tests.api.test_documents import PUBLIC, a_conversion, an_account, client, end_job, make, url
from tests.support import make_settings, selector_client

pytestmark = pytest.mark.pg
__all__ = ["client", "url"]  # the fixtures, shared with test_documents


def a_new_file(url: str, source: str) -> None:
    """The entry's file fetched again and converted: its page 1 says something else."""
    with psycopg.connect(url, autocommit=True) as connection:
        file_id, conversion = new_id(), new_id()
        connection.execute(
            "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 1, 'sources/neu')",
            (file_id, b"\x09" * 32),
        )
        connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'conversion')", (conversion,))
        connection.execute(
            "INSERT INTO conversion (id, source_file_id, engine, engine_version, status, pages,"
            " printed_pages, markdown, finished_at)"
            " VALUES (%s, %s, 'pdfplumber', '0.11.10', 'done', 1, %s, '', now())",
            (conversion, file_id, Jsonb(["i"])),
        )
        connection.execute(
            "INSERT INTO document_block (conversion_id, block_id, page, last_page, seq, kind, text,"
            " x0, top, x1, bottom, bold, italic)"
            " VALUES (%s, 'p1-b1', 1, 1, 1, 'text', 'Neu', 0, 0, 1, 1, false, false)",
            (conversion,),
        )
        connection.execute("UPDATE source SET file_id = %s WHERE id = %s", (file_id, source))


def test_a_document_s_page_is_read_off_its_own_conversion_though_the_entry_s_file_changed(
    client: TestClient, url: str
) -> None:
    document, header = a_document(client, url)
    source = client.get(f"/api/v1/documents/{document}", headers=header).json()["source_id"]
    a_new_file(url, source)

    first = client.get(f"/api/v1/documents/{document}/blocks", params={"page": 1}, headers=header)
    second = client.get(f"/api/v1/documents/{document}/blocks", params={"page": 2}, headers=header)
    entry = client.get(f"/api/v1/sources/{source}/conversion/blocks", params={"page": 1}, headers=header)

    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["page"], body["pages"], body["printed_page"], body["continued"]) == (1, 2, None, [])
    assert [(block["id"], block["text"]) for block in body["blocks"]] == [("p1-b1", "Text")]
    assert [block["id"] for block in second.json()["blocks"]] == ["p2-b1"]
    assert [block["text"] for block in entry.json()["blocks"]] == ["Neu"]  # the entry's, today's file


def test_an_editor_reads_the_blocks_of_another_s_document(client: TestClient, url: str) -> None:
    document, _ = a_document(client, url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))

    answer = client.get(f"/api/v1/documents/{document}/blocks", params={"page": 2}, headers=editor)

    assert (answer.status_code, [block["id"] for block in answer.json()["blocks"]]) == (200, ["p2-b1"])


def test_a_page_past_the_end_or_a_document_the_caller_does_not_see_is_refused(
    client: TestClient, url: str
) -> None:
    document, header = a_document(client, url)
    _, stranger = an_account(url, "Fremde")
    path = f"/api/v1/documents/{document}/blocks"

    beyond = client.get(path, params={"page": 3}, headers=header)
    unseen = client.get(path, params={"page": 1}, headers=stranger)
    nought = client.get(path, params={"page": 0}, headers=header)

    assert (beyond.status_code, beyond.json()["code"]) == (404, "no_such_page")
    assert (unseen.status_code, unseen.json()["code"]) == (404, "no_document")
    assert nought.status_code == 422


def test_a_document_whose_entry_is_no_longer_the_owner_s_to_read_shows_no_blocks(
    client: TestClient, url: str, tmp_path: Path
) -> None:
    # made while THIRD_PARTY_MARKDOWN opened an entry of no account to every account, read while hidden
    owner, header = an_account(url)
    made = a_conversion(url, owner)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE source SET owner_id = NULL WHERE id = %s", (made["source"],))
    opened = make_settings(database_url=url, storage_dir=tmp_path, third_party_markdown="accounts")
    with selector_client(create_app(opened), base_url=PUBLIC) as while_open:
        started = make(while_open, url, header, made)
    end_job(url, started["job"]["id"], "done")

    hidden = client.get(
        f"/api/v1/documents/{started['document']['id']}/blocks", params={"page": 1}, headers=header
    )

    assert (hidden.status_code, hidden.json()["code"]) == (403, "file_hidden")
