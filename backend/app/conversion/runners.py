"""The conversion in a child process (plan M1, 3.4).

A PDF parser on an untrusted file may take minutes, memory without end, or the process down; in the
worker's own process it would stop the event loop, and with it the job's lease. So the conversion
runs in a child of its own, started fresh (``spawn``: the worker has threads and a loop a fork
would copy half of). Its answer comes back as a file, written whole before it is renamed: the
conversion as JSON, or the refusal with its code. A child that ends with no answer died - killed
by the kernel for its memory, or ended by a signal.

Whatever ends the waiting - the job cancelled, its deadline (``asyncio.timeout`` around the call),
its lease lost, which the worker turns into a cancel - kills the child at once. On POSIX the child
leads a process group of its own, which is killed whole, so nothing it started outlives it; on
Linux the kernel takes it before the worker when memory runs out. Windows has no process groups:
there a grandchild would outlive it (the engines start none).

No settings here: the caller names the engine, the page limit and the deadline.
"""

import asyncio
import contextlib
import json
import logging
import multiprocessing
import os
import shutil
import signal
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from app.conversion.base import Conversion, engine
from app.conversion.convert import ConversionRefused, convert_file

log = logging.getLogger(__name__)
POLL_S = 0.2  # how often the waiting asks whether the child is done
KILL_WAIT_S = 5.0
Convert = Callable[[Path, str, int], Conversion]


class ConversionFailed(RuntimeError):
    """The conversion raised in its process; its log says what (the message names no file)."""


class ConversionDied(RuntimeError):
    """The child ended without an answer: killed for its memory, or by a signal."""


def convert_with_engine(path: Path, name: str, max_pages: int) -> Conversion:
    return convert_file(path, engine(name), max_pages=max_pages)


async def convert_in_child(
    path: Path, *, engine: str, max_pages: int, convert: Convert = convert_with_engine
) -> Conversion:
    """The conversion of ``path`` by ``engine`` in a child process; ConversionRefused with its
    code, ConversionFailed or ConversionDied where there is none. ``convert`` stands in for the
    conversion in tests: a function the child imports by its name."""
    out = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="convert-"))
    child = multiprocessing.get_context("spawn").Process(
        target=_run, args=(convert, str(path), engine, max_pages, str(out)), daemon=True
    )
    try:
        child.start()
        try:
            while child.is_alive():
                await asyncio.sleep(POLL_S)
        except BaseException:
            _kill(child)  # cancelled, past its deadline, or the lease lost
            raise
        child.join()
        return await asyncio.to_thread(_outcome, child.exitcode, out)
    finally:
        shutil.rmtree(out, ignore_errors=True)


def _outcome(exit_code: int | None, out: Path) -> Conversion:
    if (out / "result.json").exists():
        return Conversion.model_validate_json((out / "result.json").read_bytes())
    if (out / "refused.json").exists():
        refused = json.loads((out / "refused.json").read_text(encoding="utf-8"))
        raise ConversionRefused(refused["code"], refused["message"])
    if (out / "crashed.json").exists():
        raise ConversionFailed("the conversion failed in its process")
    if exit_code is not None and exit_code < 0:
        raise ConversionDied(f"the conversion's process was ended by signal {-exit_code}")
    raise ConversionDied(f"the conversion's process ended without an answer (exit code {exit_code})")


def _kill(child: multiprocessing.process.BaseProcess) -> None:
    # sys.platform, not os.name: the type checker reads it, and checks each platform's calls
    if sys.platform != "win32" and child.pid is not None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(child.pid, signal.SIGKILL)  # the child leads its group: what it started too
    child.kill()
    child.join(KILL_WAIT_S)
    if child.is_alive():
        log.warning("the conversion's process %s outlived its kill", child.pid)


def _run(convert: Convert, path: str, name: str, max_pages: int, out: str) -> None:
    """The child: convert, and leave the answer in ``out``."""
    _stand_alone()
    try:
        conversion = convert(Path(path), name, max_pages)
    except ConversionRefused as refused:
        _write(Path(out) / "refused.json", json.dumps({"code": refused.code, "message": str(refused)}))
        return
    except Exception:
        logging.getLogger(__name__).exception("the conversion failed")
        _write(Path(out) / "crashed.json", "{}")
        raise SystemExit(1) from None
    _write(Path(out) / "result.json", conversion.model_dump_json())


def _stand_alone() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    if sys.platform != "win32":
        os.setsid()  # a group of its own, killed whole
    if sys.platform == "linux":
        with contextlib.suppress(OSError):
            # the kernel takes this process first when memory runs out, not the worker
            Path("/proc/self/oom_score_adj").write_text("1000", encoding="ascii")


def _write(path: Path, text: str) -> None:
    """Whole or not at all: the parent reads only a renamed file."""
    part = path.with_suffix(".part")
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)
