"""The values of the source register that the Kern does not know (Gesamtplan §7; plan M1).

The database holds the same lists as CHECKs (migration 0006_sources); tests/db/test_sources_schema.py
writes every value named here, so the two cannot drift. In the interface: "ungeprüft" etc.
"""

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
# The comparison dataset and where its published files lie: data/seed/ of the repository, or
# /srv/data/seed in the API image
COMPARISON_DATASET: SeedDataset = "vergleichsdatensatz-v62.493"
SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed" / "vergleichsdatensatz"

# The concept scheme the sector of a source belongs to (cur-vokabular.ttl)
EDUCATION_SECTORS = "https://w3id.org/wlo/curriculum/vocab#EducationSectors"
