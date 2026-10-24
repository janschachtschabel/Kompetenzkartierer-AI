"""What X1 reads of a document for its profile (plan M1 6.2, konzept §13.2): its opening blocks up to
OPENING_SIGNS, its table of contents, and the passages on when and for whom it holds with their
neighbours up to VALIDITY_SIGNS - each block with its id."""

from typing import Literal

from app.conversion.base import Block
from app.pipeline.toc import Contents
from app.pipeline.x1_excerpt import OPENING_SIGNS, VALIDITY_SIGNS, profile_excerpt

NO_CONTENTS = Contents((), frozenset())
Kind = Literal["text", "page_header"]


def block(block_id: str, words: str, kind: Kind = "text") -> Block:
    return Block(
        id=block_id, page=int(block_id[1 : block_id.index("-")]), kind=kind, text=words,
        bbox=(0, 0, 1, 1), font_size=10, bold=False, italic=False,
    )  # fmt: skip


def paragraphs(count: int, signs: int = 1000, page: int = 1) -> list[Block]:
    return [
        block(f"p{page}-b{number}", f"{number:03d}" + "x" * (signs - 3)) for number in range(1, count + 1)
    ]


def test_the_opening_is_read_up_to_its_signs() -> None:
    blocks = paragraphs(20)

    excerpt = profile_excerpt(blocks, [None], NO_CONTENTS)

    within = OPENING_SIGNS // 1000
    assert f"[p1-b{within}] " in excerpt
    assert f"[p1-b{within + 1}] " not in excerpt


def test_a_first_block_longer_than_the_opening_is_read_all_the_same() -> None:
    excerpt = profile_excerpt([block("p1-b1", "Titel " * 2000), block("p1-b2", "Mehr")], [None], NO_CONTENTS)

    assert excerpt.startswith("— Seite 1 —\n[p1-b1] Titel")
    assert "[p1-b2]" not in excerpt


def test_the_contents_are_read_wherever_they_stand() -> None:
    blocks = [*paragraphs(20), block("p2-b1", "1 Einleitung ..... 3"), *paragraphs(3, page=3)]

    excerpt = profile_excerpt(blocks, [None, "1", None], Contents((), frozenset({20})))

    assert "— Seite 2 (gedruckt 1) —\n[p2-b1] 1 Einleitung ..... 3" in excerpt
    assert "[p3-b1]" not in excerpt


def test_a_passage_on_when_the_document_holds_is_read_with_its_neighbours() -> None:
    blocks = paragraphs(20)
    blocks[15] = block("p1-b16", "Dieser Lehrplan tritt am 1. August 2019 in Kraft.")

    excerpt = profile_excerpt(blocks, [None], NO_CONTENTS)

    for kept in ("p1-b15", "p1-b16", "p1-b17"):
        assert f"[{kept}] " in excerpt
    assert "[p1-b14] " not in excerpt and "[p1-b18] " not in excerpt
    assert "[…]\n[p1-b15] " in excerpt  # what lies between is marked left out


def test_passages_are_read_up_to_their_signs() -> None:
    blocks = paragraphs(40)
    for at in (20, 25, 30, 35):
        blocks[at] = block(f"p1-b{at + 1}", "Gilt für alle Schulformen. " + "y" * 1000)

    excerpt = profile_excerpt(blocks, [None], NO_CONTENTS)

    read = [at for at in (20, 25, 30, 35) if f"[p1-b{at + 1}] " in excerpt]
    assert read == [20]  # its neighbours with it come to some 3000 signs: the next would pass 4000
    assert VALIDITY_SIGNS == 4000


def test_headers_and_footers_are_not_read() -> None:
    blocks = [block("p1-b1", "Kernlehrplan", kind="page_header"), block("p1-b2", "Inkrafttreten: 2019")]

    excerpt = profile_excerpt(blocks, [None], NO_CONTENTS)

    assert "[p1-b1]" not in excerpt and "[p1-b2] Inkrafttreten: 2019" in excerpt


def test_a_passage_s_neighbour_is_the_text_beside_it_not_a_header() -> None:
    blocks = [
        *paragraphs(10),
        block("p1-b11", "Inkrafttreten: 2019"),
        block("p2-b1", "Kernlehrplan", kind="page_header"),
        block("p2-b2", "Nach dem Kopf"),
    ]

    excerpt = profile_excerpt(blocks, [None, None], NO_CONTENTS)

    assert "[p1-b10] " in excerpt and "[p2-b2] Nach dem Kopf" in excerpt
