"""An answer checked against its stage's output schema (ontology/schemas, plan M1 5.1): pydantic-ai's
StructuredDict hands the schema to the model and takes back whatever comes."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.settings import REPOSITORY_ONTOLOGY
from app.llm.schema import KNOWN_KEYWORDS, KNOWN_TYPES, SCHEMA_DIR, load_schema, schema_errors, storable

SCHEMAS = REPOSITORY_ONTOLOGY / SCHEMA_DIR
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "level", "items"],
    "properties": {
        "title": {"type": "string", "description": "as printed"},
        "level": {"type": ["integer", "null"]},
        "share": {"type": ["number", "null"]},
        "kind": {"type": ["string", "null"], "enum": ["area", "unit", None]},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["n"],
                "properties": {"n": {"type": "integer"}, "done": {"type": "boolean"}},
            },
        },
    },
}
VALID = {"title": "Zahlen", "level": None, "share": 2, "kind": None, "items": [{"n": 1, "done": True}]}


def test_an_answer_of_the_schema_s_form_has_no_errors() -> None:
    assert schema_errors(SCHEMA, VALID) == []
    assert schema_errors(SCHEMA, VALID | {"level": 3, "share": 0.5, "kind": "unit"}) == []


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"title": 3}, "$.title: a string"),
        ({"level": "3"}, "$.level: an integer or null"),
        ({"level": True}, "$.level: an integer or null"),  # a boolean is no number in JSON
        ({"share": "half"}, "$.share: a number or null"),
        ({"kind": "chapter"}, "$.kind: one of"),
        ({"items": [{"n": 1}, {"n": "2"}]}, "$.items[1].n: an integer"),
        ({"items": [{}]}, "$.items[0]: lacks n"),
        ({"items": [{"n": 1, "extra": 1}]}, "$.items[0]: has extra, which the schema does not name"),
        ({"items": {"n": 1}}, "$.items: an array"),
    ],
)
def test_an_answer_out_of_the_schema_s_form_is_told_where(change: dict[str, Any], says: str) -> None:
    errors = schema_errors(SCHEMA, VALID | change)

    assert any(error.startswith(says) for error in errors), errors


def test_an_answer_lacking_a_field_names_it() -> None:
    answer = {key: value for key, value in VALID.items() if key != "items"}

    assert schema_errors(SCHEMA, answer) == ["$: lacks items"]


def test_the_errors_of_a_long_answer_stop_at_a_few() -> None:
    answer = VALID | {"items": [{"n": str(n)} for n in range(50)]}

    assert len(schema_errors(SCHEMA, answer)) == 10


@pytest.mark.parametrize("path", sorted(SCHEMAS.glob("*.schema.json")), ids=lambda path: path.name)
def test_every_keyword_the_ontology_s_schemas_use_is_one_the_check_knows(path: Path) -> None:
    # a keyword it does not know it would pass over: a schema using one fails here, not silently
    used: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            used.update(node)
            for key, value in node.items():
                if key == "properties":
                    for each in value.values():
                        walk(each)
                elif key in ("items", "additionalProperties"):
                    walk(value)

    walk(json.loads(path.read_text(encoding="utf-8")))

    assert used <= KNOWN_KEYWORDS, sorted(used - KNOWN_KEYWORDS)


@pytest.mark.parametrize("path", sorted(SCHEMAS.glob("*.schema.json")), ids=lambda path: path.name)
def test_every_form_the_ontology_s_schemas_give_a_keyword_is_one_the_check_knows(path: Path) -> None:
    # additionalProperties as a schema or true, items as a list, a type it has no test for: the
    # check would pass them over or fail on them in the middle of a paid run
    unknown: list[str] = []

    def walk(node: dict[str, Any], where: str) -> None:
        kinds = node.get("type", [])
        unknown.extend(
            f"{where}: type {kind}"
            for kind in ([kinds] if isinstance(kinds, str) else kinds)
            if kind not in KNOWN_TYPES
        )
        if node.get("additionalProperties", False) is not False:
            unknown.append(f"{where}: additionalProperties other than false")
        if "items" in node and not isinstance(node["items"], dict):
            unknown.append(f"{where}: items other than one schema")
        for name, each in node.get("properties", {}).items():
            walk(each, f"{where}.{name}")
        if isinstance(node.get("items"), dict):
            walk(node["items"], f"{where}[]")

    walk(json.loads(path.read_text(encoding="utf-8")), "$")

    assert unknown == []


def test_a_stage_s_schema_is_read_by_its_name() -> None:
    schema = load_schema(SCHEMAS, "x4-aussagen")

    assert schema["type"] == "object"
    with pytest.raises(FileNotFoundError):
        load_schema(SCHEMAS, "x9-nichts")
    with pytest.raises(ValueError, match="name"):
        load_schema(SCHEMAS, "../profile/schule")


def test_a_text_the_store_takes_not_is_made_storable_wherever_it_stands() -> None:
    # a NUL and a lone surrogate - half a pair, no character - each become the replacement sign
    nul, lone, sign = chr(0), chr(0xD800), chr(0xFFFD)

    made = storable({"a" + nul: ["b" + lone + "c", 3, None, {"d": lone}]})

    assert made == {"a" + sign: ["b" + sign + "c", 3, None, {"d": sign}]}
