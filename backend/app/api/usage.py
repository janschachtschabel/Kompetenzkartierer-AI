"""What an account may spend on the language model and has spent (plan M1 5.7; app/usage/ledger.py).

An admin sets an account's limits - its own too - and each setting is audited; a quota names
both limits, a count or null for none, so that no limit is ever left out by mistake. An account
reads its own usage: an account without a quota may spend nothing, an admin's too.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import require_account, require_role
from app.api.errors import AUTH_RESPONSES
from app.core.auth import Principal
from app.core.logging import current_request_id
from app.db import accounts as store
from app.usage.ledger import set_quota, usage_of

router = APIRouter(prefix="/api/v1", tags=["usage"], responses=AUTH_RESPONSES)
Admin = Annotated[Principal, Depends(require_role("admin"))]
# Far beyond any budget, well within what the database's bigint holds
MAX_LIMIT = 10**15
Limit = Annotated[int | None, Field(ge=0, le=MAX_LIMIT)]


class QuotaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_limit: Limit  # input and output tokens together; null: no limit
    page_limit: Limit  # pages of an engine that costs; null: no limit


class QuotaOut(BaseModel):
    account_id: UUID
    token_limit: int | None
    page_limit: int | None


class UsageOut(BaseModel):
    token_limit: int | None
    tokens_spent: int
    tokens_held: int  # for requests not yet answered
    tokens_estimated: int  # of those spent, booked as held for requests nobody answered
    tokens_left: int | None
    page_limit: int | None
    pages_spent: int


@router.put("/accounts/{account_id}/quota", summary="Set what an account may spend")
async def put_quota(account_id: UUID, body: QuotaIn, request: Request, admin: Admin) -> QuotaOut:
    async with request.app.state.pool.connection() as connection:
        if await store.get_account(connection, account_id) is None:
            raise HTTPException(404, "No such account.")
        await set_quota(connection, account_id, token_limit=body.token_limit, page_limit=body.page_limit)
        await store.record_audit(
            connection,
            admin.account_id,
            admin.name,
            "account.quota",
            f"account:{account_id}",
            body.model_dump(),
            current_request_id(),
        )
    return QuotaOut(account_id=account_id, token_limit=body.token_limit, page_limit=body.page_limit)


@router.get("/me/usage", summary="What the caller's account may spend and has spent")
async def my_usage(request: Request, who: Annotated[Principal, Depends(require_account)]) -> UsageOut:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    async with request.app.state.pool.connection() as connection:
        usage = await usage_of(connection, who.account_id)
    return UsageOut(
        token_limit=usage.token_limit,
        tokens_spent=usage.tokens_spent,
        tokens_held=usage.tokens_held,
        tokens_estimated=usage.tokens_estimated,
        tokens_left=usage.tokens_left,
        page_limit=usage.page_limit,
        pages_spent=usage.pages_spent,
    )
