"""X1's answer read into a document's profile (plan M1 6.2; schema x1-dokumentprofil).

The keys of the call (D…, T…; app/pipeline/prompts/x1_profile.py) go back to their IRIs, the
answer's codes - enums named after the vocabularies' notations (``x-cv-scheme``) - to the active
values of their schemes, its dates to YYYY, YYYY-MM or YYYY-MM-DD as far as their wording goes
(their wording stays with the run). Whatever it names that the lists, the vocabularies or the
conversion do not hold is a finding (warning) and no value - an answer is a proposal, never a
crash. A specification or variant without a title or with a key given before is left out with a
finding; wording longer than its column is cut with one. The regions and the sector are the
document's from when it was made: where X1 reads others, that is a finding (info), never a change.
"""

import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from app.db.findings import Finding
from app.domain.l1 import Severity
from app.pipeline.prompts.x1_profile import ProfileLists

_MONTHS = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
    "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}  # fmt: skip
_MONTH = "|".join(_MONTHS)
_Parts = tuple[str, int | str, int | str | None]
# The wordings of a date, the fullest first; the first that is found decides
_DATES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], _Parts]]] = [
    (
        re.compile(rf"\b(\d{{1,2}})\.\s*({_MONTH})\s+(\d{{4}})\b", re.I),
        lambda m: (m[3], _MONTHS[m[2].lower()], m[1]),
    ),
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (m[1], m[2], m[3])),
    (re.compile(rf"\b({_MONTH})\s+(\d{{4}})\b", re.I), lambda m: (m[2], _MONTHS[m[1].lower()], None)),
    (re.compile(r"\b(\d{1,2})\.(\d{4})\b"), lambda m: (m[2], m[1], None)),
    (re.compile(r"\b(\d{4})-(\d{2})\b"), lambda m: (m[1], m[2], None)),
]
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
# The columns' lengths (0013_l1_documents.sql)
_TITLE, _ISSUER, _EDITION, _KEY, _FIELD, _LABEL = 1000, 500, 200, 100, 2000, 500


@dataclass(frozen=True)
class ProfileContext:
    """What an answer is read against: the document as it was made, its conversion's blocks, the
    call's keys and the schemes' values by notation (``codes["LegalForms"]["law"]``)."""

    document_id: UUID
    sector: str  # its notation
    regions: tuple[str, ...]
    block_ids: Collection[str]
    lists: ProfileLists
    codes: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    kind: str  # a cv:VariantKinds IRI


@dataclass(frozen=True)
class Specification:
    key: str
    kind: str  # its core class: curriculum, competencyFramework, …
    title: str
    field_text: str | None
    applicability: dict[str, Any]  # its codes as IRIs, its wording as given
    evidence: tuple[str, ...]
    variants: tuple[Variant, ...]


@dataclass(frozen=True)
class Profile:
    title: str | None
    document_type: str | None
    legal_form: str | None
    binding: str | None
    lifecycle: str | None
    issuer: str | None
    edition: str | None
    issued: str | None
    valid_from: str | None
    evidence: tuple[str, ...]
    specifications: tuple[Specification, ...]
    term_mappings: tuple[dict[str, Any], ...]
    new_terms: tuple[dict[str, Any], ...]
    said: dict[str, Any]  # the wording the values were read from, for the run's result
    findings: tuple[Finding, ...] = field(default=())


def parse_date(wording: str | None) -> str | None:
    """The date a wording gives, as far as it goes ("im Juni 2019" 2019-06); None where it gives none
    or one that is no date."""
    if wording is None:
        return None
    for pattern, parts in _DATES:
        if (found := pattern.search(wording)) is not None:
            return _date(*parts(found))
    year = _YEAR.search(wording)
    return None if year is None else year[1]


def read_profile(answer: Mapping[str, Any], context: ProfileContext) -> Profile:
    """The profile an answer of the schema's form gives the document."""
    reading = _Reading(context)
    given = answer["document"]
    path = "$.document"
    # read in the answer's order, so its findings come in it
    title = reading.text(given["title"], _TITLE, f"{path}.title")
    document_type = reading.key(given["documentType"], context.lists.document_types, f"{path}.documentType")
    legal_form = reading.code("LegalForms", given["legalForm"], f"{path}.legalForm")
    binding = reading.code("DocumentBindings", given["documentBinding"], f"{path}.documentBinding")
    lifecycle = reading.code("Lifecycles", given["lifecycle"], f"{path}.lifecycle")
    issuer = reading.text(given["issuerText"], _ISSUER, f"{path}.issuerText")
    edition = reading.text(given["editionText"], _EDITION, f"{path}.editionText")
    evidence = reading.blocks(given["evidenceBlockIds"], f"{path}.evidenceBlockIds")
    reading.compare_regions(given["regions"], f"{path}.regions")
    reading.compare_sectors(given["educationSectors"], f"{path}.educationSectors")
    specifications = reading.specifications(answer["specifications"])
    mappings = [
        {
            "documentTerm": term["documentTerm"],
            "mapsTo": target,
            "evidenceBlockId": reading.block(
                term["evidenceBlockId"], f"$.termMappings[{at}].evidenceBlockId"
            ),
        }
        for at, term in enumerate(answer["termMappings"])
        if (target := reading.key(term["mapsTo"], context.lists.terms, f"$.termMappings[{at}].mapsTo"))
    ]
    new_terms = [
        {
            "documentTerm": term["documentTerm"],
            "suggestedFunction": reading.code(
                "NodeFunctions", term["suggestedFunction"], f"$.newTerms[{at}].suggestedFunction"
            ),
            "evidenceBlockId": reading.block(term["evidenceBlockId"], f"$.newTerms[{at}].evidenceBlockId"),
        }
        for at, term in enumerate(answer["newTerms"])
    ]
    said = {
        "issuedText": given["issuedText"],
        "validFromText": given["validFromText"],
        "regions": list(given["regions"]),
        "educationSectors": list(given["educationSectors"]),
    }
    return Profile(
        title=title,
        document_type=document_type,
        legal_form=legal_form,
        binding=binding,
        lifecycle=lifecycle,
        issuer=issuer,
        edition=edition,
        issued=parse_date(given["issuedText"]),
        valid_from=parse_date(given["validFromText"]),
        evidence=evidence,
        specifications=tuple(specifications),
        term_mappings=tuple(mappings),
        new_terms=tuple(new_terms),
        said=said,
        findings=tuple(reading.findings),
    )


