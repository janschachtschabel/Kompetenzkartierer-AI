"""A wording checked against the text of the blocks its anchor names (plan M1 8.1; konzept §13.1): found
word for word, across whitespace, with the gaps it marks, with the document's marks and case
(normalized) or as a paraphrase (fuzzy, with its likeness) - else not found. The search and its cases
come from the old app (ce_api/services/extraction/anchors.py, audit 2026-10-03 F01, live replays); here
the text is the anchor's blocks, one line end between two, not the whole document."""

import difflib
import time
from collections.abc import Iterator

import pytest

from app.pipeline import anchor_fuzzy, anchor_passage
from app.pipeline.anchor_check import MAX_FUZZY, check_wording
from app.pipeline.anchor_fuzzy import FUZZY_PLACES, FUZZY_QUOTE, MIN_RATIO
from app.pipeline.anchor_match import ELIDED_GAP, words

TWO = ["Die Schülerinnen und Schüler\nbeschreiben die Strukturen.", "Zweiter Absatz auf der zweiten Seite."]


def test_a_wording_the_block_holds_is_exact_with_its_place_in_the_text_of_the_blocks() -> None:
    found = check_wording("Zweiter Absatz auf der zweiten Seite.", TWO)

    assert (found.kind, found.score, found.quote) == ("exact", None, "Zweiter Absatz auf der zweiten Seite.")
    assert "\n".join(TWO)[found.start : found.end] == found.quote


def test_a_wording_a_block_breaks_into_lines_is_found_across_the_whitespace() -> None:
    found = check_wording("Die Schülerinnen und Schüler beschreiben die Strukturen.", TWO)

    assert (found.kind, found.quote) == ("whitespace", TWO[0])


def test_a_wording_over_two_blocks_is_found_across_the_line_end_between_them() -> None:
    # a heading the conversion parted into two blocks
    texts = ["Lernfeld 11: Wärmeerzeugungsanlagen für flüssige", "und feste Brennstoffe installieren"]

    found = check_wording(
        "Lernfeld 11: Wärmeerzeugungsanlagen für flüssige und feste Brennstoffe installieren", texts
    )

    assert (found.kind, found.quote) == ("whitespace", "\n".join(texts))


def test_a_wording_with_a_letter_changed_is_fuzzy_with_its_likeness() -> None:
    found = check_wording("Die Schülerinnen und Schueler beschreiben die Strukturen.", TWO)

    assert found.kind == "fuzzy" and found.score is not None and 0.8 <= found.score < 1
    assert found.quote == TWO[0]


@pytest.mark.parametrize("wording", ["Ein völlig anderer Satz, der nirgends im Dokument steht.", "   ", ""])
def test_a_wording_the_blocks_do_not_hold_is_not_found_and_has_no_place(wording: str) -> None:
    found = check_wording(wording, TWO)

    assert (found.kind, found.score, found.quote, found.start, found.end) == (
        "notFound",
        None,
        None,
        None,
        None,
    )


def test_blocks_without_text_hold_no_wording() -> None:
    assert check_wording("Zweiter Absatz", []).kind == "notFound"


# --- paraphrases (audit 2026-10-03, F01): each says what the document does not ----------------------

INKRAFT = "Dieser Lehrplan tritt zum 1. August 2023 in Kraft."
EXPERIMENTE = (
    "Die Schülerinnen und Schüler können optische Experimente selbstständig "
    "durchführen und die Ergebnisse protokollieren."
)
AUGE = "Die Schülerinnen und Schüler benennen die Bestandteile des menschlichen Auges."
PHYSIK = [
    "Fachlehrplan Physik Sekundarstufe I", "1 Vorwort", INKRAFT, "2 Optik", EXPERIMENTE, AUGE, "3 Mechanik",
    "Die Schülerinnen und Schüler beschreiben gleichförmige Bewegungen mit Diagrammen.",
]  # fmt: skip

