"""The skeleton of a document without the model (plan M1 6.3): its table of contents, its headings
from type, layout, numbering and the contents, their levels and parents, their codes, and the node
type a strong pattern of the lexicon gives a heading."""

import functools
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pytest

from app.conversion.base import Block, Cell
from app.domain.lexicon import HOMONYM, NEGATIVE, ActiveCue, Cue, active_cues
from app.pipeline.skeleton import Heading, Skeleton, build_skeleton
from app.pipeline.toc import TocEntry, leading_number
from app.vocab.lexicon import LexicalCue
from app.vocab.loader import read_vocabulary

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
PROFILE = "https://w3id.org/wlo/curriculum/profile/"
REGION = "https://w3id.org/wlo/curriculum/region/"
NODE_TYPE = "https://w3id.org/wlo/curriculum/core#NodeType"
CV = "https://w3id.org/wlo/curriculum/vocab#"
HEADING_PATTERN = CV + "ck_headingPattern"
CODE_PATTERN = CV + "ck_codePattern"
IN_CONTENTS = CV + "occ_toc"
BODY = "Die Schülerinnen und Schüler beschreiben, wie Licht sich ausbreitet, und erklären Schatten."

Kind = Literal["text", "table", "page_header", "page_footer"]


def block(
    block_id: str, words: str, *, size: float | None = 10, bold: bool = False, kind: Kind = "text"
) -> Block:
    return Block(
        id=block_id, page=int(block_id[1 : block_id.index("-")]), kind=kind, text=words, bbox=(0, 0, 1, 1),
        font_size=size, bold=bold, italic=False,
    )  # fmt: skip


def table(block_id: str, number: int, rows: list[list[str]]) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    cells = tuple(
        Cell(id=f"T{number}:r{r}c{c}", page=page, row=r, column=c, text=value, header=r == 1)
        for r, row in enumerate(rows, start=1)
        for c, value in enumerate(row, start=1)
    )
    joined = "\n".join(" ".join(row) for row in rows)
    return Block(
        id=block_id, page=page, kind="table", text=joined, bbox=(0, 0, 1, 1), font_size=None, bold=False,
        italic=False, cells=cells,
    )  # fmt: skip


def skeleton(
    blocks: Sequence[Block], cues: Sequence[ActiveCue] = (), node_types: frozenset[str] = frozenset()
) -> Skeleton:
    return build_skeleton(blocks, cues, node_types)


def titles(found: Skeleton) -> list[str]:
    return [heading.title for heading in found.headings]


def shape(found: Skeleton) -> list[tuple[str, int, str | None]]:
    return [(heading.title, heading.level, heading.parent) for heading in found.headings]


COVER = block("p1-b1", "Kernlehrplan Physik für die Sekundarstufe I", size=24)


def test_a_heading_is_a_short_line_set_larger_than_the_body_its_level_the_rank_of_its_size() -> None:
    found = skeleton([
        COVER,
        block("p1-b2", "Ministerium für Schule und Bildung", size=12),
        block("p2-b1", "Einleitung", size=16),
        block("p2-b2", BODY),
        block("p2-b3", "Aufgaben des Faches", size=13),
        block("p2-b4", BODY),
        block("p3-b1", "Kompetenzen", size=16),
        block("p3-b2", BODY),
    ])  # fmt: skip

    assert shape(found) == [
        ("Einleitung", 1, None),
        ("Aufgaben des Faches", 2, "H1"),
        ("Kompetenzen", 1, None),
    ]
    assert [heading.key for heading in found.headings] == ["H1", "H2", "H3"]
    first = found.headings[0]
    assert (first.position, first.block_id, first.page) == (2, "p2-b1", 2)


def test_the_title_page_is_no_heading() -> None:
    # set larger than any heading, on the first page alone: the document's title, not a section
    found = skeleton(
        [
            COVER,
            block("p1-b2", "Stand: 2019", size=14),
            block("p2-b1", "Einleitung", size=16),
            block("p2-b2", BODY),
        ]
    )

    assert titles(found) == ["Einleitung"]


