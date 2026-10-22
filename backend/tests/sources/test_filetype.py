"""What a source is, by its bytes: the trust boundary for every file that comes in.

Taken over from curriculum-extractor (tests/test_filetype.py), with its findings: magic bytes
over names, text only as UTF-8, a ZIP held to bounds before anything unpacks it.
"""

import tracemalloc
import zipfile

import pytest

from app.sources import archives
from app.sources.archives import ArchiveTooLarge, ArchiveUnreadable, check_archive
from app.sources.filetype import DOCX_MIME, UnsupportedType, accepted_type, detect_type, stored_name
from tests.sources.zip_helpers import directory_says, make_zip

# --- the type, by content


def test_a_pdf_is_known_by_its_magic_bytes() -> None:
    detected = detect_type("x.pdf", b"%PDF-1.7 ...")
    assert detected is not None and detected.mime == "application/pdf"


def test_a_zip_is_taken_for_a_docx() -> None:
    detected = detect_type("x.docx", b"PK\x03\x04rest")
    assert detected is not None and detected.mime == DOCX_MIME


def test_an_rtf_is_known_by_its_magic_bytes() -> None:
    detected = detect_type("x.rtf", b"{\\rtf1\\ansi")
    assert detected is not None and detected.mime == "application/rtf"


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("lp.md", "text/markdown"),
        ("page.html", "text/html"),
        ("note.txt", "text/plain"),
        ("lp.ttl", "text/turtle"),
    ],
)
def test_text_is_known_by_its_name_if_it_reads_as_utf8(name: str, mime: str) -> None:
    detected = detect_type(name, "# Titel äöü\n".encode())
    assert detected is not None and detected.mime == mime


def test_magic_bytes_win_over_the_name() -> None:
    # a PDF named .md is a PDF: content, not the name the sender chose
    detected = detect_type("spoof.md", b"%PDF-1.4")
    assert detected is not None and detected.mime == "application/pdf"


@pytest.mark.parametrize(
    ("name", "data"),
    [("evil.bin", b"\x00\x01\x02rubbish"), ("broken.md", b"\xff\xfe\x00bad"), (None, b"plain text")],
    ids=["unknown-binary", "text-not-utf8", "no-name-no-magic"],
)
def test_anything_else_is_no_type(name: str | None, data: bytes) -> None:
    assert detect_type(name, data) is None


def test_a_file_of_no_type_is_refused() -> None:
    with pytest.raises(UnsupportedType):
        accepted_type("evil.exe", b"MZ\x90\x00")


def test_a_zip_is_held_to_the_archive_bounds_before_it_is_accepted() -> None:
    with pytest.raises(ArchiveTooLarge):
        accepted_type("bomb.docx", make_zip({"word/document.xml": b"\0" * (4 * 2**20)}))


# --- the name a source is filed under


@pytest.mark.parametrize(
    ("name", "data", "stored"),
    [
        ("lehrplan.pdf", b"%PDF-1.7", "lehrplan.pdf"),
        ("14629", b"%PDF-1.7", "14629.pdf"),  # a download URL that names no file
        (None, b"%PDF-1.7", "source.pdf"),
        ("lehrplan.PDF", b"%PDF-1.7", "lehrplan.PDF"),
        ("folien.pptx", b"PK\x03\x04", "folien.pptx"),  # a ZIP keeps its own suffix
        ("../../etc/lehrplan.pdf", b"%PDF-1.7", "lehrplan.pdf"),
    ],
)
def test_a_source_is_filed_under_its_name_ending_in_what_it_is(
    name: str | None, data: bytes, stored: str
) -> None:
    detected = detect_type(name, data)
    assert detected is not None
    assert stored_name(name, detected) == stored


def test_a_stored_name_shows_what_it_is_without_hidden_signs() -> None:
    # a right-to-left override makes "lehrplan<RLO>fdp.exe" read as "lehrplanexe.pdf"
    detected = detect_type("x.pdf", b"%PDF-1.7")
    assert detected is not None

    assert stored_name("lehr‮plan\x00.pdf", detected) == "lehrplan.pdf"
    assert stored_name("​‮", detected) == "source.pdf"


def test_a_long_name_is_cut_to_what_a_file_system_holds_keeping_its_ending() -> None:
    detected = detect_type("x.pdf", b"%PDF-1.7")
    assert detected is not None

    stored = stored_name("Lehrplan" * 50 + ".pdf", detected)

    assert len(stored) == 255
    assert stored.endswith(".pdf")


# --- archives that expand past what a conversion may hold (old app audit 2026-09-26, E-05)


def test_an_ordinary_archive_passes() -> None:
    check_archive(make_zip({"word/document.xml": b"<w:document/>" * 200, "[Content_Types].xml": b"<Types/>"}))


def test_an_archive_that_expands_a_thousandfold_is_refused() -> None:
    # A 200 KiB upload expanded to 200 MiB, and python-docx held 438 MiB of it in memory
    bomb = make_zip({"word/document.xml": b"\0" * (4 * 2**20)})
    assert len(bomb) < 20_000

    with pytest.raises(ArchiveTooLarge):
        check_archive(bomb)


def test_an_archive_of_too_many_parts_is_refused() -> None:
    with pytest.raises(ArchiveTooLarge):
        check_archive(make_zip({f"word/part{index}.xml": b"x" for index in range(5001)}))


def test_an_archive_too_large_in_sum_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archives, "MAX_ARCHIVE_EXPANDED", 1_000)

    with pytest.raises(ArchiveTooLarge):
        check_archive(make_zip({"a.xml": bytes(range(256)) * 3, "b.xml": bytes(range(256)) * 3}))


def test_an_archive_that_cannot_be_read_is_refused() -> None:
    with pytest.raises(ArchiveUnreadable):
        check_archive(b"PK\x03\x04" + b"\0" * 20)


def test_a_part_that_unpacks_past_the_size_it_states_is_refused_in_blocks() -> None:
    # zipfile unpacks a part - up to a GiB at a time - before it cuts it to the size stated:
    # 112 bytes stating 16 held 205 MiB at once, and every bound above passed
    lying = directory_says(make_zip({"word/document.xml": b"\0" * (32 * 2**20)}), size=16)

    tracemalloc.start()
    try:
        with pytest.raises(ArchiveTooLarge):
            check_archive(lying)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert peak < 4 * 2**20


@pytest.mark.parametrize("method", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA], ids=["bzip2", "lzma"])
def test_a_part_packed_past_any_block_bound_is_refused(method: int) -> None:
    # zipfile unpacks what it reads of a BZIP2 or LZMA part whole, however small the block asked for
    with pytest.raises(ArchiveUnreadable):
        check_archive(make_zip({"word/document.xml": b"<w:document/>"}, method))


def test_an_encrypted_part_is_refused() -> None:
    # a part that cannot be read cannot be measured
    encrypted = directory_says(make_zip({"word/document.xml": b"<w:document/>"}), flags=0x1)

    with pytest.raises(ArchiveUnreadable):
        check_archive(encrypted)
