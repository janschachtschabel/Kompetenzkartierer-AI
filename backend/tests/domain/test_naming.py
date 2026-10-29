"""The IRIs a document's nodes and statements get when it is frozen (plan M1 9.6, Paket 9b H6): nodes from
the top by the path of their codes, siblings in their order; statements numbered under their node, each
number given once. What a draft copy brought along keeps its IRI, what is new steps past it; a rejected
statement gets none."""

from uuid import uuid4

from app.domain.naming import NodeRow, StatementRow, name_rows

DOC = "https://example.org/kk/doc/de/kmk/rlp/2018"


def node(code: str | None, position: int, parent: NodeRow | None = None, **changes: object) -> NodeRow:
    values: dict[str, object] = {
        "id": uuid4(), "parent_id": None if parent is None else parent.id, "position": position,
        "code": code, "code_assigned": False, "iri": None, "statement_serial": 0,
    } | changes  # fmt: skip
    return NodeRow(**values)  # type: ignore[arg-type]


def statement(at: NodeRow, position: int, **changes: object) -> StatementRow:
    values: dict[str, object] = {
        "id": uuid4(),
        "node_id": at.id,
        "position": position,
        "iri": None,
        "rejected": False,
    } | changes
    return StatementRow(**values)  # type: ignore[arg-type]


def test_a_document_frozen_first_names_its_nodes_by_their_codes_and_numbers_its_statements() -> None:
    first = node("LF 1", 1)
    second = node("2", 2, code_assigned=True)
    under = node(None, 1, first)  # an editor's, without a code: its place names it
    beside = node(None, 2, first)
    said = [statement(first, 1), statement(first, 2, rejected=True), statement(first, 3)]

    # in any order: the positions decide
    named = name_rows(DOC, [second, beside, under, first], list(reversed(said)))

    assert named.nodes == {
        first.id: f"{DOC}/lf-1",
        second.id: f"{DOC}/pos-2",
        under.id: f"{DOC}/lf-1/pos-1",
        beside.id: f"{DOC}/lf-1/pos-2",
    }
    # a rejected statement is none of the curriculum's: it takes no number
    assert named.statements == {said[0].id: f"{DOC}/lf-1/s-1", said[2].id: f"{DOC}/lf-1/s-2"}
    assert named.serials == {first.id: 2}


def test_a_copy_keeps_what_it_brought_and_names_what_is_new_past_it() -> None:
    # copied: lf-1 with s-1 and s-3 (s-2 was an editor's, taken away in the copy); new: a second "LF 1"
    first = node("LF 1", 1, iri=f"{DOC}/lf-1", statement_serial=3)
    renamed = node("LF 7", 2, iri=f"{DOC}/lf-2")  # its code changed in the copy: its IRI stays
    added = node("LF 1", 3)
    kept = [statement(first, 1, iri=f"{DOC}/lf-1/s-1"), statement(first, 3, iri=f"{DOC}/lf-1/s-3")]
    new = statement(first, 4)
    taken_back = statement(first, 2, iri=f"{DOC}/lf-1/s-2", rejected=True)  # rejected since: it keeps it

    named = name_rows(DOC, [first, renamed, added], [*kept, new, taken_back])

    assert named.nodes == {added.id: f"{DOC}/lf-1-2"}
    assert named.statements == {new.id: f"{DOC}/lf-1/s-4"}
    assert named.serials == {first.id: 4}


def test_a_new_node_steps_past_a_segment_a_copied_sibling_holds_by_another_code() -> None:
    copied = node("LF 9", 1, iri=f"{DOC}/lf-3")  # once "LF 3", recoded in the copy
    added = node("LF 3", 2)

    named = name_rows(DOC, [copied, added], [])

    assert named.nodes == {added.id: f"{DOC}/lf-3-2"}


def test_a_new_node_steps_past_a_copied_sibling_s_segment_to_none_a_statement_holds() -> None:
    # counted on from "s", "s-2" would be the IRI of the parent's second statement
    copied = node("LF 1", 1, iri=f"{DOC}/s")  # once "S", recoded in the copy
    added = node("S", 2)

    named = name_rows(DOC, [copied, added], [])

    assert named.nodes == {added.id: f"{DOC}/s-1-2"}


def test_a_segment_counted_on_is_none_a_later_new_sibling_takes() -> None:
    copied = node("LF 9", 1, iri=f"{DOC}/lf-1")  # once "LF 1"
    counted = node("LF 1", 2)  # past the copied one's segment: lf-1-2
    printed = node("LF 1-2", 3)  # printed so: past the one counted on

    named = name_rows(DOC, [copied, counted, printed], [])

    assert named.nodes == {counted.id: f"{DOC}/lf-1-2", printed.id: f"{DOC}/lf-1-2-2"}


def test_nothing_new_is_nothing_named() -> None:
    first = node("LF 1", 1, iri=f"{DOC}/lf-1", statement_serial=1)

    named = name_rows(DOC, [first], [statement(first, 1, iri=f"{DOC}/lf-1/s-1")])

    assert (named.nodes, named.statements, named.serials) == ({}, {}, {})


def test_a_node_named_again_numbers_its_statements_past_all_an_earlier_revision_gave() -> None:
    # dropped in a draft copy and made anew at its code's path: its IRI comes back, no number does
    again = node("LF 1", 1)

    named = name_rows(DOC, [again], [statement(again, 1)], served={f"{DOC}/lf-1": 5})

    assert named.nodes == {again.id: f"{DOC}/lf-1"}
    assert list(named.statements.values()) == [f"{DOC}/lf-1/s-6"]
    assert named.serials == {again.id: 6}
