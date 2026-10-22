"""``python -m app.core.config_doc``: write the table of settings into docs/uebergabe/konfiguration.md.

Generated from Settings and LLMSettings, so the operators' list cannot drift from what the code
reads; tests/deploy/test_configuration_doc.py fails on a table left stale. Only the part between
the markers is written; the prose around it is the document's own.
"""

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Union, get_args, get_origin

import annotated_types
from pydantic import SecretStr
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from app.core.settings import REPOSITORY_ONTOLOGY, Settings, _is_secret
from app.llm.settings import LLMSettings

DOCUMENT = Path(__file__).resolve().parents[3] / "docs" / "uebergabe" / "konfiguration.md"
START = "<!-- settings:start (python -m app.core.config_doc) -->"
END = "<!-- settings:end -->"
_BOUNDS = (
    (annotated_types.Ge, "≥", "ge"),
    (annotated_types.Gt, ">", "gt"),
    (annotated_types.Le, "≤", "le"),
    (annotated_types.Lt, "<", "lt"),
)
_OR = " \\| "  # a pipe inside a Markdown table cell
NONE = "–"  # noqa: RUF001 - the dash German tables write for "none"
# Settings no class can require alone: a part of the service needs them, or another value does
CONDITIONS = {
    "API_KEY_PEPPER": "Pflicht für die API und `app.bootstrap`",
    "STORAGE_DIR": "Pflicht bei `STORAGE_BACKEND=fs`",
    "S3_BUCKET": "Pflicht bei `STORAGE_BACKEND=s3`",
    "S3_ACCESS_KEY": "nur zusammen mit `S3_SECRET_KEY`",
    "S3_SECRET_KEY": "nur zusammen mit `S3_ACCESS_KEY`",
}


@dataclass(frozen=True)
class Row:
    variable: str
    allowed: str
    default: str
    secret: bool
    part: str


def setting_rows() -> list[Row]:
    """One row per variable, in the order the classes declare them."""
    rows: list[Row] = []
    for settings_class, part in ((Settings, "Dienst"), (LLMSettings, "Sprachmodell")):
        for name, field in settings_class.model_fields.items():
            variable = name.upper()
            default = _default(field)
            if variable in CONDITIONS:
                default = f"{default}; {CONDITIONS[variable]}"
            rows.append(Row(variable, _allowed(field), default, _is_secret(field.annotation), part))
    return rows


def render_table() -> str:
    lines = ["| Variable | Werte | Vorgabe | Geheim | Teil |", "|---|---|---|---|---|"]
    for row in setting_rows():
        secret = f"ja, auch `{row.variable}_FILE`" if row.secret else NONE
        lines.append(f"| `{row.variable}` | {row.allowed} | {row.default} | {secret} | {row.part} |")
    return "\n".join(lines)


def _type_and_constraints(field: FieldInfo) -> tuple[Any, list[Any]]:
    """The plain type and every constraint on it, also those inside ``Annotated[...] | None``."""
    annotation = field.annotation
    if get_origin(annotation) in (Union, types.UnionType):
        members = [member for member in get_args(annotation) if member is not type(None)]
        annotation = members[0] if len(members) == 1 else annotation
    constraints = list(field.metadata)
    if get_origin(annotation) is Annotated:
        annotation, *extra = get_args(annotation)
        for item in extra:
            constraints += item.metadata if isinstance(item, FieldInfo) else [item]
    return annotation, constraints


def _allowed(field: FieldInfo) -> str:
    """Raises TypeError for a type without a rendering: a new kind of field shows in the tests,
    not as a plain "Text" that hides what the code enforces."""
    annotation, constraints = _type_and_constraints(field)
    if get_origin(annotation) is Literal:
        return _OR.join(f"`{value}`" for value in get_args(annotation))
    if annotation is bool:
        return f"`true`{_OR}`false`"
    if annotation in (int, float):
        bounds = ", ".join(
            f"{sign} {_number(getattr(constraint, attribute))}"
            for constraint in constraints
            for kind, sign, attribute in _BOUNDS
            if isinstance(constraint, kind)
        )
        return f"Zahl {bounds}" if bounds else "Zahl"
    if annotation is Path:
        return "Pfad"
    if annotation in (str, SecretStr):
        return _text(constraints)
    raise TypeError(f"no rendering for the type {annotation!r}")


def _text(constraints: list[Any]) -> str:
    patterns = [_cell(c.pattern) for c in constraints if getattr(c, "pattern", None)]
    if patterns:
        return f"Text nach Muster `{patterns[0]}`"
    minimum, maximum = annotated_types.MinLen, annotated_types.MaxLen
    # min_length=1 only says "not empty"
    shortest = [c.min_length for c in constraints if isinstance(c, minimum) and c.min_length > 1]
    longest = [c.max_length for c in constraints if isinstance(c, maximum)]
    lengths = [f"mindestens {n}" for n in shortest] + [f"höchstens {n}" for n in longest]
    return f"Text, {', '.join(lengths)} Zeichen" if lengths else "Text"


def _default(field: FieldInfo) -> str:
    if field.default is PydanticUndefined and field.default_factory is None:
        return "Pflicht"
    value = field.get_default(call_default_factory=True, validated_data={})
    if value is None:
        return NONE
    if value == REPOSITORY_ONTOLOGY:
        return "`ontology/` des Repositorys"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, float | int):
        return _number(value)
    if isinstance(value, Path):
        return f"`{value.as_posix()}`"
    return f"`{_cell(str(value))}`" if value != "" else "leer"


def _cell(text: str) -> str:
    """A pipe would end the table cell, inside a code span too."""
    return text.replace("|", "\\|")


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def main(document: Path = DOCUMENT) -> int:
    text = document.read_text(encoding="utf-8")
    start, end = text.find(START), text.find(END)
    if start < 0 or end < start:
        print(f"{document} lacks the markers {START!r} and {END!r}, in this order", file=sys.stderr)
        return 1
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    document.write_text(f"{head}{START}\n{render_table()}\n{END}{tail}", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
