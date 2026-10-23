"""The IRIs of works, documents and nodes, and the codes the pipeline assigns (konzept §11).

A work is named by its country and short title, a document by its issuer, short title and
edition, a node by the path of its codes under its document ("…/lf-5", "…/if-5/st-3"). A node
without a code gets its position among its siblings (``cur:codeAssigned``), named ``pos-<n>`` so it
never meets a code the document prints. Siblings printing one code twice are counted on: "lf-5",
"lf-5-2". The base is the service's (``IRI_BASE``, set when documents are frozen, plan M1 9.6);
until then a document carries a draft IRI from its id. Each part is a slug: lowercase ASCII, the
German letters spelt out ("ä" as "ae", "ß" as "ss"), anything else between words a hyphen.
"""

import re
import unicodedata
from collections.abc import Sequence
from uuid import UUID

_SPELT_OUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_OTHER = re.compile(r"[^a-z0-9]+")
_BASE = re.compile(r"https?://[^/\s]+/(?:[^\s]*/)?")


def slug(text: str) -> str:
    """``text`` as one part of an IRI; ValueError where it holds no letter or digit."""
    folded = unicodedata.normalize("NFKD", text.lower().translate(_SPELT_OUT))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    made = _OTHER.sub("-", ascii_only).strip("-")
    if not made:
        raise ValueError(f"no slug in {text!r}: it holds no letter or digit")
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
    """The node's IRI: its document's and the segments of its path from the top."""
    if not segments:
        raise ValueError("a node's IRI needs a segment at least")
    return "/".join([document, *segments])


def node_segments(siblings: Sequence[tuple[str, bool]]) -> list[str]:
    """The segments of siblings in their order, from each one's code and whether it was assigned."""
    taken: set[str] = set()
    segments: list[str] = []
    for code, assigned in siblings:
        segment = f"pos-{slug(code)}" if assigned else slug(code)
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
