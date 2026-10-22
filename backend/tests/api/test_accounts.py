"""An admin creates accounts and hands out, revokes and blocks their tokens; all audited."""

import asyncio
import io
from collections.abc import Iterator
from typing import Any

import httpx2
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.logging import configure_logging
from app.db.accounts import create_account, issue_key
from app.db.migrate import migrate
from tests.support import FAKE_PEPPER, make_settings, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"


async def seed(url: str, name: str, roles: list[str]) -> str:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as connection:
        account = await create_account(connection, name, roles)
        _, token = await issue_key(connection, account, "seed", FAKE_PEPPER)
    return token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fetch(url: str, query: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query).fetchall()


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


@pytest.fixture
def log(restore_logging: None) -> io.StringIO:
    stream = io.StringIO()
    configure_logging("INFO", "json", stream=stream)
    return stream


@pytest.fixture
def client(migrated: str) -> Iterator[TestClient]:
    with selector_client(create_app(make_settings(database_url=migrated)), base_url=PUBLIC) as test_client:
        yield test_client


@pytest.fixture
def admin(migrated: str) -> dict[str, str]:
    return bearer(asyncio.run(seed(migrated, "Admin", ["admin"]), loop_factory=asyncio.SelectorEventLoop))


def test_an_admin_creates_an_account_and_hands_out_its_token(
    client: TestClient, admin: dict[str, str], migrated: str, log: io.StringIO
) -> None:
    created = client.post(
        "/api/v1/accounts", json={"name": "Lehrkraft Optik", "roles": ["nutzer"]}, headers=admin
    )
    account = created.json()
    issued = client.post(f"/api/v1/accounts/{account['id']}/keys", json={"label": "Laptop"}, headers=admin)
    token = issued.json()["token"]

    me = client.get("/api/v1/me", headers=bearer(token))

    assert created.status_code == 201
    assert (account["name"], account["roles"], account["disabled"]) == ("Lehrkraft Optik", ["nutzer"], False)
    assert issued.status_code == 201
    assert issued.headers["Cache-Control"] == "no-store"
    assert me.json() == {"id": account["id"], "name": "Lehrkraft Optik", "roles": ["nutzer"]}
    actions = [action for (action,) in fetch(migrated, "SELECT action FROM audit_log ORDER BY id")]
    assert actions == ["account.create", "key.issue"]
    assert token not in str(fetch(migrated, "SELECT row_to_json(a)::text FROM audit_log a"))
    assert token not in log.getvalue()


def test_only_an_admin_manages_accounts(client: TestClient, migrated: str) -> None:
    user = bearer(
        asyncio.run(seed(migrated, "Lehrkraft", ["nutzer"]), loop_factory=asyncio.SelectorEventLoop)
    )

    assert (
        client.post("/api/v1/accounts", json={"name": "X", "roles": ["admin"]}, headers=user).status_code
        == 403
    )
    assert client.post("/api/v1/accounts", json={"name": "X", "roles": ["admin"]}).status_code == 401


def test_a_second_account_of_the_same_name_is_refused(client: TestClient, admin: dict[str, str]) -> None:
    client.post("/api/v1/accounts", json={"name": "Redaktion", "roles": ["redaktion"]}, headers=admin)

    again = client.post("/api/v1/accounts", json={"name": "redaktion", "roles": ["nutzer"]}, headers=admin)

    assert again.status_code == 409
    assert again.json()["code"] == "conflict"


@pytest.mark.parametrize(
    "body",
    [{"name": "", "roles": ["nutzer"]}, {"name": "X", "roles": []}, {"name": "X", "roles": ["superuser"]}],
    ids=["empty-name", "no-role", "unknown-role"],
)
def test_an_account_needs_a_name_and_known_roles(
    client: TestClient, admin: dict[str, str], body: dict[str, Any]
) -> None:
    assert client.post("/api/v1/accounts", json=body, headers=admin).status_code == 422


