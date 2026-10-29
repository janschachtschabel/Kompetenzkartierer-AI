"""The IRIs of works, documents and nodes, and the codes the pipeline assigns (konzept §11)."""

from uuid import UUID

import pytest

from app.domain.iris import (
    assign_code,
    checked_base,
    document_iri,
    draft_iri,
    node_iri,
    node_segments,
    slug,
    statement_iri,
    work_iri,
)

BASE = "https://example.org/kk/"


@pytest.mark.parametrize(
    ("text", "made"),
    [
        ("Rahmenlehrplan Mechatronik", "rahmenlehrplan-mechatronik"),
        ("Größe & Maß", "groesse-mass"),
        ("Übergänge", "uebergaenge"),
        ("U\N{COMBINING DIAERESIS}berga\N{COMBINING DIAERESIS}nge", "uebergaenge"),  # decomposed
        ("Café", "cafe"),
        ("  LF 5 ", "lf-5"),
        ("3.2.1", "3-2-1"),
        ("M-ET-04", "m-et-04"),
    ],
)
def test_a_slug_is_its_text_in_lowercase_ascii_words_parted_by_hyphens(text: str, made: str) -> None:
    assert slug(text) == made


@pytest.mark.parametrize("text", ["", " ", "\N{EM DASH}", "§", "\N{GREEK SMALL LETTER ALPHA}", "\N{BULLET}"])
def test_a_text_without_ascii_letters_or_digits_has_no_slug(text: str) -> None:
    with pytest.raises(ValueError, match=r"no slug .* no ASCII letter or digit"):
        slug(text)


def test_a_slug_keeps_a_hundred_signs_at_most_and_ends_on_a_word() -> None:
    made = slug("Kernlehrplan " * 20)

    assert len(made) <= 100
    assert set(made.split("-")) == {"kernlehrplan"}  # whole words alone
    assert not made.endswith("-")


def test_a_work_is_named_by_its_country_and_short_title() -> None:
    made = work_iri(BASE, "DE-NW", "Kernlehrplan Mathematik")

    assert made == "https://example.org/kk/work/de-nw/kernlehrplan-mathematik"


def test_a_document_is_named_by_its_issuer_short_title_and_edition() -> None:
    made = document_iri(BASE, "MSB NRW", "Kernlehrplan Mathematik", "2019")

    assert made == "https://example.org/kk/doc/msb-nrw/kernlehrplan-mathematik/2019"


@pytest.mark.parametrize(
    "base",
    [
        "https://example.org/kk",
        "example.org/kk/",
        "urn:kk:",
        "https://user:secret@example.org/kk/",
        "https://example.org/kk?draft=1/",
        "https://example.org/kk#top/",
    ],
)
def test_a_base_is_an_http_iri_ending_in_a_slash(base: str) -> None:
    with pytest.raises(ValueError, match="base"):
        work_iri(base, "DE-NW", "Kernlehrplan")
    with pytest.raises(ValueError, match="base"):
        checked_base(base)
    assert checked_base("https://example.org/kk/") == "https://example.org/kk/"


def test_a_draft_is_named_by_its_id() -> None:
    made = draft_iri(UUID("01a16940-29e3-7bf4-86d3-421b72698f8e"))

    assert made == "urn:uuid:01a16940-29e3-7bf4-86d3-421b72698f8e"


def test_a_node_is_named_by_the_path_of_its_codes_under_its_document() -> None:
    document = document_iri(BASE, "KMK", "Rahmenlehrplan Mechatronik", "2018")

    assert node_iri(document, ["lf-5", "pos-2"]) == f"{document}/lf-5/pos-2"


def test_a_statement_is_named_by_its_number_under_its_node() -> None:
    node = "https://example.org/kk/doc/kmk/rlp/2018/lf-5"

    assert statement_iri(node, 3) == f"{node}/s-3"
    with pytest.raises(ValueError, match="number"):
        statement_iri(node, 0)
    with pytest.raises(ValueError, match="frozen"):
        statement_iri(draft_iri(UUID("01a16940-29e3-7bf4-86d3-421b72698f8e")), 1)


def test_a_node_needs_a_segment() -> None:
    with pytest.raises(ValueError, match="segment"):
        node_iri("https://example.org/kk/doc/kmk/rlp/2018", [])


def test_a_node_is_named_under_a_frozen_document_alone() -> None:
    # a draft's urn:uuid takes no path: its nodes are named once it is frozen (plan M1 9.6)
    with pytest.raises(ValueError, match="document"):
        node_iri(draft_iri(UUID("01a16940-29e3-7bf4-86d3-421b72698f8e")), ["lf-5"])


def test_siblings_take_their_codes_an_assigned_one_its_position_and_a_repeated_one_a_count() -> None:
    siblings = [("LF 5", False), ("3", True), ("LF 5", False), ("LF 5", False)]

    assert node_segments(siblings) == ["lf-5", "pos-3", "lf-5-2", "lf-5-3"]


def test_a_code_without_an_ascii_letter_or_digit_gives_way_to_its_place() -> None:
    siblings = [("\N{GREEK SMALL LETTER ALPHA}", False), ("LF 1", False), ("\N{BULLET}", False)]

    assert node_segments(siblings) == ["pos-1", "lf-1", "pos-3"]


def test_a_count_steps_past_a_code_a_sibling_holds_already() -> None:
    siblings = [("LF 5", False), ("LF 5-2", False), ("LF 5", False)]

    assert node_segments(siblings) == ["lf-5", "lf-5-2", "lf-5-3"]


def test_a_segment_a_statement_s_iri_would_have_counts_on() -> None:
    # <node>/s-<n> names the node's statements (app/domain/naming.py): a child coded "S 1" is no statement
    siblings = [("S 1", False), ("S-1", False), ("S 12a", False), ("S 12", False)]

    assert node_segments(siblings) == ["s-1-2", "s-1-3", "s-12a", "s-12-2"]


def test_siblings_coded_s_count_on_past_every_segment_a_statement_s_iri_would_have() -> None:
    # "s-2", "s-3", ... are all statements': under "s" the count goes on from "s-1"
    siblings = [("S", False), ("S", False), ("(s)", False)]

    assert node_segments(siblings) == ["s", "s-1-2", "s-1-3"]


def test_an_assigned_code_is_the_position_among_its_siblings() -> None:
    assert assign_code(3) == "3"


@pytest.mark.parametrize("position", [0, -1])
def test_a_position_counts_from_one(position: int) -> None:
    with pytest.raises(ValueError, match="position"):
        assign_code(position)