def test_the_numbering_gives_the_level_and_the_code() -> None:
    found = skeleton([
        COVER,
        block("p2-b1", "1 Einleitung", bold=True),
        block("p2-b2", BODY),
        block("p2-b3", "1.1 Ziele des Faches", bold=True),
        block("p2-b4", BODY),
        block("p2-b5", "1.2 Aufbau", bold=True),
        block("p2-b6", BODY),
        block("p3-b1", "2 Kompetenzen", bold=True),
        block("p3-b2", BODY),
    ])  # fmt: skip

    assert shape(found) == [
        ("1 Einleitung", 1, None),
        ("1.1 Ziele des Faches", 2, "H1"),
        ("1.2 Aufbau", 2, "H1"),
        ("2 Kompetenzen", 1, None),
    ]
    assert [(heading.code, heading.code_assigned) for heading in found.headings] == [
        ("1", False), ("1.1", False), ("1.2", False), ("2", False),
    ]  # fmt: skip


def test_a_level_is_the_depth_in_the_tree_however_deep_the_numbering_begins() -> None:
    found = skeleton(
        [
            COVER,
            block("p2-b1", "2.1 Optik", bold=True),
            block("p2-b2", BODY),
            block("p2-b3", "2.1.1 Linsen", bold=True),
        ]
    )

    assert shape(found) == [("2.1 Optik", 1, None), ("2.1.1 Linsen", 2, "H1")]


def test_a_bold_line_is_a_heading_below_the_larger_ones_unless_bold_text_follows_it() -> None:
    found = skeleton([
        COVER,
        block("p2-b1", "Einleitung", size=16),
        block("p2-b2", "Ziele", bold=True),
        block("p2-b3", BODY),
        block("p2-b4", "Hinweis", bold=True),  # a bold paragraph follows: a lead-in, not a heading
        block("p2-b5", "Die Vorgaben gelten für alle Schulen.", bold=True),
        block("p2-b6", BODY),
        block("p2-b7", "Die Vorgaben dieses Kapitels gelten für alle Schulformen und alle Jahrgänge"
                       " ohne Ausnahme", bold=True),
        block("p2-b8", BODY),  # bold of more than 80 signs: a sentence set bold, not a heading
    ])  # fmt: skip

    assert shape(found) == [("Einleitung", 1, None), ("Ziele", 2, "H1")]


def test_a_sentence_a_long_block_and_a_list_are_no_headings_however_large() -> None:
    rejected = [
        "Die Kompetenzen bauen aufeinander auf.",
        "Kompetenzen " * 17,  # more than 200 signs
        "Erste Zeile\nzweite Zeile\ndritte Zeile\nvierte Zeile",
        "1. Licht\n2. Schatten\n3. Farben",
    ]
    blocks = [COVER, block("p2-b1", "Einleitung", size=16), block("p2-b2", BODY)]
    for number, words in enumerate(rejected, start=1):
        blocks += [block(f"p3-b{2 * number - 1}", words, size=16), block(f"p3-b{2 * number}", BODY)]

    found = skeleton(blocks)

    assert found.body_size == 10
    assert titles(found) == ["Einleitung"]


def test_a_line_a_little_larger_or_numbered_in_the_body_s_type_is_no_heading() -> None:
    found = skeleton([
        COVER,
        block("p2-b1", "Einleitung", size=16),
        block("p2-b2", "Etwas größer gesetzt", size=11),
        block("p2-b3", "1 Stunde je Woche"),
        block("p2-b4", BODY),
    ])  # fmt: skip

    assert titles(found) == ["Einleitung"]


@pytest.mark.parametrize(
    ("title", "number"),
    [
        ("1.2 Ziele", "1.2"),
        ("1.2. Ziele", "1.2"),
        ("IV. Anhang", "IV"),
        ("A. Grundlagen", "A"),
        ("2024 Fassung", None),  # a year leads no numbering
        ("Lernfeld 5", None),
        ("1.", None),
    ],
)
def test_a_numbering_leads_a_title_of_two_digits_a_part(title: str, number: str | None) -> None:
    assert leading_number(title) == number


def test_a_heading_s_title_is_its_wording_with_its_lines_joined() -> None:
    found = skeleton(
        [COVER, block("p2-b1", "Ziele und Aufgaben\ndes Faches Physik", size=16), block("p2-b2", BODY)]
    )

    assert titles(found) == ["Ziele und Aufgaben des Faches Physik"]


