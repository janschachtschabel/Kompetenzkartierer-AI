"""An account uploads a curriculum document: one register entry, the file stored once by its bytes.

The form is read only after the token is checked; a file too large, of no type a conversion
reads, or an archive bomb is refused with a code of its own, and leaves nothing behind.
"""

import asyncio
import hashlib
import tempfile
import tracemalloc
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.api import sources
from app.api.app import create_app
from app.db.migrate import migrate
from tests.sources.zip_helpers import make_zip
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
PDF = b"%PDF-1.7\n" + b"lehrplan " * 100


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "store"


def client_for(url: str, store: Path, **settings: Any) -> TestClient:
    app = create_app(make_settings(database_url=url, storage_dir=store, **settings))
    return selector_client(app, base_url=PUBLIC)


@pytest.fixture
def client(migrated: str, store: Path) -> Iterator[TestClient]:
    with client_for(migrated, store) as test_client:
        yield test_client


@pytest.fixture
def owner(migrated: str) -> tuple[UUID, dict[str, str]]:
    return seed_account(migrated, "Lehrkraft", ["nutzer"])


def rows(url: str, query: str, *values: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, values).fetchall()


def upload(
    client: TestClient, header: dict[str, str], data: bytes = PDF, name: str = "lehrplan.pdf", **form: str
) -> Any:
    return client.post("/api/v1/sources", headers=header, files={"file": (name, data)}, data=form)


def nothing_was_kept(url: str, store: Path) -> bool:
    counts = rows(url, "SELECT (SELECT count(*) FROM source), (SELECT count(*) FROM source_file)")
    return counts == [(0, 0)] and not any(store.rglob("*.*")) and not (store / "sources").exists()