PARAPHRASES = [
    (EXPERIMENTE.replace("können optische", "können keine optischen"), EXPERIMENTE),
    (
        "können keine optischen Experimente selbstständig durchführen",
        "können optische Experimente selbstständig durchführen",
    ),
    (EXPERIMENTE.replace("Experimente selbstständig", "Experimente nicht selbstständig"), EXPERIMENTE),
    (INKRAFT.replace("2023", "2024"), INKRAFT),
    (INKRAFT.replace("2023", "2032"), INKRAFT),
    (AUGE.replace("benennen", "beurteilen"), AUGE),
    (
        "beurteilen die Bestandteile des menschlichen Auges",
        "benennen die Bestandteile des menschlichen Auges",
    ),
]


def _ratio(text: str, wording: str) -> float:
    return difflib.SequenceMatcher(None, text, wording, autojunk=False).ratio()


@pytest.mark.parametrize(("wording", "document"), PARAPHRASES)
def test_a_changed_sentence_is_fuzzy_and_the_quote_is_the_document_s_wording(
    wording: str, document: str
) -> None:
    found = check_wording(wording, PHYSIK)

    assert (found.kind, found.quote) == ("fuzzy", document)
    assert "\n".join(PHYSIK)[found.start : found.end] == document
    assert found.score == round(_ratio(document, wording), 3)
    assert found.score is not None and 0.8 <= found.score < 1


def test_a_fuzzy_passage_takes_in_the_words_the_wording_left_out() -> None:
    sentence = "Die Schülerinnen und Schüler können sehr gut optische Experimente selbstständig durchführen."

    found = check_wording(sentence.replace("sehr gut ", ""), ["Optik", sentence])

    assert (found.kind, found.quote) == ("fuzzy", sentence)


def test_a_heading_with_a_dash_for_its_colon_is_normalized() -> None:
    texts = ["Lernfeld 11: Wärmeerzeugungsanlagen für flüssige", "und feste Brennstoffe installieren"]

    found = check_wording(
        "Lernfeld 11 - Wärmeerzeugungsanlagen für flüssige und feste Brennstoffe installieren", texts
    )

    assert (found.kind, found.score, found.quote) == ("normalized", None, "\n".join(texts))


@pytest.mark.parametrize(
    ("text", "wording", "document"),
    [
        (
            "Zu den Experimenten siehe hierzu Lernfeld 3.",
            "siehe hierzu Lernfeld 5",
            "siehe hierzu Lernfeld 3",
        ),
        (
            "Die Schülerinnen und Schüler können die Bestandteile des Auges beschreiben.",
            "Die Schülerinnen und Schüler können die Bestandteile des Auges erläutern.",
            "Die Schülerinnen und Schüler können die Bestandteile des Auges beschreiben.",
        ),
        (
            "Zeitrichtwert:\n- 45 Stunden für die Optik",
            "60 Stunden für die Optik",
            "45 Stunden für die Optik",
        ),
    ],
    ids=["number last", "operator last", "number first"],
)
def test_a_word_the_wording_replaced_at_either_end_is_the_document_s_in_the_quote(
    text: str, wording: str, document: str
) -> None:
    found = check_wording(wording, [text])

    assert (found.kind, found.quote) == ("fuzzy", document)


def test_a_fuzzy_passage_does_not_run_into_the_next_sentence() -> None:
    text = "Die Schülerinnen und Schüler protokollieren die Ergebnisse. Danach werten sie die Messreihen aus."

    found = check_wording("Die Schülerinnen und Schüler protokollieren die Ergebnisse und Messwerte.", [text])

    assert found.quote == "Die Schülerinnen und Schüler protokollieren die Ergebnisse."


LIST = [
    "Im Prüfungsbereich Versorgungstechnik soll der Prüfling nachweisen, dass er in der Lage ist,",
    "1. technische Unterlagen zu nutzen, Arbeitsschritte zu planen und Arbeitsmittel festzulegen,\n"
    "2. Material manuell und maschinell unter Berücksichtigung von Qualität zu bearbeiten,\n"
    "3. Bauteile zu fügen und zu montieren.",
]
LIST_WORDING = (
    "Im Prüfungsbereich Versorgungstechnik soll der Prüfling nachweisen, dass er in der Lage ist, "
    "technische Unterlagen zu nutzen, Arbeitsschritte zu planen und Arbeitsmittel festzulegen, Material "
    "manuell und maschinell unter Berücksichtigung von Qualität zu bearbeiten, Bauteile zu fügen und "
    "zu montieren."
)


