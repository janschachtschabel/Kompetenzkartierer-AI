"""The values of the source register that the Kern does not know (Gesamtplan §7; plan M1).

The database holds the same lists as CHECKs (migration 0006_sources); tests/db/test_sources_schema.py
writes every value named here, so the two cannot drift. In the interface: "ungeprüft" etc.
"""

import re
from pathlib import Path
from typing import Literal

# Where a register entry or hint comes from - never a value's origin in the Kern's sense
Provenance = Literal[
    "upload", "url", "vergleichsdatensatz-v62.493", "laenderrecherche", "ttl", "recherche", "redaktion"
]
# On what terms the document may be used; unclear until the editors say otherwise, with evidence
RightsStatus = Literal["amtlich", "offen_lizenziert", "geschuetzt", "unklar"]
# Who publishes the copy the register points at
SourceType = Literal["amtlich", "archiv", "spiegel", "sekundaer"]
# How far the register has come with the entry: acquired means its file is stored
RegisterStatus = Literal["unchecked", "reachable", "unreachable", "acquired"]
# The datasets whose rows source_seed keeps beside an entry (migration 0008_source_seed)
SeedDataset = Literal["vergleichsdatensatz-v62.493", "laenderrecherche"]
# Where a land's research read a document's row: in the primary document (E) or a secondary source
Evidence = Literal["E", "S"]
# What the check job found at an address (migration 0010_url_check): an answer of 2xx read to its
# end, or one past the upload limit; a refusal (4xx), a request to slow down (429, 503), a server's
# error (5xx); no answer for now (502, 504, a timeout, a broken connection), no answer there can be;
# or robots.txt saying no. A later check asks again what was throttled or unavailable
CheckOutcome = Literal[
    "reachable", "too_large", "refused", "throttled", "server_error", "unavailable", "unreachable", "robots"
]
# What the bytes at an address are, as far as their first ones and the server's type tell
DetectedKind = Literal["pdf", "docx", "rtf", "html", "other"]
# The comparison dataset and where its published files lie: data/seed/ of the repository, or
# /srv/data/seed in the API image
COMPARISON_DATASET: SeedDataset = "vergleichsdatensatz-v62.493"
SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed" / "vergleichsdatensatz"

# The concept scheme the sector of a source belongs to (cur-vokabular.ttl)
EDUCATION_SECTORS = "https://w3id.org/wlo/curriculum/vocab#EducationSectors"

_LAND = re.compile(r"[A-Z]{2}")


def land_country(code: str) -> str | None:
    """The country of a land's code as the comparison dataset writes it: "BY" is DE-BY (ISO
    3166-2), "DE" (the federation's rows, KMK) Germany itself; anything else is none."""
    code = code.strip()
    if code == "DE":
        return "DE"
    return f"DE-{code}" if _LAND.fullmatch(code) else None
