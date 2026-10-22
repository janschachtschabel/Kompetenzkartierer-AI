"""A ZIP that comes in (a DOCX, an OOXML file) held to bounds before anything unpacks it.

Taken over from curriculum-extractor (services/filetype.py), with what its audits found:
python-docx holds every part in memory, so a 200 KiB upload that expanded to 200 MiB peaked at
438 MiB in 0.6 s, and about 3 MB of DOCX reached the container's limit. A real curriculum is
far below all three bounds.
"""

import copy
import io
import sys
import zipfile
import zlib

MAX_ARCHIVE_ENTRIES = 5000
MAX_ARCHIVE_EXPANDED = 256 * 2**20
# A part over a MiB that expands more than a hundredfold is a bomb, not a text
_BOMB_MIN_SIZE = 2**20
_BOMB_RATIO = 100
# How every document packs its parts. zipfile unpacks what it reads of a BZIP2 or LZMA part
# whole, however small a block it is asked for, so no measurement in blocks bounds those
_PACKED_WITH = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_ENCRYPTED = 0x1  # general-purpose bit 0
_MEASURING_BLOCK = 2**16


class ArchiveUnreadable(ValueError):
    """A ZIP whose directory or parts cannot be read: not a document to convert."""


class ArchiveTooLarge(ValueError):
    """A ZIP that would expand beyond what one conversion may hold."""


def check_archive(data: bytes) -> None:
    """Refuse a ZIP whose parts would expand past the bounds above.

    The central directory first: how many parts, the sizes they state, the bomb ratio, how
    they are packed. Then every part unpacked in blocks and counted, for those sizes are the
    uploader's to state, and zipfile unpacks a part - up to a GiB at a time - before it cuts it
    to the size stated: 112 bytes stating 16 held 205 MiB at once. A part holding more than it
    states is refused here, so nothing that reads the archive after unpacks more than the
    stated sizes allow. That unpacks up to the bound on the sum - 1.3 s of CPU for 256 MiB of
    text, measured: a caller on the event loop runs it in a thread.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError) as error:
        raise ArchiveUnreadable("not a readable archive") from error
    with archive:
        parts = archive.infolist()
        if len(parts) > MAX_ARCHIVE_ENTRIES:
            raise ArchiveTooLarge(f"more than {MAX_ARCHIVE_ENTRIES} parts")
        if sum(part.file_size for part in parts) > MAX_ARCHIVE_EXPANDED:
            raise ArchiveTooLarge("expands beyond the size limit")
        if any(
            part.file_size > _BOMB_MIN_SIZE and part.file_size > _BOMB_RATIO * max(part.compress_size, 1)
            for part in parts
        ):
            raise ArchiveTooLarge("a part expands beyond any document's")
        if any(part.compress_type not in _PACKED_WITH for part in parts):
            raise ArchiveUnreadable("a part is packed in a way no document is")
        if any(part.flag_bits & _ENCRYPTED for part in parts):
            raise ArchiveUnreadable("a part is encrypted")
        for part in parts:
            if _unpacks_past_its_size(archive, part):
                raise ArchiveTooLarge("a part unpacks past the size it states")


def _unpacks_past_its_size(archive: zipfile.ZipFile, part: zipfile.ZipInfo) -> bool:
    """Whether the part unpacks to more bytes than it states, counted a block at a time and
    given up a block past them. Opened as told no size: told its own, zipfile would cut it
    there - after unpacking it."""
    untold = copy.copy(part)
    untold.file_size = sys.maxsize
    unpacked = 0
    try:
        with archive.open(untold) as stream:
            while block := stream.read(_MEASURING_BLOCK):
                unpacked += len(block)
                if unpacked > part.file_size:
                    return True
    except (zipfile.BadZipFile, EOFError, ValueError, NotImplementedError, zlib.error) as error:
        raise ArchiveUnreadable("a part cannot be unpacked") from error
    return False