def test_a_wording_that_runs_a_numbered_list_into_one_sentence_spans_the_list() -> None:
    found = check_wording(LIST_WORDING, LIST)

    assert found.kind == "fuzzy" and found.quote is not None and found.score is not None
    assert found.quote.startswith("Im Prüfungsbereich Versorgungstechnik")
    assert found.quote.endswith("3. Bauteile zu fügen und zu montieren.")
    assert found.score >= 0.8


def test_the_full_stop_of_an_abbreviation_ends_no_sentence() -> None:
    text = (
        "Die Lernenden nutzen digitale Werkzeuge, z. B. Tabellenkalkulationen und Datenbanken, um "
        "Messreihen auszuwerten."
    )
    wording = (
        "Die Lernenden nutzen digitale Werkzeuge wie Tabellenkalkulationen und Datenbanken, um "
        "Messreihen auszuwerten."
    )

    found = check_wording(wording, ["Versuche", text])

    assert (found.kind, found.quote) == ("fuzzy", text)


def test_a_passage_tightened_to_less_than_the_window_held_is_not_taken() -> None:
    text = (
        "Die Schülerinnen und Schüler planen Versuche. Sie werten Messreihen aus und dokumentieren die "
        "Ergebnisse."
    )
    wording = (
        "Die Schülerinnen und Schüler planen Versuche und werten Messreihen aus und dokumentieren die "
        "Ergebnisse."
    )

    found = check_wording(wording, ["Versuche", text])

    assert (found.kind, found.quote) == ("fuzzy", text)
    assert found.score is not None and found.score >= 0.8


BANKEN = (
    "Sie erklären die Aufgaben der Zentralbanken sowie die Funktion und Wirkung ihres Instrumentariums "
    "(Offenmarktgeschäfte, Fazilitäten, Mindestreserve) für die Gesamtwirtschaft (Inflation, Deflation) "
    "und den Bankensektor (Bankenaufsicht). Sie beschreiben und unterscheiden mögliche Ziele der "
    "Wirtschaftspolitik anhand des im Stabilitätsgesetz beschriebenen gesamtwirtschaftlichen "
    "Gleichgewichtes (Wirtschaftswachstum, Preisniveaustabilität, hoher Beschäftigungsstand, "
    "außenwirtschaftliches Gleichgewicht) und leiten mögliche Zielkonflikte ab."
)


@pytest.mark.parametrize(
    ("wording", "ending"),
    [
        (
            "Sie erklären die Aufgaben der Zentralbanken sowie die Funktion und Wirkung ihres "
            "Instrumentariums für die Gesamtwirtschaft und den Bankensektor.",
            "(Inflation, Deflation) und den Bankensektor",
        ),
        (
            "Sie beschreiben und unterscheiden mögliche Ziele der Wirtschaftspolitik anhand des im "
            "Stabilitätsgesetz beschriebenen gesamtwirtschaftlichen Gleichgewichtes und leiten mögliche "
            "Zielkonflikte ab.",
            "Gleichgewicht) und leiten mögliche Zielkonflikte ab.",
        ),
    ],
    ids=["first sentence", "second sentence"],
)
def test_a_passage_runs_on_to_the_wording_s_last_words_past_what_it_left_out(
    wording: str, ending: str
) -> None:
    found = check_wording(wording, [BANKEN])

    assert found.kind == "fuzzy" and found.quote is not None
    assert found.quote.startswith(wording[:40]) and found.quote.endswith(ending)
    # the quote's likeness, under the window's threshold: what it holds more is what the wording left out
    assert found.score is not None and 0.75 < found.score < MIN_RATIO


# --- normalized: the same words, marks and case aside -------------------------------------------------