def test_headers_and_footers_are_no_headings() -> None:
    found = skeleton([
        COVER,
        block("p2-b1", "Kernlehrplan Physik", size=14, kind="page_header"),
        block("p2-b2", "Einleitung", size=16),
        block("p2-b3", BODY),
        block("p2-b4", "Seite 2", size=14, bold=True, kind="page_footer"),
    ])  # fmt: skip

    assert titles(found) == ["Einleitung"]


def test_the_body_size_is_that_of_most_of_the_text() -> None:
    found = skeleton(
        [COVER, block("p2-b1", "Anmerkung", size=8), block("p2-b2", BODY), block("p2-b3", BODY, size=9)]
    )

    assert found.body_size == 10


CONTENTS = (
    "1 Einleitung ..... 3\n"
    "2 Kompetenzen ..... 4\n"
    "2.1 Wahrnehmung und Messung . . . . 5\n"
    "3 GRUNDSÄTZE ....... 9\n"  # set in capitals, named in the body's case
    "Anhang ..... 12"
)


def contents_document() -> list[Block]:
    return [
        COVER,
        block("p2-b1", "Inhalt", size=16),
        block("p2-b2", CONTENTS),
        block("p3-b1", "1 Einleitung", size=16),
        block("p3-b2", BODY),
        block("p4-b1", "2 Kompetenzen", size=16),
        block("p4-b2", BODY),
        block("p5-b1", "2.1 Wahrnehmung und Messung", size=13),
        block("p5-b2", BODY),
        block("p9-b1", "Grundsätze"),  # in the body's type: a heading because the contents name it
        block("p9-b2", BODY),
    ]


def test_the_table_of_contents_is_read_with_its_pages_and_levels() -> None:
    found = skeleton(contents_document())

    assert found.contents.entries == (
        TocEntry("1 Einleitung", "3", 1, 2),
        TocEntry("2 Kompetenzen", "4", 1, 2),
        TocEntry("2.1 Wahrnehmung und Messung", "5", 2, 2),
        TocEntry("3 GRUNDSÄTZE", "9", 1, 2),
        TocEntry("Anhang", "12", None, 2),  # no numbering, no level
    )
    assert found.contents.positions == frozenset({1, 2})  # its title with it


def test_the_table_of_contents_is_never_a_heading_nor_what_stands_before_it() -> None:
    found = skeleton(contents_document())

    assert shape(found) == [
        ("1 Einleitung", 1, None),
        ("2 Kompetenzen", 1, None),
        ("2.1 Wahrnehmung und Messung", 2, "H2"),
        ("Grundsätze", 1, None),  # the contents give its level: 3 is of the top
    ]


def test_what_stands_before_the_contents_is_no_heading() -> None:
    # a foreword before the contents: the title pages, read as the document's front matter
    blocks = [COVER, block("p2-b1", "Vorwort", size=16), block("p2-b2", BODY), *contents_document()[1:]]

    assert titles(skeleton(blocks))[0] == "1 Einleitung"


def test_a_table_is_never_contents() -> None:
    # the learning fields' overview of a Rahmenlehrplan: numbered rows ending in hours
    overview = table("p3-b1", 1, [["1", "Den Betrieb erkunden", "80"], ["2", "Kunden beraten", "60"],
                                  ["3", "Waren annehmen", "40"]])  # fmt: skip
    blocks = [COVER, block("p2-b1", "Teil I Vorbemerkungen", size=16), block("p2-b2", BODY), overview]

    found = skeleton(blocks)

    assert found.contents.entries == ()
    assert titles(found) == ["Teil I Vorbemerkungen"]


def test_contents_of_one_line_a_block_are_contents_from_three_lines_on() -> None:
    entries = [
        block("p2-b1", "1 Einleitung 3"),
        block("p2-b2", "2 Bildungsbereiche 5"),
        block("p2-b3", "2.1 Sprache 6"),
    ]

    three = skeleton([COVER, *entries, block("p3-b1", "1 Einleitung", size=16)])
    two = skeleton([COVER, *entries[:2], block("p3-b1", "1 Einleitung", size=16)])

    assert [entry.title for entry in three.contents.entries] == [
        "1 Einleitung",
        "2 Bildungsbereiche",
        "2.1 Sprache",
    ]
    assert three.contents.positions == frozenset({1, 2, 3})
    assert two.contents.entries == ()
    # text between them parts them: two and one are no contents
    parted = [*entries[:2], block("p2-b4", BODY), block("p2-b5", "3 Sprache 6")]
    assert skeleton([COVER, *parted, block("p3-b1", "1 Einleitung", size=16)]).contents.entries == ()


