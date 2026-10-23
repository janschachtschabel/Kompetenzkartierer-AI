"""The IRIs of works, documents and nodes, and the codes the pipeline assigns (konzept §11).

A work is named by its country and short title, a document by its issuer, short title and
edition, a node by the path of its codes under its document ("…/lf-5", "…/if-5/st-3"). A node
without a code gets its position among its siblings (``cur:codeAssigned``), named ``pos-<n>``, and
so does one whose code holds no ASCII letter or digit (a Greek letter, a bullet). Siblings whose
segments meet - a code printed twice, or printed as "Pos. 3" beside an assigned third - are
counted on: "lf-5", "lf-5-2". The base is the service's (``IRI_BASE``, set when documents are
frozen, plan M1 9.6); until then a document carries a draft IRI from its id, and its nodes are
named once it is frozen. Each part is a slug of a hundred signs at most: lowercase ASCII, the
German letters spelt out ("ä" as "ae", "ß" as "ss"), anything else between words a hyphen.
"""

import re
import unicodedata
from collections.abc import Sequence
from uuid import UUID

_SPELT_OUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_OTHER = re.compile(r"[^a-z0-9]+")
# an http(s) IRI ending in a slash, without credentials, query or fragment
_BASE = re.compile(r"https?://[^/\s@?#]+/(?:[^\s?#]*/)?")
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
    return f"{_checked(base)}work/{slug(region)}/{slug(short_title)}"


def document_iri(base: str, issuer: str, short_title: str, edition: str) -> str:
    """The document's IRI: ``<base>doc/<issuer>/<short title>/<edition>``."""
    return f"{_checked(base)}doc/{slug(issuer)}/{slug(short_title)}/{slug(edition)}"


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


def node_segments(siblings: Sequence[tuple[str, bool]]) -> list[str]:
    """The segments of siblings in their order, from each one's code and whether it was assigned."""
    taken: set[str] = set()
    segments: list[str] = []
    for place, (code, assigned) in enumerate(siblings, start=1):
        try:
            segment = f"pos-{slug(code)}" if assigned else slug(code)
        except ValueError:  # no ASCII letter or digit to name it by: its place names it
            segment = f"pos-{place}"
        made, count = segment, 1
        while made in taken:
            count += 1
            made = f"{segment}-{count}"
        taken.add(made)
        segments.append(made)
    return segments


def assign_code(position: int) -> str:
    """The code of a node the document prints none for: its position among its siblings."""
    if position < 1:
        raise ValueError(f"a position counts from 1, not {position}")
    return str(position)


def _checked(base: str) -> str:
    if _BASE.fullmatch(base) is None:
        raise ValueError(f"an IRI base is an http(s) IRI ending in a slash, not {base!r}")
    return base