@pytest.mark.parametrize(
    ("text", "wording"),
    [
        (
            "Sie wählen das Angebot aus ( Verkehrs-  und Betriebssicherheit;  Rückrufaktion, Inspektion ).",
            "Sie wählen das Angebot aus (Verkehrs- und Betriebssicherheit, Rückrufaktion, Inspektion).",
        ),
        (
            "Die Schülerinnen und Schüler analysieren Kundenaufträge, indem sie sich mit Hilfe "
            "Technischer Zeichnungen informieren.",
            "Die Schülerinnen und Schüler analysieren Kundenaufträge, indem sie sich mit Hilfe "
            "technischer Zeichnungen informieren.",
        ),
        (
            "Während beim Lernen einzelne Fähigkeiten, Fertig\xad keiten und Kenntnisse erworben werden.",
            "Während beim Lernen einzelne Fähigkeiten, Fertigkeiten und Kenntnisse erworben werden.",
        ),
    ],
    ids=["punctuation and spacing", "case", "soft hyphen"],
)
def test_the_same_words_in_other_marks_or_case_are_normalized_and_quote_the_document(
    text: str, wording: str
) -> None:
    found = check_wording(wording, [text])

    assert (found.kind, found.score) == ("normalized", None)
    assert found.quote is not None and found.quote == text[found.start : found.end]
    assert [word.casefold() for word in words(found.quote)] == [word.casefold() for word in words(wording)]


def test_a_soft_hyphen_and_its_space_do_not_part_a_word() -> None:
    assert words("Fähigkeiten, Fertig\xad keiten und Kenntnisse") == [
        "Fähigkeiten",
        "Fertigkeiten",
        "und",
        "Kenntnisse",
    ]


# --- elided: the document's words with the gaps the wording marks -------------------------------------

ELIDED = "Die Schülerinnen und Schüler können … durchführen und die Ergebnisse protokollieren."


def test_fragments_that_stand_in_order_are_elided_and_the_quote_is_the_passage() -> None:
    found = check_wording(ELIDED, PHYSIK)

    assert (found.kind, found.score, found.quote) == ("elided", None, EXPERIMENTE)


@pytest.mark.parametrize("mark", ["…", "...", "[…]", "[...]", "(…)"])
def test_every_common_mark_of_a_gap_is_read(mark: str) -> None:
    assert check_wording(ELIDED.replace("…", mark), PHYSIK).kind == "elided"


def test_a_common_opening_fragment_starts_where_its_passage_does() -> None:
    found = check_wording(
        "Die Schülerinnen und Schüler … benennen die Bestandteile des menschlichen Auges.", PHYSIK
    )

    assert (found.kind, found.quote) == ("elided", AUGE)


def test_fragments_out_of_order_are_no_elision() -> None:
    wording = "durchführen und die Ergebnisse protokollieren … Die Schülerinnen und Schüler können"

    assert check_wording(wording, PHYSIK).kind != "elided"


