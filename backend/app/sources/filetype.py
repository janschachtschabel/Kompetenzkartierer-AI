"""What a source is, by its bytes: the trust boundary for every file that comes in.

Binary formats are known by their magic bytes, not by the name the sender chose; text formats
(Markdown, HTML, plain text, Turtle), which have no signature, by their name - and only if they
read as UTF-8. Anything else is refused. One check for every way a source comes in (upload, URL
import), so none takes another way round it. Taken over from curriculum-extractor
(services/filetype.py).
"""

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from app.sources.archives import check_archive

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TURTLE_MIME = "text/turtle"
# Name ending -> type, for text without a signature
_TEXT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".ttl": TURTLE_MIME,  # machine-readable curricula
}


class UnsupportedType(ValueError):
    """A file of no type a conversion reads."""


@dataclass(frozen=True)
class DetectedType:
    mime: str
    extension: str


def detect_type(filename: str | None, data: bytes) -> DetectedType | None:
    """The type, or ``None`` for none a conversion reads.

    A ZIP (``PK\\x03\\x04``) is taken for a DOCX, the only OOXML type in scope; a mislabelled
    XLSX or PPTX fails in the conversion, not here.
    """
    if data.startswith(b"%PDF"):
        return DetectedType("application/pdf", ".pdf")
    if data.startswith(b"PK\x03\x04"):
        return DetectedType(DOCX_MIME, ".docx")
    if data.startswith(b"{\\rtf"):
        return DetectedType("application/rtf", ".rtf")
    suffix = PurePosixPath(_base_name(filename)).suffix.lower()
    text_mime = _TEXT_TYPES.get(suffix)
    if text_mime and _is_utf8(data):
        return DetectedType(text_mime, suffix)
    return None


def accepted_type(filename: str | None, data: bytes) -> DetectedType:
    """What a source is, held to everything a source is held to before it is stored: a type a
    conversion reads, and for a ZIP parts within the bounds (app/sources/archives.py).

    Raises UnsupportedType, ArchiveUnreadable or ArchiveTooLarge. The archive check unpacks, so
    a caller on the event loop runs this in a thread.
    """
    detected = detect_type(filename, data)
    if detected is None:
        raise UnsupportedType("not a file type any conversion reads")
    if detected.mime == DOCX_MIME:
        check_archive(data)
    return detected


def stored_name(filename: str | None, detected: DetectedType) -> str:
    """The name a source is filed under: the one it came by, without any folder, ending in what
    its bytes are.

    Every conversion engine decides by the suffix: a download URL that names no file gave a PDF
    called ``source``, which the engines refused. A ZIP keeps whatever suffix it has: the
    signature is every OOXML type's, DOCX only the assumption, and a ``.pptx`` renamed to
    ``.docx`` would be a lie of our own making.
    """
    name = _base_name(filename)
    suffix = PurePosixPath(name).suffix.lower()
    if suffix == detected.extension or (suffix and detected.mime == DOCX_MIME):
        return name
    return f"{name or 'source'}{detected.extension}"


def _base_name(filename: str | None) -> str:
    """The last part of a name a sender gave, with either kind of slash."""
    return PureWindowsPath(PurePosixPath(filename or "").name).name


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