def test_a_heading_without_a_printed_code_gets_its_place_among_its_siblings() -> None:
    found = skeleton([
        COVER,
        block("p2-b1", "Vorwort", size=16),
        block("p2-b2", BODY),
        block("p2-b3", "Einleitung", size=16),
        block("p2-b4", "Ziele", size=13),
        block("p2-b5", BODY),
        block("p2-b6", "Aufbau", size=13),
        block("p2-b7", BODY),
    ])  # fmt: skip

    assert [(heading.code, heading.code_assigned) for heading in found.headings] == [
        ("1", True), ("2", True), ("1", True), ("2", True),
    ]  # fmt: skip


# --- the lexicon's patterns: a heading of its own, and a node type where one is strong (≥ 0.9)


def as_cue(found: LexicalCue) -> Cue:
    return Cue(
        iri=found.iri,
        role=found.role,
        kind=found.kind,
        maps_to=tuple(found.maps_to),
        surface_form=found.surface_form,
        pattern=found.pattern,
        layout_signal=found.layout_signal,
        also_maps_to=tuple(found.also_maps_to),
        scope_regions=frozenset(found.scope_regions),
        scope_document_types=frozenset(found.scope_document_types),
        plan_generations=frozenset(found.plan_generations),
        strength=None if found.strength is None else float(found.strength),
        positive_examples=tuple(found.positive_examples),
        negative_examples=tuple(found.negative_examples),
    )


@functools.cache
def sector(name: str) -> tuple[tuple[Cue, ...], frozenset[str]]:
    """The cues of a sector's profile and its node types, as the ontology holds them."""
    vocabulary = read_vocabulary(ONTOLOGY)
    profile = f"{PROFILE}{name}#Terminology"
    namespace = vocabulary.profiles[profile].namespace
    cues = tuple(as_cue(found) for found in vocabulary.cues.values() if found.profile == profile)
    node_types = frozenset(
        iri
        for iri, concept in vocabulary.concepts.items()
        if NODE_TYPE in concept.types and iri.startswith(namespace)
    )
    return cues, node_types


def in_sector(
    name: str, *regions: str, document_type: str | None = None
) -> tuple[list[ActiveCue], frozenset[str]]:
    cues, node_types = sector(name)
    return active_cues(
        cues, frozenset(REGION + region for region in regions), document_type, None
    ), node_types


def headed(*headings: str) -> list[Block]:
    """A cover page, then each heading bold above a paragraph."""
    blocks = [COVER]
    for number, heading in enumerate(headings):
        blocks += [block(f"p2-b{2 * number + 1}", heading, bold=True), block(f"p2-b{2 * number + 2}", BODY)]
    return blocks


def typed(found: Skeleton) -> list[tuple[str, str | None, str | None]]:
    def short(iri: str | None) -> str | None:
        return None if iri is None else iri.removeprefix(PROFILE)

    return [(heading.title, short(heading.node_type), short(heading.rule_id)) for heading in found.headings]


def test_a_learning_field_is_typed_by_its_pattern_and_coded_by_its_number() -> None:
    cues, node_types = in_sector("vocational")

    found = skeleton(headed("Lernfeld 5: Kunden akquirieren", "Lernfeld 13GH: Projekt"), cues, node_types)

    assert typed(found) == [
        ("Lernfeld 5: Kunden akquirieren", "vocational#Lernfeld", "vocational#c-lf-1"),
        ("Lernfeld 13GH: Projekt", "vocational#Lernfeld", "vocational#c-lf-1"),
    ]
    assert [(heading.code, heading.code_assigned) for heading in found.headings] == [
        ("5", False),
        ("13GH", False),
    ]


