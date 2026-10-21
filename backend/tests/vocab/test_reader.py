"""Reading the vocabularies from the ontology's Turtle files, without a database."""

import shutil
from pathlib import Path

import pytest
from rdflib import Graph, Literal

from app.vocab.loader import MODEL_DIRS, VocabularyError, read_vocabulary

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
LEVEL = "https://w3id.org/wlo/curriculum/level/"
EX = "https://example.org/vocab/"

COLOURS = """\
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix cur: <https://w3id.org/wlo/curriculum/core#> .
@prefix ex: <https://example.org/vocab/> .

ex:colours a skos:ConceptScheme ; skos:prefLabel "Farben"@de, "Colours"@en .

ex:red a skos:Concept ; skos:inScheme ex:colours ; skos:topConceptOf ex:colours ;
    skos:prefLabel "Rot"@de ; skos:notation "R" ; cur:rank 1 .

ex:dark-red a skos:Concept ; skos:inScheme ex:colours ; skos:broader ex:red ;
    skos:prefLabel "Dunkelrot"@de ; skos:altLabel "Weinrot"@de, "Bordeaux"@de ;
    skos:definition "Ein dunkles Rot."@de .
"""


def vocabulary_dir(root: Path, content: str = COLOURS) -> Path:
    (root / "vokabulare").mkdir(parents=True, exist_ok=True)
    (root / "vokabulare" / "farben.ttl").write_text(content, encoding="utf-8")
    return root


def independent_level_counts() -> tuple[int, int]:
    """The counts by a SPARQL query of their own, not by the loader's code."""
    graph = Graph()
    for directory in MODEL_DIRS:
        for path in sorted((ONTOLOGY / directory).glob("*.ttl")):
            graph.parse(path, format="turtle")
    query = """
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX cur: <https://w3id.org/wlo/curriculum/core#>
        SELECT (COUNT(DISTINCT ?scheme) AS ?schemes) (COUNT(DISTINCT ?level) AS ?levels) WHERE {
            ?scheme a cur:LevelScheme . OPTIONAL { ?level skos:inScheme ?scheme }
            FILTER(STRSTARTS(STR(?scheme), ?prefix))
        }
    """
    [row] = list(graph.query(query, initBindings={"prefix": Literal(LEVEL)}))
    return int(row[0]), int(row[1])  # type: ignore[index]


def test_the_ontology_has_the_level_schemes_and_levels_the_plan_counts() -> None:
    vocabulary = read_vocabulary(ONTOLOGY)

    schemes = [iri for iri in vocabulary.schemes if iri.startswith(LEVEL)]
    levels = [concept for concept in vocabulary.concepts.values() if concept.scheme.startswith(LEVEL)]
    assert (len(schemes), len(levels)) == independent_level_counts() == (24, 135)


def test_a_concept_keeps_its_labels_notation_definition_and_broader(tmp_path: Path) -> None:
    vocabulary = read_vocabulary(vocabulary_dir(tmp_path))

    red, dark = vocabulary.concepts[EX + "red"], vocabulary.concepts[EX + "dark-red"]
    assert vocabulary.schemes[EX + "colours"].pref_labels == {"de": "Farben", "en": "Colours"}
    assert (red.scheme, red.notation, red.pref_labels) == (EX + "colours", "R", {"de": "Rot"})
    assert dark.alt_labels == {"de": ["Bordeaux", "Weinrot"]}
    assert dark.definitions == {"de": "Ein dunkles Rot."}
    assert dark.broader == [EX + "red"]
    assert red.types == ["http://www.w3.org/2004/02/skos/core#Concept"]


def test_other_statements_are_kept_as_properties(tmp_path: Path) -> None:
    red = read_vocabulary(vocabulary_dir(tmp_path)).concepts[EX + "red"]

    assert red.properties["https://w3id.org/wlo/curriculum/core#rank"] == [
        {"value": "1", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}
    ]
    assert red.properties["http://www.w3.org/2004/02/skos/core#topConceptOf"] == [{"iri": EX + "colours"}]


def test_the_content_hash_follows_the_bytes_of_the_files(tmp_path: Path) -> None:
    first = read_vocabulary(vocabulary_dir(tmp_path / "a")).content_hash
    same = read_vocabulary(vocabulary_dir(tmp_path / "b")).content_hash
    changed = read_vocabulary(
        vocabulary_dir(tmp_path / "c", COLOURS.replace('"Rot"', '"Rotton"'))
    ).content_hash

    assert first == same
    assert changed != first


@pytest.mark.parametrize(
    ("addition", "fault"),
    [
        (
            "ex:other a skos:ConceptScheme ; skos:prefLabel 'Andere'@de .\nex:red skos:inScheme ex:other .",
            "red",
        ),
        ("ex:blue a skos:Concept ; skos:inScheme ex:colours ; skos:broader ex:nowhere .", "nowhere"),
        ("ex:red skos:prefLabel 'Rot zwei'@de .", "red"),
        ("ex:red skos:notation 'R2' .", "red"),
    ],
    ids=["two-schemes", "unknown-broader", "two-labels-one-language", "two-notations"],
)
def test_a_vocabulary_the_tables_cannot_hold_is_refused(tmp_path: Path, addition: str, fault: str) -> None:
    with pytest.raises(VocabularyError, match=fault):
        read_vocabulary(vocabulary_dir(tmp_path, COLOURS + addition + "\n"))


def test_files_outside_the_model_directories_are_not_read(tmp_path: Path) -> None:
    root = vocabulary_dir(tmp_path)
    shutil.copytree(root / "vokabulare", root / "beispiele")
    (root / "beispiele" / "farben.ttl").write_text(COLOURS.replace("ex:red", "ex:green"), encoding="utf-8")

    assert EX + "green" not in read_vocabulary(root).concepts
