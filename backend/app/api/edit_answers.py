"""What the editor's routes take and refuse beside their rows (app/api/node_editing.py,
statement_editing.py; Paket 9 G2-G7): fields by the form's keys, and the refusals of a change - a field
the form does not take so (422 ``invalid_field``, ``anchor_missing`` for a statement without an anchor),
a job of the document waiting or running (409 ``job_open``, the job named to the owner and the admins),
a frozen document (409 ``frozen``), one whose extraction has not read every package (409
``not_extracted``), a sector without a form (409 ``no_form``). Each change is audited in its transaction.
"""

from typing import Annotated, Any
from uuid import UUID

import psycopg
from pydantic import BaseModel, Field, StringConstraints

from app.api.errors import ErrorBody, Refusal
from app.core.auth import Principal
from app.core.logging import current_request_id
from app.db.accounts import record_audit
from app.db.document_meta import DocumentNamed
from app.db.documents import DocumentError
from app.db.editing import DocumentFrozen, JobOpen, NotExtracted
from app.vocab.form_values import FieldError

MOST_FIELDS = 50  # a form's fields, and room
MOST_VALUES = 50  # of a field of many
FieldIn = str | Annotated[list[str], Field(max_length=MOST_VALUES)] | None
# a form's key (app/vocab/forms.py, a test compares): one wrong is refused as the request's, unechoed
FieldKey = Annotated[str, StringConstraints(max_length=40, pattern=r"^[a-z][a-zA-Z_]*$")]
Fields = Annotated[dict[FieldKey, FieldIn], Field(max_length=MOST_FIELDS)]
# what a change may meet besides a stale revision, which answers with the row as it stands
REFUSED = (FieldError, JobOpen, DocumentFrozen, NotExtracted, DocumentNamed, DocumentError)
Responses = dict[int | str, dict[str, Any]]
# the document closed to changes now
_CLOSED = (
    "job_open (details.job_id to the owner and the admins), frozen,"
    " not_extracted (X4 has not read every package)"
)
_CURRENT = "stale_revision (details.current: the row as it stands)"
EDIT_RESPONSES: Responses = {
    409: {"model": ErrorBody, "description": f"{_CURRENT}, {_CLOSED}, no_form"},
    422: {"model": ErrorBody, "description": "invalid_field (details: field, problem)"},
}
STATEMENT_RESPONSES: Responses = EDIT_RESPONSES | {
    422: {"model": ErrorBody, "description": "invalid_field (details: field, problem), anchor_missing"}
}
TAKE_RESPONSES: Responses = {409: {"model": ErrorBody, "description": f"{_CURRENT}, {_CLOSED}"}}
REVIEW_RESPONSES: Responses = {
    409: {
        "model": ErrorBody,
        "description": "stale_revision (details.stale: each row changed or gone, its revision now or null), "
        + _CLOSED,
    }
}


def stale(row: str, current: BaseModel | None) -> Refusal:
    """The answer to a change of a ``row`` - "node", "statement" - on a revision it stands no more at:
    the row as it stands now, as the tree reads it (none where it has gone meanwhile)."""
    return Refusal(
        409,
        "stale_revision",
        f"The {row} was changed meanwhile: see it as it stands.",
        details={"current": None if current is None else current.model_dump(mode="json")},
    )


def answers(not_found: str, refusals: Responses = EDIT_RESPONSES) -> Responses:
    """A change's answers beside its row: ``not_found`` the 404's description, and the ``refusals`` it
    gives - an edit's (a statement's with its anchors), a taking away's (no field, so no form), a review's."""
    return {404: {"model": ErrorBody, "description": not_found}} | refusals


async def refusal_of(
    connection: psycopg.AsyncConnection, who: Principal, document_id: UUID | None, error: Exception
) -> Refusal:
    """The answer to a change refused by ``error``, one of REFUSED, in the document ``document_id``."""
    if isinstance(error, FieldError):
        if (error.key, error.problem) == ("anchors", "required"):
            return Refusal(422, "anchor_missing", "A statement stands somewhere in its source: name where.")
        return Refusal(
            422,
            "invalid_field",
            f"The field {error.key} may not be set so: {error.problem}.",
            details={"field": error.key, "problem": error.problem},
        )
    if isinstance(error, JobOpen):
        named = "admin" in who.roles or (
            document_id is not None and await _owns(connection, who, document_id)
        )
        return Refusal(
            409,
            "job_open",
            "A job of the document waits or runs: change it once that has ended.",
            details={"job_id": str(error.job_id)} if named else None,
        )
    if isinstance(error, DocumentFrozen):
        return Refusal(409, "frozen", "The document is frozen: its draft copy takes changes.")
    if isinstance(error, NotExtracted):
        return Refusal(409, "not_extracted", "The extraction has not read every work package yet.")
    if isinstance(error, DocumentNamed):
        return Refusal(409, "named", "The document is named by its IRI: its work, issuer and edition stay.")
    if isinstance(error, DocumentError) and error.code == "no_form":
        return Refusal(409, "no_form", "The document's sector has no form to edit it with.")
    return Refusal(404, "no_document", "No such document.")


async def audit(
    connection: psycopg.AsyncConnection, who: Principal, action: str, subject: str, details: dict[str, Any]
) -> None:
    await record_audit(connection, who.account_id, who.name, action, subject, details, current_request_id())


async def _owns(connection: psycopg.AsyncConnection, who: Principal, document_id: UUID) -> bool:
    cursor = await connection.execute("SELECT owner_id FROM document WHERE id = %s", (document_id,))
    found = await cursor.fetchone()
    return found is not None and found[0] == who.account_id