def test_a_content_field_is_typed_where_its_pattern_holds_and_only_with_its_colon() -> None:
    # the pattern asks for a colon or a full stop behind the number (school#cue-ib-inhaltsfeld)
    in_nw, school = in_sector("school", "DE-NW")
    in_by, _ = in_sector("school", "DE-BY")

    assert typed(skeleton(headed("Inhaltsfeld 3: Optik", "Inhaltsfeld 4 Elektrik"), in_nw, school)) == [
        ("Inhaltsfeld 3: Optik", "school#Inhaltsbereich", "school#cue-ib-inhaltsfeld"),
        ("Inhaltsfeld 4 Elektrik", None, None),
    ]
    assert typed(skeleton(headed("Inhaltsfeld 3: Optik"), in_by, school)) == [
        ("Inhaltsfeld 3: Optik", None, None)
    ]


def test_a_weaker_pattern_makes_a_heading_and_leaves_its_type_to_the_model() -> None:
    cues, node_types = in_sector("vocational")  # c-hf-1 is of 0.8

    found = skeleton(
        [COVER, block("p2-b1", "Handlungsfeld 1: Bildung und Erziehung"), block("p2-b2", BODY)],
        cues,
        node_types,
    )

    assert typed(found) == [("Handlungsfeld 1: Bildung und Erziehung", None, None)]
    assert found.headings[0].code == "1"


def test_a_pattern_of_a_statement_kind_makes_no_heading() -> None:
    # c-fkf-1 names a statement subkind (FKF), no node type: its lines stay text
    cues, node_types = in_sector("vocational", document_type=PROFILE + "vocational#dt-Ausbildungsordnung")

    found = skeleton(
        [
            COVER,
            block("p2-b1", "Einleitung", size=16),
            block("p2-b2", "a) Aufbau und Organisation erläutern"),
            block("p2-b3", BODY),
        ],
        cues,
        node_types,
    )

    assert titles(found) == ["Einleitung"]


def test_a_table_opened_by_a_heading_pattern_is_a_heading_any_other_table_is_none() -> None:
    cues, node_types = in_sector("vocational")
    learning_field = table("p2-b3", 1, [["Lernfeld 5: Kunden akquirieren", "2. Ausbildungsjahr"], [BODY, ""]])
    other = table("p3-b1", 2, [["Kompetenzen", "Inhalte"], ["Kunden beraten", "Angebote"]])

    found = skeleton(
        [COVER, block("p2-b1", "Teil V Lernfelder", size=16), block("p2-b2", BODY), learning_field, other],
        cues,
        node_types,
    )

    assert typed(found) == [
        ("Teil V Lernfelder", None, None),
        ("Lernfeld 5: Kunden akquirieren", "vocational#Lernfeld", "vocational#c-lf-1"),
    ]
    assert found.headings[1].block_id == "p2-b3"
    # the number behind a heading's first word is its code only where a pattern found it
    assert (found.headings[0].code, found.headings[0].code_assigned) == ("1", True)


def strong_cues(name: str) -> list[tuple[Cue, str]]:
    """The cues of a sector that may type a heading alone, each with the node type it names."""
    cues, node_types = sector(name)
    return [
        (found, targets[0])
        for found in cues
        if found.kind in (HEADING_PATTERN, CODE_PATTERN)
        and found.pattern is not None
        and (found.strength or 0) >= 0.9
        and len(targets := [target for target in found.maps_to if target in node_types]) == 1
    ]


def test_the_lexicon_s_negative_examples_are_never_typed_by_their_cue_and_its_positive_ones_are() -> None:
    wrong: list[tuple[str, str]] = []
    checked = 0
    for name in ("school", "vocational", "higher-education", "adult-education", "early-childhood"):
        for found, target in strong_cues(name):
            regions = {region.removeprefix(REGION) for region in found.scope_regions}
            document_type = min(found.scope_document_types, default=None)
            cues, node_types = in_sector(name, *regions, document_type=document_type)
            for example in found.negative_examples:
                checked += 1
                if any(
                    heading.rule_id == found.iri
                    for heading in skeleton(headed(example), cues, node_types).headings
                ):
                    wrong.append((found.iri, example))
            for example in found.positive_examples:
                checked += 1
                if [
                    heading.node_type for heading in skeleton(headed(example), cues, node_types).headings
                ] != [target]:
                    wrong.append((found.iri, example))

    assert checked > 10
    assert wrong == []


def own_cue(
    name: str, pattern: str, target: str, *, strength: float = 0.95, role: str = CV + "role_cue"
) -> Cue:
    return Cue(
        iri=name, role=role, kind=HEADING_PATTERN, maps_to=(target,), pattern=pattern, strength=strength
    )


