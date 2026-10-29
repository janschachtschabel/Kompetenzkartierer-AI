"""The blocks of a document's own conversion, one page at a time (plan M1 9.9, Paket 9c J3): the blocks its
anchors name (``anchor_block``) are those of the conversion it was read off, not of the entry's file today -
a file fetched again, or one converted by another engine, numbers its blocks anew. Read as the document is
(``visible_document``, 404 ``no_document``), its content as the entry's (403 ``file_hidden`` once it is no
longer the reader's), a page past the file's end 404 ``no_such_page``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.conversions import PageOut, read_page
from app.api.deps import require_account
from app.api.document_access import readable_content, visible_document
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.core.auth import Principal
from app.db.conversions import printed_pages

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]


class DocumentPageOut(PageOut):
    pages: int  # the conversion's, from 1


@router.get(
    "/documents/{document_id}/blocks",
    summary="The blocks of one page of the conversion the document was read off, in reading order",
    responses={
        403: {
            "model": ErrorBody,
            "description": "file_hidden: the entry's content is no longer yours to read",
        },
        404: {
            "model": ErrorBody,
            "description": "no_document: none the caller may read; no_such_page: the file has fewer pages",
        },
    },
)
async def read_document_blocks(
    document_id: UUID, page: Annotated[int, Query(ge=1, le=100_000)], request: Request, who: Account
) -> DocumentPageOut:
    async with request.app.state.pool.connection() as connection:
        document = await visible_document(connection, who, document_id)
        await readable_content(connection, who, request.app.state.settings, document)
        printed = await printed_pages(connection, document.conversion_id)
        if page > len(printed):
            raise Refusal(404, "no_such_page", f"The document's file has {len(printed)} pages.")
        blocks, continued = await read_page(connection, document.conversion_id, page)
    return DocumentPageOut(
        page=page, pages=len(printed), printed_page=printed[page - 1], blocks=blocks, continued=continued
    )
