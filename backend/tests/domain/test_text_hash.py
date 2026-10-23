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
        ("Kompe\N{SOFT HYPHEN}\ntenzen erwerben", "Kompetenzen erwerben"),
        ("Kompe\N{HYPHEN}\ntenzen erwerben", "Kompetenzen erwerben"),
        ("Kompe-\N{NO-BREAK SPACE}\r\n  tenzen erwerben", "Kompetenzen erwerben"),
        ("E-\nMail schreiben", "E-Mail schreiben"),  # before a capital the hyphen is the word's
        ("Klasse 5-\n6", "Klasse 5-6"),
        ("Die Lernen\N{ZERO WIDTH SPACE}den planen", "Die Lernenden planen"),  # signs that set, not say
        ("\N{ZERO WIDTH NO-BREAK SPACE}Die Lernenden planen", "Die Lernenden planen"),
        ("Schu\N{COMBINING DIAERESIS}ler", "Schüler"),  # NFC
        ("Lern\N{EN DASH}Feld", "Lern-Feld"),
        ("STRASSE", "straße"),  # casefold, not lower
        ("1. a) Die Lernenden planen", "Die Lernenden planen"),  # numbering of three levels at most
        ("1.2. Die Lernenden planen", "Die Lernenden planen"),
        ("2.1.3.4 Die Lernenden planen", "Die Lernenden planen"),  # a section's number, as deep
        ("Texte\N{EM DASH}\nmehr", "Texte\N{EN DASH} mehr"),  # a dash at a line's end parts no word
        ("3. Klasse: Die Lernenden planen", "Klasse: Die Lernenden planen"),  # an ordinal reads as one
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
        ("1.000 Wörter lesen", "2.000 Wörter lesen"),  # a number, not a numbering
        ("100. Geburtstag", "Geburtstag"),
        ("Klasse 5-\n6", "Klasse 56"),  # digits are no word parted
        ("Texte\N{EM DASH}\nmehr", "Textemehr"),
    ],
)
def test_other_wordings_have_other_hashes(one: str, other: str) -> None:
    assert text_hash(one) != text_hash(other)


def test_the_hash_is_sha_256_of_the_normalized_wording() -> None:
    assert text_hash("  Die Lernenden\n planen ") == hashlib.sha256(b"die lernenden planen").hexdigest()


@pytest.mark.parametrize("wording", ["z. B. Texte lesen", "d. h. sie lesen"])
def test_a_letter_with_a_point_is_an_abbreviation_and_stays(wording: str) -> None:
    assert normalized(wording) == wording.casefold()


def test_the_hash_of_a_wording_beyond_ascii_stays_what_it_was() -> None:
    # fixed values: a change in the normalization or in Python's Unicode tables shows here
    wording = "U\N{COMBINING DIAERESIS}bergänge für Schülerinnen"

    assert normalized("Maße STRASSE") == "masse strasse"  # folding case joins the two
    assert text_hash(wording) == "7e06cbc3470a9b8254017d4a87ad66b99f53e2d34c1ede982446d66992fdc0ec"


def test_the_normalized_wording_stays_composed_after_its_case_is_folded() -> None:
    # casefold parts "ǰ" into "j" and a combining caron
    assert normalized("\N{LATIN SMALL LETTER J WITH CARON}") == "\N{LATIN SMALL LETTER J WITH CARON}"
