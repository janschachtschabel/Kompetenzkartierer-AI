"""Object storage on the file system: keys stay inside its root, writes are whole or not at all."""

from pathlib import Path

import pytest

from app.core.storage import FileSystemStorage, InvalidKey, ObjectNotFound


@pytest.fixture
def storage(tmp_path: Path) -> FileSystemStorage:
    return FileSystemStorage(tmp_path / "objects")


def test_an_object_is_written_read_and_deleted(storage: FileSystemStorage) -> None:
    storage.put("sources/ab/abcdef.pdf", b"%PDF-1.7 invented")

    assert storage.get("sources/ab/abcdef.pdf") == b"%PDF-1.7 invented"
    assert storage.exists("sources/ab/abcdef.pdf") is True
    storage.delete("sources/ab/abcdef.pdf")
    assert storage.exists("sources/ab/abcdef.pdf") is False


def test_writing_again_replaces_the_object(storage: FileSystemStorage) -> None:
    storage.put("runs/1.json", b"first")
    storage.put("runs/1.json", b"second")

    assert storage.get("runs/1.json") == b"second"


def test_a_missing_object_is_not_found(storage: FileSystemStorage) -> None:
    with pytest.raises(ObjectNotFound):
        storage.get("sources/none.pdf")
    with pytest.raises(ObjectNotFound):
        storage.delete("sources/none.pdf")


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../outside.txt",
        "sources/../../outside.txt",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "sources\\..\\outside.txt",
        "sources//double.txt",
        "sources/./same.txt",
        "sources/name\x00.txt",
        "sources/",
        "a" * 600,
    ],
    ids=[
        "empty",
        "parent",
        "nested-parent",
        "absolute",
        "drive",
        "backslash",
        "empty-segment",
        "dot",
        "nul",
        "trailing-slash",
        "too-long",
    ],
)
def test_a_key_that_could_leave_the_root_is_refused(
    storage: FileSystemStorage, tmp_path: Path, key: str
) -> None:
    with pytest.raises(InvalidKey):
        storage.put(key, b"x")

    assert not (tmp_path / "outside.txt").exists()


def test_a_failed_write_leaves_the_old_object_and_no_stray_file(
    storage: FileSystemStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage.put("runs/1.json", b"old")

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("disk full (invented)")

    monkeypatch.setattr("app.core.storage.os.replace", fail)
    with pytest.raises(OSError, match="disk full"):
        storage.put("runs/1.json", b"new")

    assert storage.get("runs/1.json") == b"old"
    assert [path.name for path in (storage.root / "runs").iterdir()] == ["1.json"]