def test_an_upload_becomes_a_register_entry_of_its_account(
    client: TestClient, migrated: str, store: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner
    digest = hashlib.sha256(PDF).hexdigest()

    answer = upload(client, header, title="Lehrplan Physik")

    assert answer.status_code == 201
    body = answer.json()
    assert body["title"] == "Lehrplan Physik"
    assert body["provenance"] == "upload"
    assert body["rights_status"] == "unklar"
    assert body["register_status"] == "acquired"
    assert body["file"] == {
        "name": "lehrplan.pdf",
        "mime": "application/pdf",
        "size": len(PDF),
        "sha256": digest,
    }
    assert rows(migrated, "SELECT owner_id, provenance FROM source WHERE id = %s", UUID(body["id"])) == [
        (account, "upload")
    ]
    assert (store / "sources" / digest).read_bytes() == PDF


def test_an_upload_is_acquired_by_its_account_and_audited(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    account, header = owner

    source_id = UUID(upload(client, header).json()["id"])

    assert rows(
        migrated, "SELECT method, account_id, received_name FROM acquisition WHERE source_id = %s", source_id
    ) == [("upload", account, "lehrplan.pdf")]
    assert rows(migrated, "SELECT action, subject FROM audit_log WHERE action = 'source.upload'") == [
        ("source.upload", f"source:{source_id}")
    ]


def test_without_a_title_the_file_name_names_the_entry(
    client: TestClient, owner: tuple[UUID, dict[str, str]]
) -> None:
    assert upload(client, owner[1], name="Lehrplan_Physik_RS.pdf").json()["title"] == "Lehrplan_Physik_RS"


def test_a_title_from_the_file_name_is_trimmed(
    client: TestClient, owner: tuple[UUID, dict[str, str]]
) -> None:
    assert upload(client, owner[1], name="Lehrplan Physik .pdf").json()["title"] == "Lehrplan Physik"


def test_the_name_an_upload_came_by_is_kept_without_its_folders(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    # a browser may send the path of the sender's own disk, and with it the sender's user name
    source_id = UUID(upload(client, owner[1], name="Lehrkraft/Downloads/lehrplan.pdf").json()["id"])

    assert rows(migrated, "SELECT received_name FROM acquisition WHERE source_id = %s", source_id) == [
        ("lehrplan.pdf",)
    ]


def test_the_same_file_from_two_accounts_is_stored_once(
    client: TestClient, migrated: str, store: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    other = seed_account(migrated, "Andere", ["nutzer"])[1]

    first = upload(client, owner[1]).json()
    second = upload(client, other, name="kopie.pdf").json()

    assert first["id"] != second["id"]
    assert rows(migrated, "SELECT count(*) FROM source_file") == [(1,)]
    assert len(list((store / "sources").iterdir())) == 1


def test_the_same_text_under_two_names_keeps_the_type_each_name_gives(
    client: TestClient, migrated: str, owner: tuple[UUID, dict[str, str]]
) -> None:
    # a text format is known by its name: the bytes are one file, the type is the entry's
    other = seed_account(migrated, "Andere", ["nutzer"])[1]
    text = b"<h1>Lehrplan</h1>\n"

    as_text = upload(client, owner[1], data=text, name="notiz.txt").json()["id"]
    as_html = upload(client, other, data=text, name="lehrplan.html").json()["id"]

    for source_id, header, mime in ((as_text, owner[1], "text/plain"), (as_html, other, "text/html")):
        assert client.get(f"/api/v1/sources/{source_id}", headers=header).json()["file"]["mime"] == mime
        download = client.get(f"/api/v1/sources/{source_id}/file", headers=header)
        assert download.headers["content-type"].split(";")[0] == mime
    assert rows(migrated, "SELECT count(*) FROM source_file") == [(1,)]


def test_a_name_with_folders_is_filed_under_its_last_part(
    client: TestClient, owner: tuple[UUID, dict[str, str]]
) -> None:
    assert upload(client, owner[1], name="../../etc/lehrplan.pdf").json()["file"]["name"] == "lehrplan.pdf"


def test_a_file_over_the_limit_is_refused_and_nothing_is_kept(
    migrated: str, store: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    with client_for(migrated, store, max_upload_mb=1) as client:
        answer = upload(client, owner[1], data=PDF + b"x" * 2**20)

    assert answer.status_code == 413
    assert answer.json()["code"] == "file_too_large"
    assert nothing_was_kept(migrated, store)


def test_a_file_over_the_limit_is_refused_by_its_size_before_it_is_read(
    migrated: str, store: Path, owner: tuple[UUID, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # the form parser counted the file as it spooled it: nothing of it needs reading to refuse it
    reads: list[int] = []
    read = UploadFile.read

    async def counted(self: UploadFile, size: int = -1) -> bytes:
        reads.append(size)
        return await read(self, size)

    monkeypatch.setattr(UploadFile, "read", counted)
    with client_for(migrated, store, max_upload_mb=1) as client:
        answer = upload(client, owner[1], data=PDF + b"x" * 2**20)

    assert answer.status_code == 413
    assert answer.json()["code"] == "file_too_large"
    assert reads == []


def test_a_file_is_held_once_in_memory_as_it_is_read() -> None:
    # read a MiB at a time into a bytearray and copied into bytes, it was held twice at the end
    size = 8 * 2**20
    with tempfile.SpooledTemporaryFile(max_size=2**20) as spooled:  # as the form parser spools it
        spooled.write(b"x" * size)
        spooled.seek(0)
        upload_file = UploadFile(spooled, size=size, filename="lehrplan.pdf")  # type: ignore[arg-type]

        tracemalloc.start()
        try:
            data = asyncio.run(sources._read(upload_file, 50 * 2**20))
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    assert len(data) == size
    assert peak < 1.5 * size


def test_a_file_of_no_type_a_conversion_reads_is_refused(
    client: TestClient, migrated: str, store: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    answer = upload(client, owner[1], data=b"MZ\x90\x00 an executable", name="lehrplan.pdf")

    assert answer.status_code == 415
    assert answer.json()["code"] == "unsupported_type"
    assert nothing_was_kept(migrated, store)


def test_an_archive_bomb_is_refused(
    client: TestClient, migrated: str, store: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    bomb = make_zip({"word/document.xml": b"\0" * (4 * 2**20)})

    answer = upload(client, owner[1], data=bomb, name="lehrplan.docx")

    assert answer.status_code == 413
    assert answer.json()["code"] == "archive_too_large"
    assert nothing_was_kept(migrated, store)


def test_a_form_without_a_file_is_refused(client: TestClient, owner: tuple[UUID, dict[str, str]]) -> None:
    answer = client.post("/api/v1/sources", headers=owner[1], data={"title": "ohne Datei"})

    assert answer.status_code == 422
    assert answer.json()["code"] == "file_missing"


def test_a_title_over_500_signs_is_refused(client: TestClient, owner: tuple[UUID, dict[str, str]]) -> None:
    answer = upload(client, owner[1], title="x" * 501)

    assert answer.status_code == 422
    assert answer.json()["code"] == "title_too_long"


@pytest.mark.parametrize(
    "title",
    ["Physik\N{RIGHT-TO-LEFT OVERRIDE}", "Physik\x00", "Physik\N{ZERO WIDTH SPACE}"],
    ids=["bidi", "nul", "zwsp"],
)
def test_a_title_with_hidden_signs_is_refused(
    client: TestClient, migrated: str, store: Path, owner: tuple[UUID, dict[str, str]], title: str
) -> None:
    answer = upload(client, owner[1], title=title)

    assert answer.status_code == 422
    assert answer.json()["code"] == "title_invalid"
    assert nothing_was_kept(migrated, store)


def test_a_visitor_cannot_upload(client: TestClient, migrated: str, store: Path) -> None:
    assert upload(client, {}).status_code == 401
    assert nothing_was_kept(migrated, store)


def test_the_body_is_read_only_after_the_token_is_checked(client: TestClient) -> None:
    # A body parameter on the route would make FastAPI read and parse the form before the token
    # check (the old app's audit, E-01): a visitor's upload then cost the API its whole body
    pulled: list[bytes] = []

    def body() -> Iterator[bytes]:
        for piece in (b'--kka\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n', PDF):
            pulled.append(piece)
            yield piece
        yield b"\r\n--kka--\r\n"

    answer = client.post(
        "/api/v1/sources", content=body(), headers={"Content-Type": "multipart/form-data; boundary=kka"}
    )

    assert answer.status_code == 401
    assert pulled == []


def test_the_spec_names_the_upload_form_and_its_refusals() -> None:
    # the route reads its form itself (after the token check), so FastAPI cannot see it
    operation = create_app(make_settings()).openapi()["paths"]["/api/v1/sources"]["post"]

    body = operation["requestBody"]
    form = body["content"]["multipart/form-data"]["schema"]
    assert body["required"] is True
    assert set(form["properties"]) == {"file", "title"} and form["required"] == ["file"]
    assert form["properties"]["file"]["format"] == "binary"
    assert form["properties"]["title"]["maxLength"] == 500
    responses = operation["responses"]
    # its account's uploads of the minute, or the address's failed sign-ins
    assert "too_many_uploads" in responses["429"]["description"]
    assert "failed sign-ins" in responses["429"]["description"]
    assert {"400", "413", "415", "422"} <= set(responses)


def test_uploads_past_the_account_s_limit_wait(
    migrated: str, store: Path, owner: tuple[UUID, dict[str, str]]
) -> None:
    with client_for(migrated, store, uploads_per_minute=2) as client:
        answers = [upload(client, owner[1], name=f"plan{index}.pdf") for index in range(3)]

    assert [answer.status_code for answer in answers] == [201, 201, 429]
    assert 1 <= int(answers[2].headers["Retry-After"]) <= 60
