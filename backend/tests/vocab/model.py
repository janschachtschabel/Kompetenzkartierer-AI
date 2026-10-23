"""A small model folder for the vocabulary tests, with the three folders the reader requires."""

from pathlib import Path

PREFIXES = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix cur: <https://w3id.org/wlo/curriculum/core#> .
@prefix ex: <https://example.org/vocab/> .
"""

# What a cue names of the core: a sector, its role and kind, a place, countries, a class as target
LEXICON_CORE = r"""
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix cur: <https://w3id.org/wlo/curriculum/core#> .
@prefix cv: <https://w3id.org/wlo/curriculum/vocab#> .
@prefix land: <https://w3id.org/wlo/curriculum/region/> .

cv:EducationSectors a skos:ConceptScheme .
cv:sec_school a skos:Concept ; skos:inScheme cv:EducationSectors ; skos:notation "school" .
cv:sec_vocational a skos:Concept ; skos:inScheme cv:EducationSectors ; skos:notation "vocational" .
cv:CueRoles a skos:ConceptScheme .
cv:role_cue a skos:Concept ; skos:inScheme cv:CueRoles .
cv:role_homonym a skos:Concept ; skos:inScheme cv:CueRoles .
cv:CueKinds a skos:ConceptScheme .
cv:ck_term a skos:Concept ; skos:inScheme cv:CueKinds .
cv:ck_headingPattern a skos:Concept ; skos:inScheme cv:CueKinds .
cv:Occurrences a skos:ConceptScheme .
cv:occ_titlePage a skos:Concept ; skos:inScheme cv:Occurrences .
cv:LayoutMarkers a skos:ConceptScheme .
cv:mark_bold a skos:Concept ; skos:inScheme cv:LayoutMarkers .
land:Regions a skos:ConceptScheme .
land:DE a skos:Concept ; skos:inScheme land:Regions ; skos:notation "DE" .
land:DE-NW a skos:Concept ; skos:inScheme land:Regions ; skos:notation "DE-NW" ; skos:broader land:DE .
cur:Curriculum a rdfs:Class .
"""

PROFILE_PREFIXES = r"""
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix cur: <https://w3id.org/wlo/curriculum/core#> .
@prefix cv: <https://w3id.org/wlo/curriculum/vocab#> .
@prefix land: <https://w3id.org/wlo/curriculum/region/> .
@prefix schul: <https://w3id.org/wlo/curriculum/profile/school#> .
"""

# The school's profile: two document types, a cue with every field, a pattern's cue
SCHOOL_PROFILE = (
    PROFILE_PREFIXES
    + r"""
schul:DocumentTypes a skos:ConceptScheme .
schul:dt-Lehrplan a cur:DocumentType ; skos:inScheme schul:DocumentTypes .
schul:dt-Kernlehrplan a cur:DocumentType ; skos:inScheme schul:DocumentTypes .

schul:Terminology a cur:TerminologyProfile ; rdfs:label "Terminologie Schule"@de ;
    cur:profileScope cv:sec_school ; cur:hasCue schul:cue-klp , schul:cue-lf .

schul:cue-klp a cur:LexicalCue ; cur:surfaceForm "Kernlehrplan" ; cur:cueRole cv:role_homonym ;
    cur:cueKind cv:ck_term ; cur:mapsTo schul:dt-Kernlehrplan , cur:Curriculum ;
    cur:alsoMapsTo schul:dt-Lehrplan ; cur:occursIn cv:occ_titlePage ; cur:scopeRegion land:DE-NW , land:DE ;
    cur:scopeDocumentType schul:dt-Lehrplan ; cur:planGeneration "G9" ; cur:scopeIssuer "MSB NRW" ;
    cur:validFrom "2023-08-01"^^xsd:date ; cur:strength 0.9 ; cur:verified true ;
    cur:recognitionHint "NRW: Kernlehrplan der Sekundarstufe I."@de ;
    cur:negativeHint "Nicht der KMK-Plan."@de ;
    cur:positiveExample "Kernlehrplan Mathematik" ; cur:negativeExample "Lehrplan" ;
    prov:wasDerivedFrom <https://example.org/quelle> .

schul:cue-lf a cur:LexicalCue ; cur:pattern "^Lernfeld\\s+[0-9]+" ; cur:cueRole cv:role_cue ;
    cur:cueKind cv:ck_headingPattern ; cur:mapsTo schul:dt-Lehrplan .
"""
)


def write_model(root: Path, vocabulary: str, profiles: dict[str, str] | None = None) -> Path:
    """``vocabulary`` (Turtle with its own prefixes) as vokabulare/farben.ttl beside empty model
    files; ``profiles``: more files under profile/, by their path there ("laender/x.ttl")."""
    for folder in ("ontologie", "profile"):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / "empty.ttl").write_text(PREFIXES, encoding="utf-8")
    (root / "vokabulare").mkdir(parents=True, exist_ok=True)
    (root / "vokabulare" / "farben.ttl").write_text(vocabulary, encoding="utf-8")
    for name, content in (profiles or {}).items():
        path = root / "profile" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root
