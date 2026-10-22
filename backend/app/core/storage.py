"""Object storage for source files, raw model answers and exports.

The interface is S3's (Paket D adds that backend): an object is bytes under a key such as
``sources/ab/<sha256>.pdf``. A key is plain segments of letters, digits and ``._-`` joined by
``/`` - nothing that could leave the root on a file system, whatever the caller passed in.
The file system backend writes to a temporary file beside the target and renames it, so an
object is either the old or the new one, never half of it.

simplify: a process killed between the two leaves a ``.tmp-*`` file, which no key can name and
nothing removes yet; a sweep at start would, once the file system backend serves more than
development (Paket D brings S3).
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

MAX_KEY_CHARS = 512
MAX_SEGMENT_CHARS = 255  # a file name's limit on the common file systems
_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")
# The names Windows takes for devices, with any extension, in any case
_DEVICE = re.compile(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?", re.IGNORECASE)


class InvalidKey(ValueError):
    """The key is not plain segments joined by ``/``."""


class ObjectNotFound(KeyError):
    """No object under this key."""


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


def check_key(key: str) -> str:
    """``key``, if it is plain segments joined by ``/`` that every file system holds as written.

    A segment has at most 255 signs, does not end in a dot (Windows drops it) and is no device
    name (``CON``, ``nul.json``). Keys that differ in case only are two objects in S3 but one
    file on Windows and macOS: keep keys lower case, as hashes and ids are.
    """
    segments = key.split("/")
    if not key or len(key) > MAX_KEY_CHARS or not all(_plain(segment) for segment in segments):
        raise InvalidKey(f"not a storage key: {key[:80]!r}")
    return key


def _plain(segment: str) -> bool:
    return (
        _SEGMENT.fullmatch(segment) is not None
        and len(segment) <= MAX_SEGMENT_CHARS
        and not segment.endswith(".")
        and _DEVICE.fullmatch(segment) is None
    )


class FileSystemStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        # a checked key has no "..", but a link inside the root may lead out of it
        if not path.is_relative_to(self.root):
            raise InvalidKey(f"not a storage key: {key[:80]!r}")
        return path

    def put(self, key: str, data: bytes) -> None:
        """Raises InvalidKey for a key below an object or one that holds other keys: S3 keeps
        ``a`` and ``a/b`` side by side, a file system cannot."""
        path = self._path(key)
        made = [folder for folder in (path.parent, *path.parent.parents) if not folder.exists()]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, NotADirectoryError):
            raise InvalidKey(f"a key below an object: {key[:80]!r}") from None
        if path.is_dir():
            raise InvalidKey(f"a key that holds other keys: {key[:80]!r}")
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        # the object's entry, and the entry of each folder made for it, in the folder above
        for folder in [path.parent, *(made_folder.parent for made_folder in made)]:
            _sync_folder(folder)

    def get(self, key: str) -> bytes:
        path = self._object(key)
        try:
            return path.read_bytes()
        except FileNotFoundError:  # deleted in between
            raise ObjectNotFound(key) from None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._object(key)
        try:
            path.unlink()
        except FileNotFoundError:  # deleted in between
            raise ObjectNotFound(key) from None

    def _object(self, key: str) -> Path:
        """The object's file; ObjectNotFound for none, a folder of other keys, or below a file."""
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFound(key)
        return path


def _sync_folder(folder: Path) -> None:
    """A rename is durable once the folder's entry is on disk; Windows opens no folder for it."""
    if os.name != "posix":
        return
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
