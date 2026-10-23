"""The hash of a statement's wording: one value for one wording however it was set (konzept §11)."""

import hashlib

import pytest

from app.domain.wording import normalized, text_hash


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("Die Lernenden planen ihre Arbeit.", "die  Lernenden\nplanen ihre ARBEIT. "),  # space, line, case
        ("1. Die Lernenden planen", "Die Lernenden planen"),
        ("1.2.3 Die Lernenden planen", "Die Lernenden planen"),
        ("(a) Die Lernenden planen", "Die Lernenden planen"),
        ("b) Die Lernenden planen", "Die Lernenden planen"),
        ("IV. Die Lernenden planen", "Die Lernenden planen"),
        ("\N{BULLET} Die Lernenden planen", "Die Lernenden planen"),
        ("\N{EN DASH} Die Lernenden planen", "Die Lernenden planen"),
        ("Kompe-\ntenzen erwerben", "Kompetenzen erwerben"),  # a word parted at the line's end
        ("Kompe\N{SOFT HYPHEN}tenzen erwerben", "Kompetenzen erwerben"),
        ("Schu\N{COMBINING DIAERESIS}ler", "Schüler"),  # NFC
        ("Lern\N{EN DASH}Feld", "Lern-Feld"),
        ("STRASSE", "straße"),  # casefold, not lower
    ],
)
def test_wordings_set_otherwise_have_one_hash(one: str, other: str) -> None:
    assert text_hash(one) == text_hash(other)


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("Die Lernenden planen", "Die Lernenden prüfen"),
        ("E-Mail schreiben", "EMail schreiben"),  # a hyphen within a line stays
        ("3 Aufgaben lösen", "Aufgaben lösen"),  # a number alone is no numbering
        ("z.B. Texte lesen", "Texte lesen"),
        ("civil. Texte", "Texte"),  # letters that are no Roman numeral
    ],
)
def test_other_wordings_have_other_hashes(one: str, other: str) -> None:
    assert text_hash(one) != text_hash(other)


def test_the_hash_is_sha_256_of_the_normalized_wording() -> None:
    assert text_hash("  Die Lernenden\n planen ") == hashlib.sha256(b"die lernenden planen").hexdigest()


def test_the_normalized_wording_stays_composed_after_its_case_is_folded() -> None:
    # casefold parts "ǰ" into "j" and a combining caron
    assert normalized("\N{LATIN SMALL LETTER J WITH CARON}") == "\N{LATIN SMALL LETTER J WITH CARON}"
