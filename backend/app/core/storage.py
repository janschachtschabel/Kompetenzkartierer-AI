"""Object storage for source files, raw model answers and exports.

The interface is S3's (Paket D adds that backend): an object is bytes under a key such as
``sources/ab/<sha256>.pdf``. A key is plain segments of letters, digits and ``._-`` joined by
``/`` - nothing that could leave the root on a file system, whatever the caller passed in.
The file system backend writes to a temporary file beside the target and renames it, so an
object is either the old or the new one, never half of it.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

MAX_KEY_CHARS = 512
_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


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
    segments = key.split("/")
    if not key or len(key) > MAX_KEY_CHARS or not all(_SEGMENT.fullmatch(segment) for segment in segments):
        raise InvalidKey(f"not a storage key: {key[:80]!r}")
    return key


class FileSystemStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        if not path.is_relative_to(self.root):  # cannot happen for a checked key; the last guard
            raise InvalidKey(f"not a storage key: {key[:80]!r}")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise ObjectNotFound(key) from None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            raise ObjectNotFound(key) from None
