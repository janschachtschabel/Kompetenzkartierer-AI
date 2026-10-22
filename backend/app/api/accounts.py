"""Accounts and their API tokens, managed by an admin; and who the caller is (``/me``).

A token exists only in the answer that issues it (sent with ``Cache-Control: no-store``); the
database keeps its hash. Every change is written to the audit log with the request id, never
with a token.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.deps import require_account, require_role
from app.core.auth import Principal, Role
from app.core.logging import current_request_id
from app.db import accounts as store

router = APIRouter(prefix="/api/v1", tags=["accounts"])
Admin = Annotated[Principal, Depends(require_role("admin"))]


class AccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    roles: Annotated[list[Role], Field(min_length=1)]


class AccountOut(BaseModel):
    id: UUID
    name: str
    roles: list[str]
    disabled: bool


class AccountChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disabled: bool


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Annotated[str, Field(max_length=200)] = ""


class KeyOut(BaseModel):
    id: UUID
    token: str


class Me(BaseModel):
    id: UUID
    name: str
    roles: list[str]


@router.post("/accounts", status_code=201, summary="Create an account with its roles")
async def create_account(body: AccountIn, request: Request, admin: Admin) -> AccountOut:
    async with request.app.state.pool.connection() as connection:
        try:
            account_id = await store.create_account(connection, body.name, body.roles)
        except store.AccountExists:
            raise HTTPException(409, "An account of this name exists.") from None
        await _audit(
            connection, admin, "account.create", f"account:{account_id}", {"roles": sorted(body.roles)}
        )
        record = await store.get_account(connection, account_id)
    assert record is not None  # noqa: S101 - created in this transaction
    return AccountOut(**record.__dict__)


@router.post("/accounts/{account_id}/keys", status_code=201, summary="Issue an API token for an account")
async def issue_key(
    account_id: UUID, body: KeyIn, request: Request, response: Response, admin: Admin
) -> KeyOut:
    pepper = request.app.state.settings.api_key_pepper.get_secret_value()
    async with request.app.state.pool.connection() as connection:
        if await store.get_account(connection, account_id) is None:
            raise HTTPException(404, "No such account.")
        key_id, token = await store.issue_key(connection, account_id, body.label, pepper)
        await _audit(connection, admin, "key.issue", f"key:{key_id}", {"account": str(account_id)})
    response.headers["Cache-Control"] = "no-store"  # the one answer that holds the token
    return KeyOut(id=key_id, token=token)


@router.delete("/keys/{key_id}", status_code=204, summary="Revoke an API token")
async def revoke_key(key_id: UUID, request: Request, admin: Admin) -> None:
    async with request.app.state.pool.connection() as connection:
        if not await store.revoke_key(connection, key_id):
            raise HTTPException(404, "No such active key.")
        await _audit(connection, admin, "key.revoke", f"key:{key_id}", {})


@router.patch("/accounts/{account_id}", summary="Block or unblock an account")
async def change_account(account_id: UUID, body: AccountChange, request: Request, admin: Admin) -> AccountOut:
    async with request.app.state.pool.connection() as connection:
        if not await store.set_disabled(connection, account_id, body.disabled):
            raise HTTPException(404, "No such account.")
        action = "account.disable" if body.disabled else "account.enable"
        await _audit(connection, admin, action, f"account:{account_id}", {})
        record = await store.get_account(connection, account_id)
    assert record is not None  # noqa: S101 - found just before
    return AccountOut(**record.__dict__)


@router.get("/me", tags=["accounts"], summary="The account the token belongs to")
async def me(who: Annotated[Principal, Depends(require_account)]) -> Me:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    return Me(id=who.account_id, name=who.name, roles=sorted(who.roles))


async def _audit(
    connection: Any, admin: Principal, action: str, subject: str, details: dict[str, Any]
) -> None:
    await store.record_audit(
        connection, admin.account_id, admin.name, action, subject, details, current_request_id()
    )