def test_fragments_further_apart_than_a_gap_may_be_are_no_elision() -> None:
    wording = "Die Lernenden planen … Sie prüfen die Anlage."
    filler = "Ein Satz über etwas ganz anderes. " * (ELIDED_GAP // 30 + 1)

    near = check_wording(wording, ["Die Lernenden planen die Montage. Sie prüfen die Anlage."])
    far = check_wording(wording, [f"Die Lernenden planen die Montage. {filler}Sie prüfen die Anlage."])

    assert near.kind == "elided" and far.kind != "elided"


@pytest.mark.parametrize(
    "wording",
    [
        "… können optische Experimente selbstständig durchführen",
        "Die Schülerinnen und Schüler benennen die Bestandteile des menschlichen...",
        "[…] benennen die Bestandteile des menschlichen Auges.",
    ],
)
def test_a_mark_at_either_end_only_marks_where_the_wording_was_cut(wording: str) -> None:
    assert check_wording(wording, PHYSIK).kind == "exact"


# --- bounds: the fuzzy search reads only where the wording's rare words stand ----------------------------

FILLER = "Ein Satz über etwas ganz anderes, der sich wiederholt. "


@pytest.fixture()
def difflib_work(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """What difflib is given to compare: len(a) * len(b) for each pair, the most its matching can cost
    - unlike a clock, the machine does not enter into it."""
    compared: list[int] = []
    real = difflib.SequenceMatcher

    class Counted(real):  # type: ignore[misc, valid-type]
        def set_seqs(self, a: str, b: str) -> None:
            compared.append(len(a) * len(b))
            super().set_seqs(a, b)

    monkeypatch.setattr(difflib, "SequenceMatcher", Counted)
    yield compared


def _most_difflib_may_compare(wording: str) -> int:
    """The fuzzy stage's bound: the opening against at most FUZZY_PLACES stretches of twice its
    length and a window of its own length at each, then the whole wording once against its window."""
    needle = len(wording.strip())
    opening = min(needle, FUZZY_QUOTE)
    return FUZZY_PLACES * (2 * opening * opening + opening * opening) + needle * needle


def test_a_wording_of_the_text_s_commonest_words_is_given_up_in_bounded_work(difflib_work: list[int]) -> None:
    # a table block of 770,000 signs, every word of the wording 14,000 times in it
    text = FILLER * 14_000
    wording = ("Ein Satz über etwas ganz anderes, der sich nicht wiederholt. " * 40)[:MAX_FUZZY]

    started = time.thread_time()
    check_wording(wording, [text])
    spent = time.thread_time() - started

    assert sum(difflib_work) <= _most_difflib_may_compare(wording), f"difflib compared {sum(difflib_work):,}"
    assert spent < 2.0, f"{spent:.2f} s of CPU time"


def test_a_wording_longer_than_the_fuzzy_search_takes_is_found_only_word_for_word(
    difflib_work: list[int],
) -> None:
    sentence = "Die Lernenden planen die Montage einer Anlage. "
    text = sentence * 60

    word_for_word = check_wording(text.strip(), [text])
    changed = check_wording(text.strip().replace("Montage", "Wartung", 1), [text])

    assert len(text) > MAX_FUZZY
    assert (word_for_word.kind, changed.kind) == ("exact", "notFound")
    assert difflib_work == []


PASSAGE = (
    "Die Schülerinnen und Schüler analysieren den Kundenauftrag zur Installation einer "
    "Photovoltaikanlage. Sie ermitteln die technischen Anforderungen an Wechselrichter, "
    "Speicher und Netzanschluss und berücksichtigen dabei die Vorgaben des Netzbetreibers. "
    "Sie planen die Montage, wählen Komponenten nach Datenblättern aus und dokumentieren "
    "ihre Entscheidungen. Sie prüfen die Anlage vor der Inbetriebnahme, messen Isolations- "
    "und Schleifenwiderstände und übergeben die Anlage mit einer Einweisung an den Kunden. "
    "Sie reflektieren den Ablauf und leiten Verbesserungen für künftige Aufträge ab."
)


def test_a_wording_whose_rest_the_blocks_lack_is_not_found_on_its_opening() -> None:
    wording = PASSAGE[:320] + (
        " Anschließend entwerfen sie ein Marketingkonzept für den Betrieb, kalkulieren "
        "Werbekosten, gestalten Flyer und präsentieren das Konzept der Geschäftsleitung "
        "in einer halbstündigen Präsentation mit anschließender Diskussion im Plenum."
    )

    assert check_wording(wording, ["Lernfeld 12", PASSAGE, "Lernfeld 13", "Anderer Text."]).kind == "notFound"


def test_a_long_paraphrase_is_spanned_whole() -> None:
    found = check_wording(
        PASSAGE.replace("Sie prüfen die Anlage", "Sie prüfen eine Anlage"), ["Lernfeld 12", PASSAGE]
    )

    assert found.kind == "fuzzy" and found.quote == PASSAGE


# --- the old app's thresholds and its choice of the best place ---------------------------------------


def test_the_thresholds_are_the_old_app_s() -> None:
    # plan M1 8.1: thresholds as in the old app (measured there on live replays)
    assert (anchor_fuzzy.MIN_RATIO, anchor_fuzzy.CLEARLY_WORSE, anchor_fuzzy.TIGHTEN_MARGIN) == (
        0.8,
        0.05,
        24,
    )
    assert (anchor_fuzzy.FUZZY_QUOTE, anchor_fuzzy.FUZZY_PLACES, anchor_fuzzy.FUZZY_RARE) == (300, 32, 4)
    assert (ELIDED_GAP, anchor_passage.TAIL_REACH, MAX_FUZZY) == (400, 400, 2_000)


EXPECTATION = (
    "Die Schülerinnen und Schüler analysieren die Anforderungen an geregelte {} und planen deren "
    "Inbetriebnahme."
)


def test_a_paraphrase_is_placed_on_the_sentence_most_like_it_not_an_earlier_one_like_it() -> None:
    texts = [EXPECTATION.format("Anlagen"), FILLER * 30, EXPECTATION.format("Systeme")]  # places apart
    paraphrase = (
        "Die Schülerinnen und Schüler analysieren Anforderungen an geregelte Systeme und planen deren "
        "Inbetriebnahme."
    )

    found = check_wording(paraphrase, texts)

    assert (found.kind, found.quote) == ("fuzzy", texts[2])


@pytest.mark.parametrize(
    ("text", "wording"),
    [
        (
            "Die Lernenden nutzen digitale Werkzeuge, z. B. Tabellenkalkulationen und Datenbanken, um "
            "Messreihen auszuwerten.",
            "Die Lernenden nutzen digitale Werkzeuge wie Tabellenkalkulationen und Datenbanken, um "
            "Messreihen auszuwerten.",
        ),
        (
            "Die Lernenden lösen die Aufgaben 1. bis 3. der Reihe und vergleichen ihre Ergebnisse.",
            "Die Lernenden lösen die Aufgaben eins bis drei der Reihe und vergleichen ihre Ergebnisse.",
        ),
    ],
    ids=["abbreviation", "numbers"],
)
def test_the_first_passage_offered_is_the_whole_sentence_where_its_dots_end_none(
    text: str, wording: str
) -> None:
    # the passages after the first make up for a sentence cut short: the first one is looked at alone
    first = next(anchor_passage.candidates(text, 0, len(text), wording, margin=anchor_fuzzy.TIGHTEN_MARGIN))

    assert text[slice(*first)] == text


# --- review of package 8a: the text of blocks as the conversion keeps it -------------------------------


@pytest.mark.parametrize(
    ("text", "wording"),
    [
        (
            "Die Lernenden erwerben Kompe-\ntenzen im Umgang mit Licht.",
            "Die Lernenden erwerben Kompetenzen im Umgang mit Licht.",
        ),
        ("Wärmeerzeugungs-\nanlagen installieren", "Wärmeerzeugungsanlagen installieren"),
        ("Die Lernenden pflegen saisonales Gemüse.", "Die Lernenden pflegen saisonales Gemüse."),
    ],
    ids=["hyphen at a line's end", "a heading parted in its block", "decomposed letters"],
)
def test_a_word_parted_at_a_line_s_end_or_written_decomposed_is_normalized(text: str, wording: str) -> None:
    # a block keeps its lines (app/conversion/lines.py), and a PDF may write "ü" as "u" and its mark
    found = check_wording(wording, [text])

    assert (found.kind, found.score, found.quote) == ("normalized", None, text)


def test_a_hyphen_before_a_capital_parts_two_words() -> None:
    # "E-\nMail" is the word "E-Mail", not "EMail": text_hash joins a parted word only before a small letter
    found = check_wording("Die Lernenden schreiben eine EMail.", ["Die Lernenden schreiben eine E-\nMail."])

    assert found.kind == "fuzzy"


def test_a_quote_ends_after_the_marks_of_its_last_letters() -> None:
    text = "Die Lernenden pflegen saisonales Gemüse im Beet."

    found = check_wording("Die Lernenden pflegen saisonales Gemüse.", [text])

    assert found.kind == "normalized" and found.quote == "Die Lernenden pflegen saisonales Gemüse"


@pytest.mark.parametrize(
    ("wording", "text"),
    [
        ("Lernfeld 1", "Lernfeld 12: Anlagen instand halten und ändern"),
        ("2.1 Mechanik", "12.1 Mechanik"),
        ("Lernfeld 1 … ändern", "Lernfeld 12: Anlagen instand halten und ändern"),
    ],
    ids=["ends inside a number", "begins inside a number", "elided"],
)
def test_a_wording_the_text_holds_only_inside_longer_words_is_not_found_word_for_word(
    wording: str, text: str
) -> None:
    # X5 checks the model's claim that the blocks hold the wording: "Lernfeld 12" does not hold "Lernfeld 1"
    assert check_wording(wording, [text]).kind not in ("exact", "whitespace", "elided")


def test_a_wording_that_begins_or_ends_with_a_mark_may_stand_next_to_a_word() -> None:
    # only an edge where the wording has a letter or digit can cut a word
    found = check_wording("(vgl. Kapitel 2)", ["Siehe Optik(vgl. Kapitel 2)der Anlage."])

    assert (found.kind, found.quote) == ("exact", "(vgl. Kapitel 2)")


def test_a_wording_is_found_where_it_stands_as_whole_words_after_a_place_inside_one() -> None:
    text = "Lernfeld 12: Anlagen instand halten\nLernfeld 1: Grundlagen"

    found = check_wording("Lernfeld 1", [text])

    assert (found.kind, found.start) == ("exact", text.index("Lernfeld 1:"))


def test_a_heading_block_named_with_its_paragraph_is_a_line_like_any_other() -> None:
    # the old app moved a passage off a markdown heading line; the anchor's texts do not say which block is a
    # heading, and a sentence a page break parted begins on its first block (plan M1, Nachtrag 8a)
    texts = ["Ziele des Fachs", "Die Lernenden beschreiben die Ziele des Unterrichts."]

    found = check_wording("Fach: Die Lernenden erläutern die Ziele des Unterrichts.", texts)

    assert (found.kind, found.quote) == ("fuzzy", "Fachs\n" + texts[1])


def test_the_document_s_words_before_a_passage_are_not_taken_from_the_block_before() -> None:
    texts = ["2 Optik", "Die Schülerinnen und Schüler können optische Experimente selbständig durchführen."]

    found = check_wording(
        "Insgesamt Die Schülerinnen und Schüler können optische Experimente selbstständig durchführen.", texts
    )

    assert (found.kind, found.quote) == ("fuzzy", texts[1])


def test_the_document_s_words_after_a_passage_are_not_taken_from_the_block_after() -> None:
    texts = ["Die Person zeigt, dass sie in der Lage ist,", "Dieser Satz steht im nächsten Block."]

    found = check_wording("Die Person zeigt, dass sie in der Lage ist, Probleme", texts)

    assert (found.kind, found.quote) == ("fuzzy", texts[0])


def test_a_passage_takes_in_the_document_s_opening_words_the_window_started_after() -> None:
    # the wording left out a word before its longest shared stretch: its window starts that much late
    text = "1. Die Lernenden messen elektrische Spannungen an Bauteilen und vergleichen sie mit dem Sollwert."

    found = check_wording(
        "1. Die Lernenden Spannungen an Bauteilen und vergleichen sie mit dem Sollwert.", [text]
    )

    assert (found.kind, found.quote) == ("fuzzy", text)


def test_a_wording_as_long_as_the_fuzzy_search_takes_is_searched_fuzzy() -> None:
    text = " ".join(f"Begriff{number}" for number in range(400))[:MAX_FUZZY]
    wording = text.replace("Begriff7 ", "Begriffx ", 1)  # one sign for one

    found = check_wording(wording, [text])

    assert (len(wording), found.kind) == (MAX_FUZZY, "fuzzy")


def test_a_long_paraphrase_found_in_a_table_costs_its_thread_a_bounded_time() -> None:
    # X5 checks all of a document's anchors in one thread beside the event loop
    table = " ".join(
        f"Zelle {number}: Begriff{number} steht in Zeile {number % 97}." for number in range(1_200)
    )
    start = table.index("Zelle 300:")
    wording = table[start : start + 1_950].replace("steht", "stand")

    started = time.thread_time()
    found = check_wording(wording, [table])
    spent = time.thread_time() - started

    assert found.kind == "fuzzy"
    assert spent < 5.0, f"{spent:.2f} s of CPU time"
