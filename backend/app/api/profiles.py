"""A sector's form for the editor (plan M1 9.1; app/vocab/forms.py): the fields of a node and of a
statement, each list with the active values of the sector's profile and their texts. Every account reads
it; a sector without an active profile has none (404 ``unknown_sector``)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel

from app.api.deps import require_account
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.core.auth import Principal
from app.vocab.forms import FieldKind, Form, FormField, form_of
from app.vocab.lookup import ConceptDetails

router = APIRouter(prefix="/api/v1", tags=["profiles"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Sector = Annotated[str, Path(min_length=1, max_length=40, pattern=r"^[a-z][a-zA-Z]*$")]


class ValueOut(BaseModel):
    iri: str
    notation: str | None
    label: str
    alt_labels: list[str]
    definition: str | None
    note: str | None  # skos:scopeNote
    delimitation: str | None  # what it is not for
    examples: list[str]
    broader: list[str]  # the core values it refines: a node type's function, a subkind's kind


class FieldOut(BaseModel):
    key: str
    kind: FieldKind
    required: bool
    many: bool
    most: int | None  # signs, for a text
    values: list[ValueOut] | None  # a list's, active ones in the order of their labels


class FormOut(BaseModel):
    sector: str
    profile: str
    node: list[FieldOut]
    statement: list[FieldOut]


@router.get(
    "/profiles/{sector}/form",
    summary="The fields of a node and of a statement, with the values of the sector's profile",
    responses={404: {"model": ErrorBody, "description": "unknown_sector: no active profile of this sector"}},
)
async def read_form(sector: Sector, request: Request, who: Account) -> FormOut:
    async with request.app.state.pool.connection() as connection:
        form = await form_of(connection, sector)
    if form is None:
        raise Refusal(404, "unknown_sector", "No active profile of this education sector.")
    return FormOut(
        sector=form.sector,
        profile=form.profile,
        node=[_field(field, form) for field in form.node],
        statement=[_field(field, form) for field in form.statement],
    )


def _field(field: FormField, form: Form) -> FieldOut:
    values = form.values.get(field.key) if field.values is not None else None
    return FieldOut(
        key=field.key,
        kind=field.kind,
        required=field.required,
        many=field.many,
        most=field.most,
        values=None if values is None else [_value(value) for value in values],
    )


def _value(value: ConceptDetails) -> ValueOut:
    return ValueOut(
        iri=value.iri,
        notation=value.notation,
        label=value.label,
        alt_labels=list(value.alt_labels),
        definition=value.definition,
        note=value.note,
        delimitation=value.delimitation,
        examples=list(value.examples),
        broader=list(value.broader),
    )
