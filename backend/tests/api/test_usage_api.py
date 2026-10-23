"""What an account may spend on the model and has spent, as the API shows and sets it (plan M1 5.7):
an admin sets a quota, audited; an account reads its own usage; a model job's start refused for
its budget, its jobs in flight or its starts a minute is answered with a code of its own."""

from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.errors import Refusal
from app.api.limits import admit_model_start
from app.core.ids import new_id
from app.db.accounts import create_account
from app.db.migrate import migrate
from app.jobs.queue import account_lane, enqueue
from tests.support import make_settings, seed_account, seed_admin, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


@pytest.fixture
def client(migrated: str) -> Iterator[TestClient]:
    with selector_client(create_app(make_settings(database_url=migrated)), base_url=PUBLIC) as test_client:
        yield test_client


def fetch(url: str, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


def test_an_admin_sets_an_account_s_quota_and_it_is_audited(client: TestClient, migrated: str) -> None:
    admin = seed_admin(migrated)
    account, user = seed_account(migrated, "Lehrkraft", ["nutzer"])

    put = client.put(
        f"/api/v1/accounts/{account}/quota", json={"token_limit": 50_000, "page_limit": None}, headers=admin
    )
    usage = client.get("/api/v1/me/usage", headers=user)

    assert put.status_code == 200
    assert put.json() == {"account_id": str(account), "token_limit": 50_000, "page_limit": None}
    assert usage.json() == {
        "token_limit": 50_000,
        "tokens_spent": 0,
        "tokens_held": 0,
        "tokens_estimated": 0,
        "tokens_left": 50_000,
        "page_limit": None,
        "pages_spent": 0,
    }
    [(actor, subject, details)] = fetch(
        migrated, "SELECT actor_name, subject, details FROM audit_log WHERE action = 'account.quota'"
    )
    assert (actor, subject, details) == (
        "Admin",
        f"account:{account}",
        {"token_limit": 50_000, "page_limit": None},
    )


def test_a_quota_set_again_takes_the_first_one_s_place(client: TestClient, migrated: str) -> None:
    admin = seed_admin(migrated)
    account, _ = seed_account(migrated, "Lehrkraft", ["nutzer"])
    client.put(f"/api/v1/accounts/{account}/quota", json={"token_limit": 10, "page_limit": 5}, headers=admin)

    again = client.put(
        f"/api/v1/accounts/{account}/quota", json={"token_limit": None, "page_limit": 0}, headers=admin
    )

    assert again.json()["token_limit"] is None
    assert fetch(migrated, "SELECT token_limit, page_limit FROM quota") == [(None, 0)]


def test_only_an_admin_sets_a_quota(client: TestClient, migrated: str) -> None:
    account, user = seed_account(migrated, "Redaktion", ["redaktion"])

    refused = client.put(
        f"/api/v1/accounts/{account}/quota", json={"token_limit": None, "page_limit": None}, headers=user
    )

    assert refused.status_code == 403
    assert fetch(migrated, "SELECT count(*) FROM quota") == [(0,)]


def test_a_quota_for_no_account_is_not_found(client: TestClient, migrated: str) -> None:
    admin = seed_admin(migrated)

    missing = client.put(
        f"/api/v1/accounts/{new_id()}/quota", json={"token_limit": 1, "page_limit": 1}, headers=admin
    )

    assert missing.status_code == 404
    assert fetch(migrated, "SELECT count(*) FROM audit_log WHERE action = 'account.quota'") == [(0,)]


@pytest.mark.parametrize(
    "body",
    [
        {"token_limit": -1, "page_limit": 0},
        {"token_limit": 0, "page_limit": -1},
        {"token_limit": 10**16, "page_limit": 0},
        {"token_limit": 10},
        {"page_limit": 10},
        {"token_limit": 10, "page_limit": 10, "role": "admin"},
        {"token_limit": "viel", "page_limit": 10},
    ],
    ids=[
        "negative-tokens",
        "negative-pages",
        "past-the-cap",
        "pages-unsaid",
        "tokens-unsaid",
        "extra",
        "text",
    ],
)
def test_a_quota_names_both_limits_as_counts_or_none(
    client: TestClient, migrated: str, body: dict[str, Any]
) -> None:
    # unsaid is not "no limit": a limit left out would let an account spend without one
    admin = seed_admin(migrated)
    account, _ = seed_account(migrated, "Lehrkraft", ["nutzer"])

    refused = client.put(f"/api/v1/accounts/{account}/quota", json=body, headers=admin)

    assert refused.status_code == 422
    assert fetch(migrated, "SELECT count(*) FROM quota") == [(0,)]


def test_an_account_without_a_quota_sees_it_may_spend_nothing(client: TestClient, migrated: str) -> None:
    _, admin_of_nothing = seed_account(migrated, "Admin ohne Quote", ["admin"])

    usage = client.get("/api/v1/me/usage", headers=admin_of_nothing)

    assert usage.status_code == 200
    assert (usage.json()["token_limit"], usage.json()["tokens_left"]) == (0, 0)


def test_an_account_sees_what_it_spent_holds_and_what_of_it_was_estimated(
    client: TestClient, migrated: str
) -> None:
    account, user = seed_account(migrated, "Lehrkraft", ["nutzer"])
    other, _ = seed_account(migrated, "Andere", ["nutzer"])
    with psycopg.connect(migrated, autocommit=True) as connection:
        connection.execute("INSERT INTO quota (account_id, token_limit) VALUES (%s, 10000)", (account,))
        for who, tokens, estimated in ((account, 1_000, False), (account, 400, True), (other, 5_000, False)):
            connection.execute(
                "INSERT INTO llm_usage (account_id, purpose, model, input_tokens, cached_input_tokens,"
                " output_tokens, requests, unanswered_requests, estimated)"
                " VALUES (%s, 'x1', 'gpt-6-luna', %s, 0, 0, 1, 0, %s)",
                (who, tokens, estimated),
            )
        job = new_id()
        connection.execute("INSERT INTO job_lane (lane) VALUES (%s)", (str(account),))
        connection.execute(
            "INSERT INTO job (id, kind, lane) VALUES (%s, 'extraction.x1', %s)", (job, str(account))
        )
        connection.execute(
            "INSERT INTO usage_reservation (account_id, job_id, purpose, model, input_tokens, output_tokens)"
            " VALUES (%s, %s, 'x1', 'gpt-6-luna', 600, 2000)",
            (account, job),
        )

    usage = client.get("/api/v1/me/usage", headers=user).json()

    assert (usage["tokens_spent"], usage["tokens_estimated"], usage["tokens_held"], usage["tokens_left"]) == (
        1_400,
        400,
        2_600,
        6_000,
    )


@pytest.fixture
async def connection(migrated: str) -> AsyncIterator[psycopg.AsyncConnection]:
    async with await psycopg.AsyncConnection.connect(migrated, autocommit=True) as opened:
        yield opened


async def a_user(connection: psycopg.AsyncConnection, token_limit: int | None) -> UUID:
    account = await create_account(connection, f"konto-{new_id().hex[-12:]}", ["nutzer"])
    await connection.execute(
        "INSERT INTO quota (account_id, token_limit) VALUES (%s, %s)", (account, token_limit)
    )
    return account


async def refusal_of_start(
    connection: psycopg.AsyncConnection, account: UUID, **settings: Any
) -> Refusal | None:
    try:
        async with connection.transaction():
            await admit_model_start(connection, account, make_settings(**settings), kinds={"extraction.x1"})
            await enqueue(connection, "extraction.x1", account_lane(account))
    except Refusal as refusal:
        return refusal
    return None


@pytest.mark.anyio
async def test_a_start_without_budget_is_refused_403_no_budget(connection: psycopg.AsyncConnection) -> None:
    refusal = await refusal_of_start(connection, await a_user(connection, token_limit=0))

    assert refusal is not None
    assert (refusal.status_code, refusal.code) == (403, "no_budget")


@pytest.mark.anyio
async def test_a_start_past_the_jobs_in_flight_is_refused_429_too_many_jobs(
    connection: psycopg.AsyncConnection,
) -> None:
    account = await a_user(connection, token_limit=None)
    assert await refusal_of_start(connection, account, max_jobs_in_flight=1) is None

    refusal = await refusal_of_start(connection, account, max_jobs_in_flight=1)

    assert refusal is not None
    assert (refusal.status_code, refusal.code, refusal.headers) == (
        429,
        "too_many_jobs",
        {"Retry-After": "60"},
    )


@pytest.mark.anyio
async def test_a_start_past_the_minute_s_limit_is_refused_429_too_many_starts(
    connection: psycopg.AsyncConnection,
) -> None:
    account = await a_user(connection, token_limit=None)
    assert await refusal_of_start(connection, account, model_starts_per_minute=1) is None

    refusal = await refusal_of_start(connection, account, model_starts_per_minute=1)

    assert refusal is not None
    assert (refusal.status_code, refusal.code) == (429, "too_many_starts")
    assert refusal.headers is not None
    assert 1 <= int(refusal.headers["Retry-After"]) <= 60
