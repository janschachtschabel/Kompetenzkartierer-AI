"""X1's questions read the values of every scheme their schemas' enums name (``x-cv-scheme``): a
scheme the schema gains and the question does not read would make each of its values a finding."""

from pathlib import Path
from typing import Any

from app.llm.schema import load_schema
from app.pipeline.prompts import x1_outline, x1_profile
from app.pipeline.x1_question import OUTLINE_SCHEMES, SCHEMES

SCHEMAS = Path(__file__).resolve().parents[3] / "ontology" / "schemas"


def named_schemes(schema: Any) -> set[str]:
    if isinstance(schema, dict):
        own = {schema["x-cv-scheme"]} if "x-cv-scheme" in schema else set()
        return own.union(*(named_schemes(value) for value in schema.values()))
    if isinstance(schema, list):
        return set().union(*(named_schemes(value) for value in schema))
    return set()


def test_the_profile_s_question_reads_every_scheme_its_schema_names() -> None:
    assert named_schemes(load_schema(SCHEMAS, x1_profile.SCHEMA)) == set(SCHEMES)


def test_the_outline_s_question_reads_every_scheme_its_schema_names() -> None:
    assert named_schemes(load_schema(SCHEMAS, x1_outline.SCHEMA)) == set(OUTLINE_SCHEMES)
