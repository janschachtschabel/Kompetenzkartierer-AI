"""Signs of symbol fonts mapped, and a text layer that looks broken noticed (plan M1, 3.3)."""

from app.conversion.encoding import MIN_SUSPECT, encoding_findings
from app.conversion.layout import RawBlock, RawCell, RawPage
from app.conversion.symbols import map_symbols

ARROW, REFERENCE = chr(0xF0DA), chr(0xF0DE)  # Wingdings 3 in Saxony's Lehrpläne (konzept §13.2)
BULLET = chr(0xF0B7)  # a bullet of the Symbol font, mapped by no rule
REPLACEMENT = chr(0xFFFD)


def text(page: int, words: str) -> RawBlock:
    return RawBlock(page, "text", words, (56, 100, 400, 112), 11.0, False, False)


def table(page: int, *values: str) -> RawBlock:
    return RawBlock(
        page,
        "table",
        "",
        (56, 300, 400, 400),
        None,
        False,
        False,
        (tuple(RawCell(v, False, page) for v in values),),
    )


def document(*pages: list[RawBlock]) -> list[RawPage]:
    return [RawPage(number, 842.0, list(blocks)) for number, blocks in enumerate(pages, start=1)]


def test_the_symbols_of_saxony_s_plans_become_the_arrows_they_show() -> None:
    pages = document([text(1, f"{ARROW} Lernbereich 2"), table(1, f"{REFERENCE} BNE", "Inhalt")])

    findings = map_symbols(pages)

    assert pages[0].blocks[0].text == f"{chr(0x2794)} Lernbereich 2"
    cell = pages[0].blocks[1].rows[0][0]
    assert cell is not None and cell.text == f"{chr(0x21D2)} BNE"
    assert findings == []


def test_another_sign_of_a_symbol_font_stays_and_is_counted_by_its_pages() -> None:
    pages = document(
        [text(1, f"{BULLET} erstens {BULLET} zweitens")], [table(2, f"{BULLET} drittens")], [text(3, "ohne")]
    )

    (finding,) = map_symbols(pages)

    assert (finding.code, finding.params) == (
        "unmapped_symbol",
        {"codepoint": "U+F0B7", "count": 3, "pages": [1, 2]},
    )
    assert BULLET in pages[0].blocks[0].text


def test_a_clean_text_layer_raises_nothing() -> None:
    pages = document([text(1, "Die Schülerinnen und Schüler wählen Maße für die Prüfung. " * 40)])

    assert encoding_findings(pages) == []


def test_replacement_signs_unread_glyphs_and_double_encoded_umlauts_are_suspect() -> None:
    broken = f"Sch{REPLACEMENT}ler (cid:31)(cid:32) FÃ¼r die PrÃ¼fung â€ž "
    pages = document([text(1, broken * 10 + "Die Lernenden planen. " * 20)])

    (finding,) = encoding_findings(pages)

    assert finding.code == "encoding_suspect"
    assert finding.params["count"] == 60
    assert 0.01 <= finding.params["share"] < 1
    assert finding.params["examples"] == [REPLACEMENT, "(cid:31)", "(cid:32)", "Ã¼", "â€"]


def read_as_cp1252(text: str) -> str:
    """The text's UTF-8 read as Windows-1252: "ß" becomes "ÃŸ", "Ä" "Ã" and a low quotation mark."""
    return text.encode("utf-8").decode("cp1252")


def test_umlauts_utf_8_read_as_windows_1252_are_suspect() -> None:
    broken = read_as_cp1252("Größe Änderung Öl Übung ") * 10

    (finding,) = encoding_findings(document([text(1, broken + "Die Lernenden planen. " * 20)]))

    assert finding.params["count"] == 50
    assert finding.params["examples"] == [read_as_cp1252(sign) for sign in ("ö", "ß", "Ä", "Ö", "Ü")]


def test_german_with_its_quotation_marks_and_dashes_is_not_suspect() -> None:
    quoted = f"{chr(0x201E)}Größe{chr(0x201C)} {chr(0x2013)} Änderung, Öl {chr(0x2014)} Übung. "

    assert encoding_findings(document([text(1, quoted * 40)])) == []


def test_a_few_suspect_signs_in_a_short_text_are_no_finding() -> None:
    pages = document([text(1, f"Sch{REPLACEMENT}ler " * (MIN_SUSPECT - 1))])

    assert encoding_findings(pages) == []


def test_a_few_suspect_signs_in_a_long_text_are_no_finding() -> None:
    pages = document([text(1, f"Sch{REPLACEMENT}ler " * 30 + "Die Lernenden planen ihre Arbeit. " * 400)])

    assert encoding_findings(pages) == []
