"""What an edit sets, checked against the editor's form (plan M1 9.3, 9.4; app/vocab/forms.py): each value
by the key of a field the form has; a text within its field's length, a blank one none, and given where
the form asks for it; a list's value one the form offers - active, of the document's profile -, a field
of many a list of them, each once. A node type and a subkind stand under the function and the kind beside
them: checked where the edit names either, so that a value the profile has retired since stays until an
edit touches its pair. The store checks again (its constraints and triggers); this tells the editor which
field and why.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Literal

from app.vocab.forms import Form, FormField

FieldValue = str | list[str] | None  # a text, a value's IRI, the IRIs of a field of many; none unset
FieldProblem = Literal[
    "unknown", "required", "not_text", "not_list", "too_long", "not_offered", "not_under",
    "unknown_block", "no_page",  # a statement's anchors': a block of no conversion of its document, no page
]  # fmt: skip
# a profile's value and the core value it refines, by their fields' keys
_UNDER = {"node_type": "function", "subkind": "statement_kind"}


class FieldError(ValueError):
    """A field an edit may not set as asked: ``key`` the field, ``problem`` why."""

    def __init__(self, key: str, problem: FieldProblem) -> None:
        super().__init__(f"{key}: {problem}")
        self.key = key
        self.problem: FieldProblem = problem


def checked(fields: Sequence[FormField], form: Form, given: Mapping[str, object]) -> dict[str, FieldValue]:
    """The values ``given`` by the keys of ``fields`` as the store keeps them; FieldError for the first
    that may not be set so."""
    known = {field.key: field for field in fields}
    values: dict[str, FieldValue] = {}
    for key, value in given.items():
        field = known.get(key)
        if field is None:
            raise FieldError(key, "unknown")
        values[key] = _value(field, form, value)
    return values


def check_under(form: Form, values: Mapping[str, FieldValue], *, given: Collection[str]) -> None:
    """Each node type and subkind of ``values`` under the function and kind beside it, where ``given`` -
    the keys the edit names - holds either of the pair; FieldError where one is not."""
    for key, core in _UNDER.items():
        value = values.get(key)
        if value is None or not {key, core} & set(given):
            continue
        offered = {concept.iri: concept for concept in form.values.get(key, ())}
        if not isinstance(value, str) or value not in offered:
            raise FieldError(key, "not_offered")
        if values.get(core) not in offered[value].broader:
            raise FieldError(key, "not_under")


def _value(field: FormField, form: Form, value: object) -> FieldValue:
    if field.kind == "concepts":
        if not isinstance(value, list):
            raise FieldError(field.key, "not_list")
        chosen = list(dict.fromkeys(value))
        for item in chosen:
            _offered(field, form, item)
        if field.required and not chosen:
            raise FieldError(field.key, "required")
        return chosen
    if value is not None and not isinstance(value, str):
        raise FieldError(field.key, "not_text")
    if value is not None and field.kind == "concept":
        _offered(field, form, value)
    if value is not None and not value.strip():
        value = None
    if value is None and field.required:
        raise FieldError(field.key, "required")
    if value is not None and field.most is not None and len(value) > field.most:
        raise FieldError(field.key, "too_long")
    return value


def _offered(field: FormField, form: Form, value: object) -> None:
    if value not in {concept.iri for concept in form.values.get(field.key, ())}:
        raise FieldError(field.key, "not_offered")
