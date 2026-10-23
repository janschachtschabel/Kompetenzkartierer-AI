"""The page as an engine reads it, before blocks get their names (plan M1, 3.2): text cleaned of
the signs no store keeps."""

from app.conversion.layout import clean_text


def test_control_signs_and_lone_surrogates_go_and_tabs_breaks_and_letters_stay() -> None:
    unwanted = [*map(chr, range(0x00, 0x09)), chr(0x0B), chr(0x0C), *map(chr, range(0x0E, 0x20)), chr(0x7F)]
    surrogates = [chr(0xD800), chr(0xDBFF), chr(0xDC00), chr(0xDFFF)]

    cleaned = clean_text(
        "Ma" + "".join(unwanted) + "ße\tund\nZeile" + "".join(surrogates) + " ✓ " + chr(0x1F600)
    )

    assert cleaned == "Maße\tund\nZeile ✓ " + chr(0x1F600)


def test_a_text_of_nothing_but_them_is_empty() -> None:
    assert clean_text(chr(0) * 3 + chr(0xD800)) == ""
