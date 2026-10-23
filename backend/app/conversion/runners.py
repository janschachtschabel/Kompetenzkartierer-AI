"""The conversion in a child process (plan M1, 3.4).

A PDF parser on an untrusted file may take minutes, memory without end, or the process down; in the
worker's own process it would stop the event loop, and with it the job's lease. So the conversion
runs in a child of its own, started fresh (``spawn``: the worker has threads and a loop a fork
would copy half of). Its answer comes back as a file, written whole before it is renamed: the
conversion as JSON, the refusal with its code, or the kind of error it raised.

How a child ends tells what may come of trying again. A refusal or a crash - an error raised in
the conversion, or in writing it down - is the file's, the same each time for the same engine:
ConversionRefused, ConversionCrashed. A child ended by a signal died, on Linux most likely killed
by the kernel for its memory: ConversionDied. A child that exits with no answer and no signal - a
library's exit, a full disk for the answer - says nothing of the file: ConversionFailed, which
may pass.

Whatever ends the waiting - the job cancelled, its deadline (``asyncio.timeout`` around the call),
its lease lost, which the worker turns into a cancel - kills the child at once. On POSIX the child
leads a process group of its own, which is killed whole, so nothing it started outlives it; on
Linux the kernel takes it before the worker when memory runs out. Windows has no process groups:
there a grandchild would outlive it (the engines start none).

No settings here: the caller names the engine, the page limit, how the child logs and the deadline.
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
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.conversion.base import Conversion, engine
from app.conversion.convert import ConversionRefused, convert_file
from app.core.logging import configure_logging, current_request_id, set_request_id

log = logging.getLogger(__name__)
POLL_S = 0.2  # how often the waiting asks whether the child is done
KILL_WAIT_S = 5.0
Convert = Callable[[Path, str, int], Conversion]


class ConversionCrashed(RuntimeError):
    """The conversion raised in its process; the message names the error's kind, not its text."""


class ConversionDied(RuntimeError):
    """The child was ended by a signal: killed for its memory, most likely."""


class ConversionFailed(RuntimeError):
    """The child exited without an answer and without a signal."""


@dataclass(frozen=True)
class ChildLog:
    """How the child logs: the service's level and format, and the request of the job it serves."""

    level: str
    format: str
    request_id: str


def convert_with_engine(path: Path, name: str, max_pages: int) -> Conversion:
    return convert_file(path, engine(name), max_pages=max_pages)


async def convert_in_child(
    path: Path,
    *,
    engine: str,
    max_pages: int,
    convert: Convert = convert_with_engine,
    log: ChildLog | None = None,
) -> Conversion:
    """The conversion of ``path`` by ``engine`` in a child process; ConversionRefused with its
    code, ConversionCrashed, ConversionDied or ConversionFailed where there is none. ``convert``
    stands in for the conversion in tests: a function the child imports by its name."""
    told = log or ChildLog(level="WARNING", format="text", request_id=current_request_id())
    # one mkdir, made here: in a thread, a cancel meanwhile would leave the folder behind
    out = Path(tempfile.mkdtemp(prefix="convert-"))
    child = multiprocessing.get_context("spawn").Process(
        target=_run, args=(convert, str(path), engine, max_pages, str(out), told), daemon=True
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


def log_crash(error: BaseException) -> None:
    """The error's kind and where it was raised; not its message, which may quote the file."""
    frames = "".join(traceback.format_tb(error.__traceback__))
    logging.getLogger(__name__).error("the conversion raised %s\n%s", type(error).__name__, frames)


def _outcome(exit_code: int | None, out: Path) -> Conversion:
    if (out / "result.json").exists():
        return Conversion.model_validate_json((out / "result.json").read_bytes())
    if (out / "refused.json").exists():
        refused = json.loads((out / "refused.json").read_text(encoding="utf-8"))
        raise ConversionRefused(refused["code"], refused["message"])
    if (out / "crashed.json").exists():
        crashed = json.loads((out / "crashed.json").read_text(encoding="utf-8"))
        raise ConversionCrashed(f"the conversion raised {crashed['error']} in its process")
    if exit_code is not None and exit_code < 0:
        raise ConversionDied(f"the conversion's process was ended by signal {-exit_code}")
    raise ConversionFailed(f"the conversion's process ended without an answer (exit code {exit_code})")


def _kill(child: multiprocessing.process.BaseProcess) -> None:
    # sys.platform, not os.name: the type checker reads it, and checks each platform's calls
    if sys.platform != "win32" and child.pid is not None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(child.pid, signal.SIGKILL)  # the child leads its group: what it started too
    child.kill()
    child.join(KILL_WAIT_S)
    if child.is_alive():
        log.warning("the conversion's process %s outlived its kill", child.pid)


def _run(convert: Convert, path: str, name: str, max_pages: int, out: str, told: ChildLog) -> None:
    """The child: convert, and leave the answer in ``out``."""
    _stand_alone(told)
    try:
        answer = convert(Path(path), name, max_pages).model_dump_json()
    except ConversionRefused as refused:
        _write(Path(out) / "refused.json", json.dumps({"code": refused.code, "message": str(refused)}))
        return
    except Exception as error:
        log_crash(error)
        _write(Path(out) / "crashed.json", json.dumps({"error": type(error).__name__}))
        raise SystemExit(1) from None
    # outside the try: an answer that cannot be written - the disk full - is no crash of the file
    _write(Path(out) / "result.json", answer)


def _stand_alone(told: ChildLog) -> None:
    configure_logging(told.level, told.format, stream=sys.stderr)
    set_request_id(told.request_id)
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
