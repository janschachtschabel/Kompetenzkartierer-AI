"""Documents and their extraction through the API (plan M1 7.5, 7a): a document is made of an entry's
finished conversion and its extraction started at once; a start of a document whose extraction is
waiting or running gives that one back, as does a document asked of a conversion one of the
account's documents is being extracted from; only the owner, who is charged, starts; who may read
the document reads it and its runs."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api import documents as documents_api
from app.api import limits
from app.api.app import create_app
from app.db.migrate import migrate
from app.pipeline.extraction import KIND, unique_key
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.l1 import CV, add_conversion, add_document, add_entity
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"


@pytest.fixture
def url(database_url: str) -> str:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    return database_url


@pytest.fixture
def client(url: str, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(database_url=url, storage_dir=tmp_path))
    with selector_client(app, base_url=PUBLIC) as test_client:
        yield test_client


def an_account(
    url: str, name: str = "Lehrkraft", roles: tuple[str, ...] = ("nutzer",), token_limit: int | None = None
) -> tuple[UUID, dict[str, str]]:
    account, header = seed_account(url, name, list(roles))
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO quota (account_id, token_limit) VALUES (%s, %s)", (account, token_limit)
        )
    return account, header


def a_conversion(url: str, owner: UUID, digest: bytes = b"\x01" * 32) -> dict[str, UUID]:
    with psycopg.connect(url, autocommit=True) as connection:
        return add_conversion(connection, digest, owner)


def asked(made: dict[str, UUID], **changes: Any) -> dict[str, Any]:
    return {
        "source_id": str(made["source"]),
        "conversion_id": str(made["conversion"]),
        "sector": "school",
        "regions": ["DE-NW"],
    } | changes


def rows(url: str, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


def test_a_document_is_made_of_a_finished_conversion_and_its_extraction_started(
    client: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    made = a_conversion(url, owner)

    answer = client.post("/api/v1/documents", headers=header, json=asked(made))

    assert answer.status_code == 202, answer.text
    document, job = answer.json()["document"], answer.json()["job"]
    assert (document["sector"], document["regions"], document["title"], document["own"]) == (
        "school",
        ["DE-NW"],
        None,
        True,
    )
    assert (job["kind"], job["status"]) == (KIND, "queued")
    assert document["extraction"] == {"job_id": job["id"], "status": "queued"}
    assert rows(url, "SELECT lane, payload, unique_key FROM job WHERE id = %s", job["id"]) == [
        (str(owner), {"document_id": document["id"]}, unique_key(UUID(document["id"])))
    ]
    assert rows(url, "SELECT action, subject FROM audit_log WHERE action = 'document.create'") == [
        ("document.create", f"document:{document['id']}")
    ]


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"sector": "kindergarten"}, 422, "unknown_sector"),
        ({"regions": ["DE-NW", "ZZ"]}, 422, "unknown_region"),
        ({"conversion_id": "01900000-0000-7000-8000-000000000001"}, 404, "no_conversion"),
    ],
    ids=["sector", "region", "conversion"],
)
def test_a_document_asked_wrongly_is_refused_and_nothing_is_made(
    client: TestClient, url: str, changes: dict[str, Any], status: int, code: str
) -> None:
    owner, header = an_account(url)
    made = a_conversion(url, owner)

    answer = client.post("/api/v1/documents", headers=header, json=asked(made, **changes))

    assert (answer.status_code, answer.json()["code"]) == (status, code)
    assert rows(url, "SELECT count(*) FROM document") == [(0,)]
    assert rows(url, "SELECT count(*) FROM job") == [(0,)]


def test_another_account_s_conversion_is_no_conversion_for_a_document(client: TestClient, url: str) -> None:
    owner, _ = an_account(url)
    _, stranger = an_account(url, "Fremde")
    made = a_conversion(url, owner)

    answer = client.post("/api/v1/documents", headers=stranger, json=asked(made))

    assert (answer.status_code, answer.json()["code"]) == (404, "no_conversion")


def test_an_account_without_budget_makes_no_document(client: TestClient, url: str) -> None:
    # the admission refuses after the document was made: the transaction takes it back
    owner, header = an_account(url, token_limit=0)
    made = a_conversion(url, owner)

    answer = client.post("/api/v1/documents", headers=header, json=asked(made))

    assert (answer.status_code, answer.json()["code"]) == (403, "no_budget")
    assert rows(url, "SELECT count(*) FROM document") == [(0,)]


def test_a_visitor_makes_no_document(client: TestClient, url: str) -> None:
    owner, _ = an_account(url)
    made = a_conversion(url, owner)

    assert client.post("/api/v1/documents", json=asked(made)).status_code == 401


def make(client: TestClient, url: str, header: dict[str, str], made: dict[str, UUID]) -> dict[str, Any]:
    answer = client.post("/api/v1/documents", headers=header, json=asked(made))
    assert answer.status_code == 202, answer.text
    return dict(answer.json())


def end_job(url: str, job_id: str, status: str) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE job SET status = %s, finished_at = now() WHERE id = %s", (status, job_id))


def spend_all(url: str, owner: UUID) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE quota SET token_limit = 0 WHERE account_id = %s", (owner,))


def test_a_document_asked_of_a_conversion_whose_extraction_waits_gives_that_one_back(
    client: TestClient, url: str
) -> None:
    # one extraction of the same PDF at a time for an account: a second form sent, a request sent
    # again, is led to the one waiting or running - whatever sector it names
    owner, header = an_account(url)
    made = a_conversion(url, owner)
    started = make(client, url, header, made)
    starts = rows(url, "SELECT count(*) FROM rate_event")[0][0]

    again = client.post("/api/v1/documents", headers=header, json=asked(made, sector="vocational"))

    assert again.status_code == 200, again.text
    assert (again.json()["document"]["id"], again.json()["job"]["id"]) == (
        started["document"]["id"],
        started["job"]["id"],
    )
    assert again.json()["document"]["sector"] == "school"
    assert rows(url, "SELECT count(*) FROM document") == [(1,)]
    assert rows(url, "SELECT count(*) FROM job") == [(1,)]
    assert rows(url, "SELECT count(*) FROM rate_event")[0][0] == starts  # rolled back, admission and all
    assert rows(url, "SELECT count(*) FROM audit_log WHERE action = 'document.create'") == [(1,)]


def test_a_document_asked_while_the_extraction_runs_is_led_to_it_though_the_budget_is_spent(
    client: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    made = a_conversion(url, owner)
    started = make(client, url, header, made)
    spend_all(url, owner)

    again = client.post("/api/v1/documents", headers=header, json=asked(made))

    assert (again.status_code, again.json()["document"]["id"]) == (200, started["document"]["id"])


def test_a_document_asked_beside_another_made_meanwhile_is_led_to_that_one(
    client: TestClient, url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # two requests side by side: the second looks once the admission's lock is its, and finds the
    # first's document, committed while it waited for that lock
    owner, header = an_account(url)
    made = a_conversion(url, owner)
    first: list[UUID] = []
    admit = limits.admit_model_start

    async def first_one_commits_meanwhile(*args: Any, **kwargs: Any) -> None:
        with psycopg.connect(url, autocommit=True) as connection:
            first.append(add_document(connection, made))
            connection.execute(
                "INSERT INTO job_lane (lane) VALUES (%s) ON CONFLICT DO NOTHING", (str(owner),)
            )
            connection.execute(
                "INSERT INTO job (id, kind, lane, payload, unique_key)"
                " VALUES (gen_random_uuid(), %s, %s, '{}', %s)",
                (KIND, str(owner), unique_key(first[0])),
            )
        await admit(*args, **kwargs)

    monkeypatch.setattr("app.api.documents.admit_model_start", first_one_commits_meanwhile)

    again = client.post("/api/v1/documents", headers=header, json=asked(made))

    assert (again.status_code, again.json()["document"]["id"]) == (200, str(first[0]))
    assert rows(url, "SELECT count(*) FROM document") == [(1,)]


def test_a_document_of_the_conversion_is_made_again_once_its_extraction_ended_or_by_another(
    client: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    made, other = a_conversion(url, owner), a_conversion(url, owner, b"\x02" * 32)
    started = make(client, url, header, made)

    by_editor = client.post("/api/v1/documents", headers=editor, json=asked(made))
    of_another_pdf = client.post("/api/v1/documents", headers=header, json=asked(other))
    end_job(url, started["job"]["id"], "cancelled")
    again = client.post("/api/v1/documents", headers=header, json=asked(made, sector="vocational"))

    assert by_editor.status_code == 202, by_editor.text  # the editor's own, charged to the editor
    assert of_another_pdf.status_code == 202, of_another_pdf.text
    assert again.status_code == 202, again.text
    assert again.json()["document"]["id"] != started["document"]["id"]
    assert rows(url, "SELECT count(*) FROM document") == [(4,)]


def test_a_start_while_the_extraction_waits_or_runs_gives_that_one_back(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    document = started["document"]["id"]

    starts = rows(url, "SELECT count(*) FROM rate_event")[0][0]

    again = client.post(f"/api/v1/documents/{document}/extraction", headers=header)

    assert (again.status_code, again.json()["id"]) == (200, started["job"]["id"])
    assert rows(url, "SELECT count(*) FROM job") == [(1,)]
    assert rows(url, "SELECT count(*) FROM rate_event")[0][0] == starts  # no place in the minute taken


@pytest.mark.parametrize("ended", ["cancelled", "failed", "done"])
def test_once_the_extraction_has_ended_a_start_makes_a_new_one(
    client: TestClient, url: str, ended: str
) -> None:
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    end_job(url, started["job"]["id"], ended)

    again = client.post(f"/api/v1/documents/{started['document']['id']}/extraction", headers=header)

    assert again.status_code == 202, again.text
    assert again.json()["id"] != started["job"]["id"] and again.json()["status"] == "queued"
    document = client.get(f"/api/v1/documents/{started['document']['id']}", headers=header).json()
    assert document["extraction"] == {"job_id": again.json()["id"], "status": "queued"}  # the latest
    assert rows(url, "SELECT action FROM audit_log WHERE action = 'extraction.start'") == [
        ("extraction.start",)
    ]


def test_a_start_that_meets_one_started_beside_it_gives_that_one_back_and_takes_no_start(
    client: TestClient, url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the look found none, the insert gave way: the transaction rolls back, admission and all
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    end_job(url, started["job"]["id"], "cancelled")
    beside = rows(
        url,
        "INSERT INTO job (id, kind, lane, payload, unique_key) VALUES (gen_random_uuid(), %s, %s, '{}', %s)"
        " RETURNING id",
        KIND,
        str(owner),
        unique_key(UUID(started["document"]["id"])),
    )[0][0]

    async def looked_too_early(*_: Any) -> None:
        return None

    monkeypatch.setattr(documents_api, "open_job", looked_too_early)
    starts = rows(url, "SELECT count(*) FROM rate_event")[0][0]

    again = client.post(f"/api/v1/documents/{started['document']['id']}/extraction", headers=header)

    assert (again.status_code, again.json()["id"]) == (200, str(beside))
    assert rows(url, "SELECT count(*) FROM rate_event")[0][0] == starts


def test_a_start_while_the_extraction_runs_gives_it_back_though_the_budget_is_spent(
    client: TestClient, url: str
) -> None:
    # following one's own extraction asks for nothing more
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    spend_all(url, owner)

    again = client.post(f"/api/v1/documents/{started['document']['id']}/extraction", headers=header)

    assert (again.status_code, again.json()["id"]) == (200, started["job"]["id"])


def test_a_new_start_is_admitted_as_any_model_job(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    end_job(url, started["job"]["id"], "cancelled")
    spend_all(url, owner)

    again = client.post(f"/api/v1/documents/{started['document']['id']}/extraction", headers=header)

    assert (again.status_code, again.json()["code"]) == (403, "no_budget")


def test_only_the_owner_starts_an_extraction(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, admin = an_account(url, "Admin", ("admin",))
    _, stranger = an_account(url, "Fremde")
    started = make(client, url, header, a_conversion(url, owner))
    path = f"/api/v1/documents/{started['document']['id']}/extraction"
    end_job(url, started["job"]["id"], "cancelled")

    by_editor, by_admin = client.post(path, headers=editor), client.post(path, headers=admin)
    by_stranger = client.post(path, headers=stranger)

    assert (by_editor.status_code, by_editor.json()["code"]) == (403, "not_owner")
    assert (by_admin.status_code, by_admin.json()["code"]) == (403, "not_owner")  # charged to the owner
    assert (by_stranger.status_code, by_stranger.json()["code"]) == (404, "no_document")


@pytest.fixture
def tight(url: str, tmp_path: Path) -> Iterator[TestClient]:
    # one model job in flight and one start a minute for an account
    settings = make_settings(
        database_url=url, storage_dir=tmp_path, max_jobs_in_flight=1, model_starts_per_minute=1
    )
    with selector_client(create_app(settings), base_url=PUBLIC) as test_client:
        yield test_client


def test_a_document_beside_a_job_in_flight_or_past_the_starts_a_minute_is_refused_and_nothing_made(
    tight: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    first, second, third = (a_conversion(url, owner, bytes([n]) * 32) for n in (1, 2, 3))
    started = make(tight, url, header, first)

    in_flight = tight.post("/api/v1/documents", headers=header, json=asked(second))
    end_job(url, started["job"]["id"], "done")
    past_the_minute = tight.post("/api/v1/documents", headers=header, json=asked(third))

    assert (in_flight.status_code, in_flight.json()["code"]) == (429, "too_many_jobs")
    assert (past_the_minute.status_code, past_the_minute.json()["code"]) == (429, "too_many_starts")
    assert "Retry-After" in in_flight.headers and "Retry-After" in past_the_minute.headers
    assert rows(url, "SELECT count(*) FROM document") == [(1,)]
    assert rows(url, "SELECT count(*) FROM job") == [(1,)]


def test_a_restart_beside_a_job_in_flight_or_past_the_starts_a_minute_is_refused(
    tight: TestClient, url: str
) -> None:
    owner, header = an_account(url)
    started = make(tight, url, header, a_conversion(url, owner))
    path = f"/api/v1/documents/{started['document']['id']}/extraction"
    end_job(url, started["job"]["id"], "cancelled")
    with psycopg.connect(url, autocommit=True) as connection:  # another model job of the account runs
        connection.execute(
            "INSERT INTO job (id, kind, lane, payload) VALUES (gen_random_uuid(), %s, %s, '{}')",
            (KIND, str(owner)),
        )

    in_flight = tight.post(path, headers=header)
    end_job_of_lane(url, str(owner))
    past_the_minute = tight.post(path, headers=header)

    assert (in_flight.status_code, in_flight.json()["code"]) == (429, "too_many_jobs")
    assert (past_the_minute.status_code, past_the_minute.json()["code"]) == (429, "too_many_starts")
    assert rows(url, "SELECT count(*) FROM job WHERE unique_key IS NOT NULL") == [(1,)]


def test_a_restart_needs_the_entry_s_content_still_readable_by_its_owner(
    client: TestClient, url: str, tmp_path: Path
) -> None:
    # made while the content of entries of no account was open to accounts; closed since
    # (THIRD_PARTY_MARKDOWN=hidden, the client's): the extraction does not go on reading it
    owner, header = an_account(url)
    made = a_conversion(url, owner)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("UPDATE source SET owner_id = NULL WHERE id = %s", (made["source"],))
    opened = make_settings(database_url=url, storage_dir=tmp_path, third_party_markdown="accounts")
    with selector_client(create_app(opened), base_url=PUBLIC) as while_open:
        started = make(while_open, url, header, made)
    end_job(url, started["job"]["id"], "cancelled")

    again = client.post(f"/api/v1/documents/{started['document']['id']}/extraction", headers=header)

    assert (again.status_code, again.json()["code"]) == (403, "file_hidden")
    assert rows(url, "SELECT count(*) FROM job") == [(1,)]


def end_job_of_lane(url: str, lane: str) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "UPDATE job SET status = 'done', finished_at = now() WHERE lane = %s AND status = 'queued'",
            (lane,),
        )


def test_a_document_and_its_list_are_read_by_who_sees_them(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, stranger = an_account(url, "Fremde")
    made = a_conversion(url, owner)
    first = make(client, url, header, made)
    end_job(url, first["job"]["id"], "cancelled")  # a second document of the conversion after it
    second = make(client, url, header, made)
    path = f"/api/v1/documents/{first['document']['id']}"

    own = client.get("/api/v1/documents", headers=header, params={"source_id": str(made["source"])})
    by_editor = client.get(path, headers=editor)

    assert [item["id"] for item in own.json()] == [second["document"]["id"], first["document"]["id"]]
    assert own.json()[0]["extraction"] == {"job_id": second["job"]["id"], "status": "queued"}
    assert client.get(path, headers=header).json()["own"] is True
    assert (by_editor.status_code, by_editor.json()["own"]) == (200, False)
    assert client.get(path, headers=stranger).status_code == 404
    assert client.get("/api/v1/documents", headers=stranger).json() == []


def test_the_extraction_s_job_is_named_to_those_who_may_follow_it_its_status_to_every_reader(
    client: TestClient, url: str
) -> None:
    # the job is followed in its owner's lane or by an admin (app/api/jobs.py); an editor reads how
    # it stands, as a conversion names its job to its starter alone (app/api/conversions.py)
    owner, header = an_account(url)
    _, editor = an_account(url, "Redaktion", ("redaktion",))
    _, admin = an_account(url, "Admin", ("admin",))
    made = a_conversion(url, owner)
    started = make(client, url, header, made)
    path, job = f"/api/v1/documents/{started['document']['id']}", started["job"]["id"]

    seen = {
        name: (
            client.get(path, headers=who).json()["extraction"],
            client.get("/api/v1/documents", headers=who, params={"source_id": str(made["source"])}).json()[0][
                "extraction"
            ],
        )
        for name, who in {"owner": header, "editor": editor, "admin": admin}.items()
    }

    assert seen["owner"] == seen["admin"] == ({"job_id": job, "status": "queued"},) * 2
    assert seen["editor"] == ({"job_id": None, "status": "queued"},) * 2
    assert client.get(f"/api/v1/jobs/{job}", headers=editor).status_code == 404  # whom it is kept from


def test_a_document_keeps_the_notation_of_a_sector_retired_since(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            "UPDATE vocab_concept SET retired_in = (SELECT max(id) FROM vocab_release) WHERE iri = %s",
            (CV + "sec_school",),
        )

    answer = client.get(f"/api/v1/documents/{started['document']['id']}", headers=header)

    assert answer.json()["sector"] == "school"


def add_run(url: str, document: str, job: str, stage: str, attempt: int, outcome: str | None = None,
            failure: str | None = None) -> None:  # fmt: skip
    with psycopg.connect(url, autocommit=True) as connection:
        run = add_entity(connection, "extraction_run")
        connection.execute(
            "INSERT INTO extraction_run (id, document_id, job_id, attempt, stage_scheme, stage_iri, outcome,"
            " finished_at, result) VALUES (%s, %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() END, %s)",
            (run, document, job, attempt, CV + "Stages", CV + "stage_" + stage, outcome, outcome is not None,
             None if failure is None else Jsonb({"failure": failure})),
        )  # fmt: skip


def test_a_document_s_runs_are_read_with_how_each_stands(client: TestClient, url: str) -> None:
    owner, header = an_account(url)
    started = make(client, url, header, a_conversion(url, owner))
    document, job = started["document"]["id"], started["job"]["id"]
    add_run(url, document, job, "X1", 1, "done")
    add_run(url, document, job, "X2", 1, "failed", "LeaseLost")
    add_run(url, document, job, "X2", 2)  # its job waits again: left with the attempt before

    answer = client.get(f"/api/v1/documents/{document}/runs", headers=header)

    assert answer.status_code == 200, answer.text
    assert [(run["stage"], run["attempt"], run["state"], run["failure"]) for run in answer.json()] == [
        ("X1", 1, "done", None),
        ("X2", 1, "failed", "LeaseLost"),
        ("X2", 2, "abandoned", None),
    ]
    _, stranger = an_account(url, "Fremde")
    assert client.get(f"/api/v1/documents/{document}/runs", headers=stranger).status_code == 404
