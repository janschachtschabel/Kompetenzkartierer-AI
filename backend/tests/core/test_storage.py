"""Object storage on the file system: keys stay inside its root, writes are whole or not at all."""

import os
import stat
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
    with pytest.raises(ObjectNotFound):  # on opening, before any piece
        storage.open_stream("sources/none.pdf")


def test_an_object_is_read_in_pieces_of_a_mib(storage: FileSystemStorage) -> None:
    # a download of up to MAX_UPLOAD_MB never holds the whole file
    data = bytes(range(256)) * (10 * 2**10)  # 2.5 MiB
    storage.put("sources/big.pdf", data)

    stream = storage.open_stream("sources/big.pdf")
    pieces = list(stream)

    assert stream.size == len(data)
    assert [len(piece) for piece in pieces] == [2**20, 2**20, 2**19]
    assert b"".join(pieces) == data
    storage.delete("sources/big.pdf")  # closed at the end: Windows deletes no open file


def test_a_stream_closed_early_lets_its_file_go(storage: FileSystemStorage) -> None:
    storage.put("sources/big.pdf", b"x" * (2 * 2**20))
    stream = storage.open_stream("sources/big.pdf")
    next(stream)

    stream.close()

    storage.delete("sources/big.pdf")
    with pytest.raises(StopIteration):
        next(stream)


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


@pytest.mark.parametrize(
    "key",
    ["runs/" + "a" * 256, "runs/name.", "CON", "runs/con.json", "nul", "runs/COM1", "LPT9.txt", "aux/x.json"],
    ids=["long-segment", "trailing-dot", "con", "con-ext", "nul", "com1", "lpt9-ext", "aux-folder"],
)
def test_a_key_a_file_system_cannot_hold_as_written_is_refused(storage: FileSystemStorage, key: str) -> None:
    # Windows drops a trailing dot and maps device names to devices; segments past 255 fail
    with pytest.raises(InvalidKey):
        storage.put(key, b"x")


def test_a_key_that_names_a_folder_of_other_keys_holds_no_object(storage: FileSystemStorage) -> None:
    storage.put("runs/1/answer.json", b"{}")

    assert storage.exists("runs/1") is False
    with pytest.raises(ObjectNotFound):
        storage.get("runs/1")
    with pytest.raises(ObjectNotFound):
        storage.delete("runs/1")
    with pytest.raises(InvalidKey):
        storage.put("runs/1", b"{}")


def test_a_key_below_an_object_holds_no_object(storage: FileSystemStorage) -> None:
    storage.put("runs/1.json", b"{}")

    with pytest.raises(ObjectNotFound):
        storage.get("runs/1.json/more")
    with pytest.raises(ObjectNotFound):
        storage.delete("runs/1.json/more")
    with pytest.raises(InvalidKey):
        storage.put("runs/1.json/more", b"{}")


def test_a_link_inside_the_root_does_not_lead_out_of_it(storage: FileSystemStorage, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    storage.root.mkdir(parents=True)
    try:
        (storage.root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("this system makes no symbolic links for this user")

    with pytest.raises(InvalidKey):
        storage.put("linked/x.json", b"{}")

    assert list(outside.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="a folder is synced on POSIX systems only")
def test_a_write_syncs_the_folder_it_renamed_in(
    storage: FileSystemStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the rename is only durable once the folder's entry is on disk
    synced: list[bool] = []
    real_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        synced.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        real_fsync(descriptor)

    monkeypatch.setattr("app.core.storage.os.fsync", recording_fsync)
    storage.put("runs/1.json", b"{}")

    assert synced == [False, True]


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


@pytest.mark.skipif(
    not Path("/proc/self/fd").is_dir(), reason="names a descriptor's path through /proc (Linux)"
)
def test_a_write_syncs_every_folder_it_made(
    storage: FileSystemStorage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a new folder is durable once its own entry is on disk, in the folder above it
    synced: list[str] = []
    real_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            synced.append(os.readlink(f"/proc/self/fd/{descriptor}"))
        real_fsync(descriptor)

    monkeypatch.setattr("app.core.storage.os.fsync", recording_fsync)
    storage.put("a/b/c.json", b"{}")

    root = storage.root
    assert set(synced) >= {str(tmp_path.resolve()), str(root), str(root / "a"), str(root / "a" / "b")}
