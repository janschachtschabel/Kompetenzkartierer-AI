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
