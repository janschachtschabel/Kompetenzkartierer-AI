"""Who may do what: tokens an admin issued, roles, the public access switch, the failure limit."""

import asyncio
from collections.abc import Coroutine, Iterator
from typing import Annotated, Any

import psycopg
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.deps import public_read, require_account, require_role
from app.core.auth import Principal
from app.db.accounts import create_account, issue_key, revoke_key, set_disabled
from app.db.migrate import migrate
from tests.support import FAKE_PEPPER, make_settings, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine, loop_factory=asyncio.SelectorEventLoop)


async def account_with_token(url: str, name: str, roles: list[str]) -> tuple[Any, Any, str]:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as connection:
        account = await create_account(connection, name, roles)
        key, token = await issue_key(connection, account, "test", FAKE_PEPPER)
    return account, key, token


def app_with_probes(database_url: str, public_access: str = "off") -> FastAPI:
    app = create_app(make_settings(database_url=database_url, public_access=public_access))

    async def who(principal: Principal) -> dict[str, Any]:
        return {"name": principal.name, "anonymous": principal.anonymous}

    async def lookup(principal: Annotated[Principal, Depends(public_read("lookup"))]) -> dict[str, Any]:
        return await who(principal)

    async def search(principal: Annotated[Principal, Depends(public_read("search"))]) -> dict[str, Any]:
        return await who(principal)

    async def write(principal: Annotated[Principal, Depends(require_account)]) -> dict[str, Any]:
        return await who(principal)

    async def admin(principal: Annotated[Principal, Depends(require_role("admin"))]) -> dict[str, Any]:
        return await who(principal)

    app.add_api_route("/api/v1/t/lookup", lookup, tags=["system"])
    app.add_api_route("/api/v1/t/search", search, tags=["system"])
    app.add_api_route("/api/v1/t/write", write, methods=["POST"], tags=["system"])
    app.add_api_route("/api/v1/t/llm", write, methods=["POST"], tags=["system"])
    app.add_api_route("/api/v1/t/admin", admin, tags=["system"])
    return app


@pytest.fixture
def migrated(database_url: str) -> str:
    migrate(database_url)
    return database_url


@pytest.fixture
def client(migrated: str) -> Iterator[TestClient]:
    with selector_client(app_with_probes(migrated), base_url=PUBLIC) as test_client:
        yield test_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_without_public_access_a_token_is_needed(client: TestClient, migrated: str) -> None:
    _, _, token = run(account_with_token(migrated, "Lehrkraft", ["nutzer"]))

    refused = client.get("/api/v1/t/lookup")

    assert refused.status_code == 401
    assert refused.headers["WWW-Authenticate"] == "Bearer"
    assert client.get("/api/v1/t/lookup", headers=bearer(token)).json() == {
        "name": "Lehrkraft",
        "anonymous": False,
    }


def test_lookup_access_opens_reading_but_not_search_or_writing(migrated: str) -> None:
    with selector_client(app_with_probes(migrated, "lookup"), base_url=PUBLIC) as client:
        assert client.get("/api/v1/t/lookup").json() == {"name": "", "anonymous": True}
        assert client.get("/api/v1/t/search").status_code == 401
        assert client.post("/api/v1/t/write").status_code == 401


def test_search_access_opens_search_but_never_the_language_model(migrated: str) -> None:
    with selector_client(app_with_probes(migrated, "search"), base_url=PUBLIC) as client:
        assert client.get("/api/v1/t/search").status_code == 200
        assert client.post("/api/v1/t/llm").status_code == 401


def test_a_role_the_account_lacks_is_refused(client: TestClient, migrated: str) -> None:
    _, _, user = run(account_with_token(migrated, "Lehrkraft", ["nutzer"]))
    _, _, admin = run(account_with_token(migrated, "Admin", ["admin"]))

    assert client.get("/api/v1/t/admin", headers=bearer(user)).status_code == 403
    assert client.get("/api/v1/t/admin", headers=bearer(admin)).status_code == 200
    assert client.get("/api/v1/t/admin").status_code == 401


def test_a_disabled_account_or_revoked_key_is_refused(client: TestClient, migrated: str) -> None:
    disabled_account, _, disabled = run(account_with_token(migrated, "Eins", ["nutzer"]))
    _, revoked_key, revoked = run(account_with_token(migrated, "Zwei", ["nutzer"]))

    async def withdraw() -> None:
        async with await psycopg.AsyncConnection.connect(migrated, autocommit=True) as connection:
            await set_disabled(connection, disabled_account, True)
            await revoke_key(connection, revoked_key)

    run(withdraw())

    assert client.post("/api/v1/t/write", headers=bearer(disabled)).status_code == 401
    assert client.post("/api/v1/t/write", headers=bearer(revoked)).status_code == 401


@pytest.mark.parametrize(
    "header",
    ["Basic dXNlcjpwYXNz", "Bearer", "Bearer kka_short", "Bearer kka_" + "a" * 43, "kka_" + "a" * 43],
    ids=["basic", "empty-bearer", "short", "unknown", "no-scheme"],
)
def test_a_header_with_no_valid_token_is_refused(client: TestClient, header: str) -> None:
    assert client.post("/api/v1/t/write", headers={"Authorization": header}).status_code == 401


def test_too_many_failures_refuse_the_source_s_further_failures_only(migrated: str) -> None:
    # a valid token still passes: behind one address there may be many people (review C, auth 1)
    _, _, token = run(account_with_token(migrated, "Lehrkraft", ["nutzer"]))
    app = app_with_probes(migrated)
    with selector_client(app, base_url=PUBLIC, client=("192.0.2.7", 5000)) as guessing:
        statuses = [
            guessing.post("/api/v1/t/write", headers=bearer("kka_" + "x" * 43)).status_code for _ in range(10)
        ]
        locked = guessing.post("/api/v1/t/write", headers=bearer("kka_" + "y" * 43))
        valid = guessing.post("/api/v1/t/write", headers=bearer(token))
    with selector_client(app, base_url=PUBLIC, client=("192.0.2.8", 5000)) as other:
        elsewhere = other.post("/api/v1/t/write", headers=bearer("kka_" + "x" * 43))

    assert statuses == [401] * 10
    assert locked.status_code == 429
    assert locked.json()["code"] == "too_many_requests"
    assert int(locked.headers["Retry-After"]) > 0
    assert valid.status_code == 200
    assert elsewhere.status_code == 401


def test_an_app_without_a_pepper_does_not_start() -> None:
    with pytest.raises(ValueError, match="API_KEY_PEPPER"):
        create_app(make_settings(api_key_pepper=None))