def test_a_revoked_token_and_a_blocked_account_lose_access(client: TestClient, admin: dict[str, str]) -> None:
    account = client.post(
        "/api/v1/accounts", json={"name": "Eins", "roles": ["nutzer"]}, headers=admin
    ).json()
    first = client.post(f"/api/v1/accounts/{account['id']}/keys", json={}, headers=admin).json()
    second = client.post(f"/api/v1/accounts/{account['id']}/keys", json={}, headers=admin).json()

    assert client.delete(f"/api/v1/keys/{first['id']}", headers=admin).status_code == 204
    assert client.get("/api/v1/me", headers=bearer(first["token"])).status_code == 401
    assert client.get("/api/v1/me", headers=bearer(second["token"])).status_code == 200

    blocked = client.patch(f"/api/v1/accounts/{account['id']}", json={"disabled": True}, headers=admin)
    assert blocked.json()["disabled"] is True
    assert client.get("/api/v1/me", headers=bearer(second["token"])).status_code == 401
    client.patch(f"/api/v1/accounts/{account['id']}", json={"disabled": False}, headers=admin)
    assert client.get("/api/v1/me", headers=bearer(second["token"])).status_code == 200


def test_unknown_accounts_and_keys_are_not_found(client: TestClient, admin: dict[str, str]) -> None:
    nobody = "01890000-0000-7000-8000-000000000000"

    assert client.post(f"/api/v1/accounts/{nobody}/keys", json={}, headers=admin).status_code == 404
    assert client.delete(f"/api/v1/keys/{nobody}", headers=admin).status_code == 404
    assert (
        client.patch(f"/api/v1/accounts/{nobody}", json={"disabled": True}, headers=admin).status_code == 404
    )


def test_me_needs_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401


def me_id(client: TestClient, headers: dict[str, str]) -> str:
    return str(client.get("/api/v1/me", headers=headers).json()["id"])


def test_the_last_admin_key_cannot_be_revoked(
    client: TestClient, admin: dict[str, str], migrated: str
) -> None:
    [(key_id,)] = fetch(migrated, "SELECT id FROM api_key")

    refused = client.delete(f"/api/v1/keys/{key_id}", headers=admin)

    assert refused.status_code == 409
    assert client.get("/api/v1/me", headers=admin).status_code == 200


def test_the_last_admin_cannot_block_themselves(client: TestClient, admin: dict[str, str]) -> None:
    refused = client.patch(f"/api/v1/accounts/{me_id(client, admin)}", json={"disabled": True}, headers=admin)

    assert refused.status_code == 409
    assert client.get("/api/v1/me", headers=admin).status_code == 200


def test_with_a_second_admin_the_first_one_may_go(client: TestClient, admin: dict[str, str]) -> None:
    other = client.post(
        "/api/v1/accounts", json={"name": "Zweite Admin", "roles": ["admin"]}, headers=admin
    ).json()
    client.post(f"/api/v1/accounts/{other['id']}/keys", json={}, headers=admin)

    blocked = client.patch(f"/api/v1/accounts/{me_id(client, admin)}", json={"disabled": True}, headers=admin)

    assert blocked.status_code == 200


@pytest.mark.anyio
async def test_two_admins_blocking_each_other_at_once_leave_one(migrated: str) -> None:
    # each would see the other still active and pass; the lock lets one through, then refuses
    app = create_app(make_settings(database_url=migrated, db_pool_min_size=4, db_pool_max_size=4))
    first, second = await seed(migrated, "Erste", ["admin"]), await seed(migrated, "Zweite", ["admin"])
    ids = {name: account for account, name in fetch(migrated, "SELECT id, name FROM account")}
    transport = httpx2.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=transport, base_url=PUBLIC) as client,
    ):
        await app.state.pool.wait(timeout=10)
        answers = await asyncio.gather(
            client.patch(f"/api/v1/accounts/{ids['Zweite']}", json={"disabled": True}, headers=bearer(first)),
            client.patch(f"/api/v1/accounts/{ids['Erste']}", json={"disabled": True}, headers=bearer(second)),
        )

    assert sorted(answer.status_code for answer in answers) == [200, 409]
