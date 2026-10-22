"""Reading the vocabularies from the ontology's Turtle files, without a database."""

import re
import shutil
from pathlib import Path

import pytest
from rdflib import Graph, Literal

from app.vocab import loader
from app.vocab.loader import MODEL_DIRS, VocabularyError, read_vocabulary
from tests.vocab.model import PREFIXES, write_model

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
    return write_model(root, content)


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


@pytest.mark.parametrize("folder", MODEL_DIRS)
def test_a_missing_model_folder_is_refused(tmp_path: Path, folder: str) -> None:
    # a wrong ONTOLOGY_DIR read as a small vocabulary would retire everything else
    root = vocabulary_dir(tmp_path)
    shutil.rmtree(root / folder)

    with pytest.raises(VocabularyError, match=folder):
        read_vocabulary(root)


def test_a_model_folder_without_turtle_files_is_refused(tmp_path: Path) -> None:
    root = vocabulary_dir(tmp_path)
    (root / "ontologie" / "empty.ttl").unlink()

    with pytest.raises(VocabularyError, match="ontologie"):
        read_vocabulary(root)


def test_a_missing_ontology_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(VocabularyError, match="nowhere"):
        read_vocabulary(tmp_path / "nowhere")


def test_files_without_any_scheme_are_refused(tmp_path: Path) -> None:
    with pytest.raises(VocabularyError, match="no scheme"):
        read_vocabulary(vocabulary_dir(tmp_path, PREFIXES))


def test_a_relative_ontology_folder_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vocabulary_dir(tmp_path / "model")
    monkeypatch.chdir(tmp_path)

    assert EX + "red" in read_vocabulary(Path("model")).concepts


def test_a_relative_iri_is_refused(tmp_path: Path) -> None:
    # it would resolve against the file's place on this machine
    with pytest.raises(VocabularyError, match="relative IRI"):
        read_vocabulary(vocabulary_dir(tmp_path, COLOURS + "<local-colour> skos:inScheme ex:colours ."))


def test_a_file_that_does_not_parse_is_named(tmp_path: Path) -> None:
    with pytest.raises(VocabularyError, match=re.escape("farben.ttl")):
        read_vocabulary(vocabulary_dir(tmp_path, COLOURS + "ex:blue a skos:Concept ;"))


@pytest.mark.parametrize(
    ("addition", "fault"),
    [
        ("ex:red skos:altLabel ex:colours .", "altLabel"),
        ("ex:red skos:definition ex:colours .", "definition"),
        ("ex:dark-red skos:broader 'Rot'@de .", "broader"),
        ("ex:red skos:inScheme <https://example.org/elsewhere/scheme> .", "elsewhere"),
        (
            "ex:blue a skos:Concept ; skos:inScheme ex:colours ; skos:notation 'R' .",
            "notation R twice",
        ),
        ("ex:red skos:prefLabel 'Rotton'@DE .", "prefLabel"),
    ],
    ids=[
        "iri-label",
        "iri-definition",
        "literal-broader",
        "foreign-scheme",
        "notation-twice",
        "language-case",
    ],
)
def test_a_value_the_columns_cannot_hold_is_refused_not_dropped(
    tmp_path: Path, addition: str, fault: str
) -> None:
    with pytest.raises(VocabularyError, match=fault):
        read_vocabulary(vocabulary_dir(tmp_path, COLOURS + addition))


def test_a_typed_notation_is_refused(tmp_path: Path) -> None:
    typed = COLOURS.replace('skos:notation "R"', 'skos:notation "R"^^ex:code')

    with pytest.raises(VocabularyError, match="notation"):
        read_vocabulary(vocabulary_dir(tmp_path, typed))


def test_a_new_reader_format_changes_the_content_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = vocabulary_dir(tmp_path)
    before = read_vocabulary(root).content_hash
    monkeypatch.setattr(loader, "READER_FORMAT", loader.READER_FORMAT + 1)

    assert read_vocabulary(root).content_hash != before