def _date(year: str, month: int | str, day: int | str | None) -> str | None:
    try:
        made = date(int(year), int(month), int(day) if day is not None else 1)
    except ValueError:
        return None
    if day is None:
        return f"{made.year:04d}-{made.month:02d}"
    return made.isoformat()


class _Reading:
    """One answer being read, with the findings it gives."""

    def __init__(self, context: ProfileContext) -> None:
        self.context = context
        self.findings: list[Finding] = []

    def note(self, rule: str, severity: Severity, path: str, message: str, **details: Any) -> None:
        self.findings.append(Finding(rule, severity, self.context.document_id, message, path, details))

    def text(self, value: str | None, most: int, path: str) -> str | None:
        """Wording as given; None where it is blank, cut to ``most`` signs with a finding."""
        if value is None or not value.strip():
            return None
        if len(value) > most:
            self.note("x1.value_cut", "info", path, f"cut to its {most} signs", length=len(value))
            return value[:most]
        return value

    def key(self, value: str, keys: Mapping[str, str], path: str) -> str | None:
        if value in keys:
            return keys[value]
        self.note("x1.unknown_key", "warning", path, "a key the question did not list", key=value)
        return None

    def code(self, scheme: str, value: str | None, path: str) -> str | None:
        if value is None:
            return None
        found = self.context.codes.get(scheme, {}).get(value)
        if found is None:
            self.note(
                "x1.unknown_value", "warning", path, f"no active value {value!r} of {scheme}", value=value
            )
        return found

    def block(self, value: str | None, path: str) -> str | None:
        if value is None or value in self.context.block_ids:
            return value
        self.note("x1.unknown_block", "warning", path, "a block the conversion does not hold", block=value)
        return None

    def blocks(self, values: Sequence[str], path: str) -> tuple[str, ...]:
        kept = [self.block(value, f"{path}[{at}]") for at, value in enumerate(values)]
        return tuple(dict.fromkeys(value for value in kept if value is not None))

    def compare_regions(self, found: Sequence[str], path: str) -> None:
        if found and set(found) != set(self.context.regions):
            self.note(
                "x1.regions_differ",
                "info",
                path,
                "the document reads as of other regions than it was made for",
                found=sorted(set(found)),
                document=sorted(self.context.regions),
            )

    def compare_sectors(self, found: Sequence[str], path: str) -> None:
        others = sorted(set(found) - {self.context.sector})
        if others:
            self.note(
                "x1.other_sectors", "info", path, "the document reads as of other sectors too", sectors=others
            )

    def specifications(self, given: Sequence[Mapping[str, Any]]) -> list[Specification]:
        made: list[Specification] = []
        for at, item in enumerate(given):
            path = f"$.specifications[{at}]"
            key = self._unique(item["key"], {made_one.key for made_one in made}, f"{path}.key")
            title = self._titled(item["title"], _TITLE, f"{path}.title")
            if key is None or title is None:
                continue
            applicability = item["applicability"]
            made.append(
                Specification(
                    key=key,
                    kind=item["kind"],
                    title=title,
                    field_text=self.text(item["fieldText"], _FIELD, f"{path}.fieldText"),
                    applicability={
                        "sector": self.code(
                            "EducationSectors", applicability["sector"], f"{path}.applicability.sector"
                        ),
                        "formality": self.code(
                            "Formalities", applicability["formality"], f"{path}.applicability.formality"
                        ),
                        "timeKind": self.code(
                            "TimeKinds", applicability["timeKind"], f"{path}.applicability.timeKind"
                        ),
                        **{
                            name: applicability[name]
                            for name in ("timeText", "levelText", "institutionText", "targetGroupText")
                        },
                    },
                    evidence=self.blocks(
                        applicability["evidenceBlockIds"], f"{path}.applicability.evidenceBlockIds"
                    ),
                    variants=tuple(self._variants(item["variants"], path)),
                )
            )
        return made

    def _variants(self, given: Sequence[Mapping[str, Any]], within: str) -> list[Variant]:
        made: list[Variant] = []
        for at, item in enumerate(given):
            path = f"{within}.variants[{at}]"
            key = self._unique(item["key"], {variant.key for variant in made}, f"{path}.key")
            label = self._titled(item["label"], _LABEL, f"{path}.label")
            kind = self.code("VariantKinds", item["variantKind"], f"{path}.variantKind")
            if key is not None and label is not None and kind is not None:
                made.append(Variant(key, label, kind))
        return made

    def _unique(self, value: str, taken: Collection[str], path: str) -> str | None:
        key = self._titled(value, _KEY, path)
        if key is not None and key in taken:
            self.note("x1.duplicate_key", "warning", path, "a key given before: left out", key=key)
            return None
        return key

    def _titled(self, value: str, most: int, path: str) -> str | None:
        """Wording a row cannot be without: None, with a finding, where it is blank."""
        found = self.text(value, most, path)
        if found is None:
            self.note("x1.blank_value", "warning", path, "blank: left out")
        return found
