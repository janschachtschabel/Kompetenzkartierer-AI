"""An answer checked against its stage's output schema (ontology/schemas/<name>.schema.json).

pydantic-ai's StructuredDict hands the schema to the model and takes back whatever comes; a
gateway without strict output, or a model that slips, answers out of form. The schemas are the
form OpenAI's strict output asks for, and the check knows exactly the keywords they use -
``type`` (a union with null among them), ``properties``, ``required``, ``items``, ``enum``,
``additionalProperties: false`` - besides the ones that only describe. A schema using another
keyword fails its test (tests/llm/test_schema.py) rather than going unchecked.
"""

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

KNOWN_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "additionalProperties",
        # describing only
        "$schema",
        "$id",
        "title",
        "description",
        "x-cv-scheme",
        "x-cv-subset",
    }
)
# what the model is told back of a wrong answer, at most: enough to mend it, not a second answer
MOST_ERRORS = 10
# The folder of ontology/ the stages' output schemas lie in (the image ships it)
SCHEMA_DIR = "schemas"
_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_TYPES: dict[str, tuple[str, Any]] = {
    "object": ("an object", lambda value: isinstance(value, dict)),
    "array": ("an array", lambda value: isinstance(value, list)),
    "string": ("a string", lambda value: isinstance(value, str)),
    # a whole number written as one: 3.0 is asked again, as the stages take an int
    "integer": ("an integer", lambda value: isinstance(value, int) and not isinstance(value, bool)),
    "number": ("a number", lambda value: isinstance(value, int | float) and not isinstance(value, bool)),
    "boolean": ("a boolean", lambda value: isinstance(value, bool)),
    "null": ("null", lambda value: value is None),
}
# The types it has a test for; additionalProperties it checks as false only, items as one schema
KNOWN_TYPES = frozenset(_TYPES)


def load_schema(directory: Path, name: str) -> dict[str, Any]:
    """The schema ``<name>.schema.json`` in ``directory`` ("x4-aussagen"); ValueError for a name
    that is none, FileNotFoundError for one there is no schema of."""
    if _NAME.fullmatch(name) is None:
        raise ValueError(f"{name!r} is no schema's name")
    loaded: dict[str, Any] = json.loads((directory / f"{name}.schema.json").read_text(encoding="utf-8"))
    return loaded


def schema_errors(schema: Mapping[str, Any], value: Any) -> list[str]:
    """What in ``value`` is out of the schema's form, each with its place ("$.items[1].n: an
    integer"); empty where nothing is. At most MOST_ERRORS."""
    errors: list[str] = []
    _check(schema, value, "$", errors)
    return errors[:MOST_ERRORS]


def _check(schema: Mapping[str, Any], value: Any, path: str, errors: list[str]) -> None:
    if len(errors) >= MOST_ERRORS:
        return
    kinds = schema.get("type")
    if kinds is not None:
        named = [kinds] if isinstance(kinds, str) else list(kinds)
        if not any(_TYPES[kind][1](value) for kind in named):
            errors.append(f"{path}: {' or '.join(_TYPES[kind][0] for kind in named)} belongs here")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: one of {schema['enum']} belongs here")
        return
    if isinstance(value, dict):
        _check_object(schema, value, path, errors)
    elif isinstance(value, list) and "items" in schema:
        for place, item in enumerate(value):
            _check(schema["items"], item, f"{path}[{place}]", errors)


def _check_object(schema: Mapping[str, Any], value: dict[str, Any], path: str, errors: list[str]) -> None:
    properties: Mapping[str, Any] = schema.get("properties", {})
    errors.extend(f"{path}: lacks {name}" for name in schema.get("required", ()) if name not in value)
    if schema.get("additionalProperties") is False:
        errors.extend(
            f"{path}: has {name}, which the schema does not name" for name in value if name not in properties
        )
    for name, each in properties.items():
        if name in value:
            _check(each, value[name], f"{path}.{name}", errors)