def test_a_homonym_a_tie_or_two_types_type_no_heading_two_cues_for_one_type_do() -> None:
    types = frozenset({"T", "U"})
    homonym = own_cue("homonym", r"^Bereich\s+\d", "T", role=HOMONYM)
    tie = [own_cue("tie-a", r"^Feld\s+\d", "T"), own_cue("tie-b", r"^Feld\s+\d", "U")]
    apart = [own_cue("apart-a", r"^Stufe", "T"), own_cue("apart-b", r"^Stufe\s+\d", "U")]
    agree = [own_cue("agree-a", r"^Kurs\s+\d", "T"), own_cue("agree-b", r"^Kurs\s+\d+:", "T")]

    found = skeleton(
        headed("Bereich 1: Sprache", "Feld 2: Natur", "Stufe 4: Lesen", "Kurs 3: Kunst"),
        active_cues([homonym, *tie, *apart, *agree], frozenset(), None, None),
        types,
    )

    assert typed(found) == [
        ("Bereich 1: Sprache", None, None),
        ("Feld 2: Natur", None, None),
        ("Stufe 4: Lesen", None, None),
        ("Kurs 3: Kunst", "T", "agree-a"),
    ]


def test_a_negative_cue_makes_no_heading() -> None:
    negative = own_cue("negative", r"^Bereich\s", "T", role=NEGATIVE)

    found = skeleton(
        [
            COVER,
            block("p2-b1", "Einleitung", size=16),
            block("p2-b2", "Bereich Sprache"),
            block("p2-b3", BODY),
        ],
        active_cues([negative], frozenset(), None, None),
        frozenset({"T"}),
    )

    assert titles(found) == ["Einleitung"]


def test_a_contents_pattern_of_the_lexicon_reads_contents_the_others_miss() -> None:
    chapters = Cue(iri="chapters", role=CV + "role_cue", kind=HEADING_PATTERN, maps_to=(IN_CONTENTS,),
                   pattern=r"^Kapitel\s+\d+\s", strength=0.9)  # fmt: skip
    # the last a line the pattern finds without a page behind it
    lines = ["Kapitel 1 Ziele 3", "Kapitel 2 Inhalte 5", "Kapitel 3 Methoden 8", "Kapitel 4 Anhang"]
    blocks = [COVER, *(block(f"p2-b{number}", line) for number, line in enumerate(lines, start=1))]

    found = skeleton(blocks, active_cues([chapters], frozenset(), None, None))

    assert [(entry.title, entry.page, entry.level) for entry in found.contents.entries] == [
        ("Kapitel 1 Ziele", "3", None),
        ("Kapitel 2 Inhalte", "5", None),
        ("Kapitel 3 Methoden", "8", None),
    ]


def test_a_block_most_of_whose_lines_are_no_entries_is_no_contents() -> None:
    entries = [block("p2-b1", "1 Einleitung 3"), block("p2-b2", "2 Ziele 5")]
    note = block("p2-b3", "Die Hinweise\nstehen im Anhang\n3 Seiten 9")

    found = skeleton([COVER, *entries, note, block("p3-b1", "1 Einleitung", size=16)])

    assert found.contents.entries == ()


def test_a_pattern_that_takes_too_long_types_nothing_and_is_named() -> None:
    # 0.2 s on 190 signs, four times the limit
    slow = own_cue("slow", r"(x+x+x+x+)+y", "T")

    paragraphs = [block(f"p2-b{number}", BODY) for number in range(2, 5)]
    found = skeleton(
        [COVER, block("p2-b1", "x" * 190, size=16), *paragraphs],
        active_cues([slow], frozenset(), None, None),
        frozenset({"T"}),
    )

    assert typed(found) == [("x" * 190, None, None)]
    assert found.timeouts == frozenset({"slow"})


def test_a_heading_is_a_plain_value() -> None:
    # the stage writes it as the run's result and builds nodes from it
    heading = skeleton(headed("Einleitung")).headings[0]

    assert heading == Heading(
        key="H1", position=1, block_id="p2-b1", page=2, level=1, parent=None, title="Einleitung", code="1",
        code_assigned=True, node_type=None, rule_id=None,
    )  # fmt: skip
