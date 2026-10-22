"""The failure limit behind proxies and NAT: it slows guessing and locks out no one with a token."""

import asyncio
import hashlib
import hmac
import logging
from collections.abc import Coroutine
from typing import Annotated, Any

import httpx2
import psycopg
import pytest
from fastapi import Depends, FastAPI

from app.api.app import create_app
from app.api.deps import failure_source, require_account
from app.core.auth import Principal
from app.db.accounts import create_account, issue_key, record_failure
from app.db.migrate import migrate
from tests.support import FAKE_PEPPER, make_settings, selector_client

PUBLIC = "http://testserver:8000"
BAD = {"Authorization": "Bearer kka_" + "x" * 43}


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine, loop_factory=asyncio.SelectorEventLoop)


async def token_for(url: str, name: str) -> str:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as connection:
        account = await create_account(connection, name, ["nutzer"])
        _, token = await issue_key(connection, account, "test", FAKE_PEPPER)
    return token


def app_with_probe(url: str, **settings: Any) -> FastAPI:
    app = create_app(make_settings(database_url=url, **settings))

    async def write(who: Annotated[Principal, Depends(require_account)]) -> dict[str, str]:
        return {"name": who.name}

    app.add_api_route("/api/v1/t/write", write, methods=["POST"], tags=["system"])
    return app


@pytest.mark.parametrize(
    ("host", "source"),
    [
        ("192.0.2.7", "192.0.2.7"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:db8:1:2::9", "2001:db8:1:2::/64"),
        (None, "unknown"),
        ("not-an-address", "unknown"),
        ("x" * 500, "unknown"),
    ],
)
def test_a_source_is_an_address_or_an_ipv6_network(host: str | None, source: str) -> None:
    # one IPv6 client holds a whole /64; counting single addresses would not slow it down
    assert failure_source(host) == source


@pytest.mark.pg
def test_a_valid_token_passes_where_others_behind_the_same_address_failed(database_url: str) -> None:
    # behind a proxy or a school's NAT everyone shares one address
    migrate(database_url)
    token = run(token_for(database_url, "Lehrkraft"))
    with selector_client(app_with_probe(database_url), base_url=PUBLIC, client=("10.1.2.3", 5000)) as client:
        failed = [client.post("/api/v1/t/write", headers=BAD).status_code for _ in range(11)]
        valid = client.post("/api/v1/t/write", headers={"Authorization": f"Bearer {token}"})

    assert failed == [401] * 10 + [429]
    assert valid.status_code == 200


@pytest.mark.pg
@pytest.mark.anyio
async def test_parallel_guesses_do_not_get_past_the_limit(database_url: str) -> None:
    migrate(database_url)
    # a warm pool, so the 20 requests really run at once
    app = app_with_probe(database_url, auth_failure_limit=3, db_pool_min_size=10, db_pool_max_size=10)
    transport = httpx2.ASGITransport(app=app, client=("192.0.2.9", 5000))
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=transport, base_url=PUBLIC) as client,
    ):
        await app.state.pool.wait(timeout=10)
        answers = await asyncio.gather(*(client.post("/api/v1/t/write", headers=BAD) for _ in range(20)))

    statuses = [answer.status_code for answer in answers]
    assert statuses.count(401) == 3
    assert statuses.count(429) == 17


@pytest.mark.pg
@pytest.mark.anyio
async def test_old_failures_are_swept_in_bounded_batches(database_url: str) -> None:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as connection:
        await connection.execute(
            "INSERT INTO auth_failure (source, at) SELECT '192.0.2.1', now() - interval '2 days'"
            " FROM generate_series(1, 1500)"
        )

        await record_failure(connection, "192.0.2.2")
        after_one = await (await connection.execute("SELECT count(*) FROM auth_failure")).fetchone()
        await record_failure(connection, "192.0.2.2")
        after_two = await (await connection.execute("SELECT count(*) FROM auth_failure")).fetchone()

    # each failure sweeps at most a batch of old rows: an attack costs no full-table scan
    assert after_one == (1500 - 1000 + 1,)
    assert after_two == (2,)


@pytest.mark.pg
def test_the_logged_source_is_keyed_not_a_plain_hash(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    # every IPv4 address hashes in minutes: a plain SHA-256 prefix in the log is the address
    migrate(database_url)
    caplog.set_level(logging.WARNING, logger="app.api.deps")
    with selector_client(
        app_with_probe(database_url, auth_failure_limit=1), base_url=PUBLIC, client=("192.0.2.9", 5000)
    ) as client:
        client.post("/api/v1/t/write", headers=BAD)

    [warning] = [record for record in caplog.records if "reached the limit" in record.getMessage()]
    [logged] = warning.args or ()
    assert logged != hashlib.sha256(b"192.0.2.9").hexdigest()[:12]
    # apart from the token hashes under the same pepper
    assert logged == hmac.new(FAKE_PEPPER.encode(), b"log-source:192.0.2.9", hashlib.sha256).hexdigest()[:12]
