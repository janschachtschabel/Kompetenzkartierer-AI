"""The editor's form schema (plan M1 9.1; Paket 9 G10): the fields of a node and of a statement an editor
may set, and the active values of their lists in a sector's profile - its node types and statement
subkinds with label, definition, note and examples.

The fields are named here, not read from the shapes at run time (rdflib's literal normalisation is a
process-wide switch, app/vocab/loader.py): each field that the core's shapes know names their property
(``path``), and tests/vocab/test_forms.py holds the form no laxer than the shapes demand - a title the
shapes leave optional the form asks for. Not in M1's form: a profile's own properties, L2's fields
(level, time, workload), layout markers.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import psycopg

from app.domain.l1 import WORDING_FIELDS
from app.vocab.lookup import (
    ConceptDetails,
    concept_details,
    notations_of,
    profile_concepts,
    terminology_profile,
)

CV = "https://w3id.org/wlo/curriculum/vocab#"
FieldKind = Literal["text", "longtext", "concept", "concepts"]
MOST_TEXT = 2_000  # the store's limit of a title, a lead-in, a wording field, signs (migration l1_nodes)
MOST_VERBATIM = 20_000
MOST_CODE = 100


@dataclass(frozen=True)
class FormField:
    """``key`` as the API names it; ``values``: where a list's values come from - a scheme's IRI, or a
    profile's ``node_types``/``subkinds``; ``path``: the shapes' property it follows, none for a field the
    shapes say nothing of."""

    key: str
    kind: FieldKind
    required: bool
    many: bool
    most: int | None = None
    values: str | None = None
    path: str | None = None


NODE_FIELDS: tuple[FormField, ...] = (
    FormField("original_title", "text", True, False, most=MOST_TEXT, path="cur:originalTitle"),
    FormField("function", "concept", True, False, values=CV + "NodeFunctions", path="cur:nodeFunction"),
    FormField("node_type", "concept", False, False, values="node_types", path="cur:nodeType"),
    FormField("code", "text", False, False, most=MOST_CODE),
    FormField("obligation", "concept", False, False, values=CV + "Obligations", path="cur:obligation"),
)
STATEMENT_FIELDS: tuple[FormField, ...] = (
    FormField("verbatim", "longtext", True, False, most=MOST_VERBATIM, path="cur:verbatim"),
    FormField("lead_in", "text", False, False, most=MOST_TEXT),
    FormField(
        "statement_kind", "concept", True, False, values=CV + "StatementKinds", path="cur:statementKind"
    ),
    FormField("subkind", "concept", False, False, values="subkinds", path="cur:statementSubkind"),
    FormField("addressees", "concepts", True, True, values=CV + "Addressees", path="cur:addressee"),
    FormField("obligation", "concept", False, False, values=CV + "Obligations", path="cur:obligation"),
    *(FormField(name, "text", False, False, most=MOST_TEXT) for name in WORDING_FIELDS),
)


@dataclass(frozen=True)
class Form:
    """A sector's form: its fields, and the values of each list field by the field's key, active ones
    alone, in the order of their labels."""

    sector: str
    profile: str
    node: tuple[FormField, ...]
    statement: tuple[FormField, ...]
    values: Mapping[str, tuple[ConceptDetails, ...]]


async def form_of(connection: psycopg.AsyncConnection, sector: str) -> Form | None:
    """The form for documents of ``sector`` (a notation of cv:EducationSectors), or None where the sector
    has no active profile."""
    profile = await terminology_profile(connection, sector)
    chosen = await profile_concepts(connection, sector)
    if profile is None or chosen is None:
        return None
    own = {"node_types": list(chosen.node_types), "subkinds": list(chosen.subkinds)}
    values: dict[str, tuple[ConceptDetails, ...]] = {}
    for field in (*NODE_FIELDS, *STATEMENT_FIELDS):
        if field.values is None or field.key in values:
            continue
        iris = own.get(field.values)
        if iris is None:
            iris = list((await notations_of(connection, field.values)).values())
        details = await concept_details(connection, iris)
        values[field.key] = tuple(sorted(details.values(), key=lambda concept: concept.label.casefold()))
    return Form(sector, profile, NODE_FIELDS, STATEMENT_FIELDS, values)
