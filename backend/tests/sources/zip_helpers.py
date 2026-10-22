"""ZIP archives whose directory says one thing of their parts and holds another: the sizes and
flags a ZIP's central directory states are the uploader's to choose, and zipfile believes them.
Taken over from curriculum-extractor (tests/zip_helpers.py)."""

import io
import struct
import zipfile

_DIRECTORY_ENTRY = b"PK\x01\x02"


def make_zip(entries: dict[str, bytes], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", method) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def directory_only(entries: int) -> bytes:
    """A ZIP whose central directory holds ``entries`` parts that all point at one empty local
    header: 47 bytes a part, so a few MB name a million of them."""
    local = b"PK\x03\x04" + b"\0" * 26
    entry = struct.pack("<4s6H3I5H2I", _DIRECTORY_ENTRY, 20, 20, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0)
    directory = entry + b"a"
    end = struct.pack(
        "<4s4H2IH",
        b"PK\x05\x06",
        0,
        0,
        min(entries, 0xFFFF),
        min(entries, 0xFFFF),
        len(directory) * entries,
        len(local),
        0,
    )
    return local + directory * entries + end


def directory_says(data: bytes, *, size: int | None = None, flags: int | None = None) -> bytes:
    """``data`` with every part's entry in the central directory stating ``size`` unpacked bytes
    and ``flags`` as its general-purpose bits, where given. The archive carries no comment, as
    zipfile writes it."""
    out = bytearray(data)
    (entry,) = struct.unpack_from("<I", out, len(out) - 22 + 16)
    while out[entry : entry + 4] == _DIRECTORY_ENTRY:
        if flags is not None:
            struct.pack_into("<H", out, entry + 8, flags)
        if size is not None:
            struct.pack_into("<I", out, entry + 24, size)
        name, extra, comment = struct.unpack_from("<HHH", out, entry + 28)
        entry += 46 + name + extra + comment
    return bytes(out)
