"""The IRIs of works, documents and nodes, and the codes the pipeline assigns (konzept §11).

A work is named by its country and short title, a document by its work's country, its issuer, the work's short
title and its edition, a node by the path of its codes under its document ("…/lf-5", "…/if-5/st-3"), a
statement by its number under its node ("…/lf-5/s-3", numbers given once, plan M1 9.6). A node without a code
gets its position among its siblings (``cur:codeAssigned``), named ``pos-<n>``, and so does one whose code
holds no ASCII letter or digit (a Greek letter, a bullet). Siblings whose segments meet - a code printed
twice, or printed as "Pos. 3" beside an assigned third - are counted on: "lf-5", "lf-5-2"; so is a code that
would read as a statement's number ("S 1" as "s-1-2"), and "S" twice is "s", "s-1-2" (SegmentCounter). The
base is the service's (``IRI_BASE``, set when documents are frozen, plan M1 9.6); until then a document
carries a draft IRI from its id, and its nodes are named once it is frozen. Each part is a slug of a hundred
signs at most: lowercase ASCII, the German letters spelt out ("ä" as "ae", "ß" as "ss"), anything else between
words a hyphen.
"""

import re
import unicodedata
from collections.abc import Sequence
from uuid import UUID

_SPELT_OUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_OTHER = re.compile(r"[^a-z0-9]+")
# an http(s) IRI ending in a slash, without credentials, query or fragment
_BASE = re.compile(r"https?://[^/\s@?#]+/(?:[^\s?#]*/)?")
# a statement's segment under its node (statement_iri): no child node takes it
_STATEMENT = re.compile(r"s-\d+")
_LONGEST = 100


def slug(text: str) -> str:
    """``text`` as one part of an IRI, cut after its last whole word within a hundred signs;
    ValueError where it holds no ASCII letter or digit."""
    composed = unicodedata.normalize("NFC", text).lower().translate(_SPELT_OUT)
    ascii_only = unicodedata.normalize("NFKD", composed).encode("ascii", "ignore").decode("ascii")
    made = _OTHER.sub("-", ascii_only).strip("-")
    if not made:
        raise ValueError(f"no slug in {text!r}: it holds no ASCII letter or digit")
    if len(made) > _LONGEST:
        within = made[: _LONGEST + 1]
        made = within.rsplit("-", 1)[0] if "-" in within else made[:_LONGEST]
    return made


def work_iri(base: str, region: str, short_title: str) -> str:
    """The work's IRI: ``<base>work/<country>/<short title>``."""
    return f"{checked_base(base)}work/{slug(region)}/{slug(short_title)}"


def document_iri(base: str, region: str, issuer: str, short_title: str, edition: str) -> str:
    """The document's IRI: ``<base>doc/<country>/<issuer>/<short title>/<edition>``, the country and the
    short title its work's - the country first, as two countries' ministries may bear one name."""
    return f"{checked_base(base)}doc/{slug(region)}/{slug(issuer)}/{slug(short_title)}/{slug(edition)}"


def draft_iri(document_id: UUID) -> str:
    """The IRI a document carries until it is frozen."""
    return document_id.urn


def node_iri(document: str, segments: Sequence[str]) -> str:
    """The node's IRI: its frozen document's and the segments of its path from the top."""
    if not document.startswith(("https://", "http://")):
        raise ValueError(f"a node is named under its frozen document's http(s) IRI, not {document!r}")
    if not segments:
        raise ValueError("a node's IRI needs a segment at least")
    return "/".join([document, *segments])


def statement_iri(node: str, number: int) -> str:
    """The statement's IRI: its node's and its number among those its node has given."""
    if not node.startswith(("https://", "http://")):
        raise ValueError(f"a statement is named under its frozen node's http(s) IRI, not {node!r}")
    if number < 1:
        raise ValueError(f"a statement's number counts from 1, not {number}")
    return f"{node}/s-{number}"


def node_segments(siblings: Sequence[tuple[str, bool]]) -> list[str]:
    """The segments of siblings in their order, from each one's code and whether it was assigned."""
    counter = SegmentCounter()
    segments: list[str] = []
    for place, (code, assigned) in enumerate(siblings, start=1):
        try:
            segment = f"pos-{slug(code)}" if assigned else slug(code)
        except ValueError:  # no ASCII letter or digit to name it by: its place names it
            segment = f"pos-{place}"
        segments.append(counter.take(segment))
    return segments


class SegmentCounter:
    """The segments of one group of siblings, each given once, past those in ``taken`` (the set it adds
    to)."""

    def __init__(self, taken: set[str] | None = None) -> None:
        self._taken = set() if taken is None else taken
        # by segment, the count it was last given at: every count below it is taken, and stays so
        self._counts: dict[str, int] = {}

    def take(self, segment: str) -> str:
        """``segment`` where none holds it, else the first of ``<segment>-2``, ``-3``, ... none holds; one
        that reads as a statement's (``s-<n>``) is passed over, and under ``s``, whose every count would, the
        count goes on from ``s-1`` ("s-1-2")."""
        stem = "s-1" if segment == "s" else segment
        count = self._counts.get(segment, 1)
        made = segment if count == 1 else f"{stem}-{count}"
        while made in self._taken or _STATEMENT.fullmatch(made):
            count += 1
            made = f"{stem}-{count}"
        self._counts[segment] = count
        self._taken.add(made)
        return made


def assign_code(position: int) -> str:
    """The code of a node the document prints none for: its position among its siblings."""
    if position < 1:
        raise ValueError(f"a position counts from 1, not {position}")
    return str(position)


def checked_base(base: str) -> str:
    """``base`` where it is an http(s) IRI ending in a slash, without credentials, query or fragment;
    ValueError where not."""
    if _BASE.fullmatch(base) is None:
        raise ValueError(f"an IRI base is an http(s) IRI ending in a slash, not {base!r}")
    return base
