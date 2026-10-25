"""The conversion in a child process (plan M1, 3.4).

A PDF parser on an untrusted file may take minutes, memory without end, or the process down; in the
worker's own process it would stop the event loop, and with it the job's lease. So the conversion
runs in a child of its own (app/core/child.py). Its answer comes back as a file, written whole before
it is renamed: the conversion as JSON, the refusal with its code, or the kind of error it raised.

How a child ends tells what may come of trying again. A refusal or a crash - an error raised in
the conversion, or in writing it down, or a fault that ended it by a signal of its own (SIGSEGV,
SIGABRT of a parser on a broken file) - is the file's, the same each time for the same engine:
ConversionRefused, ConversionCrashed. A child killed (SIGKILL) died, on Linux most likely by the
kernel for its memory: ConversionDied. A child that exits with no answer and no signal - a
library's exit, a full disk for the answer - says nothing of the file: ConversionFailed, which
may pass.

The child logs as the service does, but the PDF libraries say no more than warnings: at DEBUG
pdfminer logs each token it reads, the text of a file perhaps hidden from all but its editors.

Whatever ends the waiting - the job cancelled, its deadline (``asyncio.timeout`` around the call),
its lease lost, which the worker turns into a cancel - kills the child at once, and on POSIX all it
started (the engines start nothing).

No settings here: the caller names the engine, the page limit, how the child logs and the deadline.
"""

import json
import logging
import traceback
from collections.abc import Callable
from pathlib import Path

from app.conversion.base import Conversion, engine
from app.conversion.convert import ConversionRefused, convert_file
from app.core.child import KILLED, ChildLog, run_in_child, stand_alone, write
from app.core.logging import current_request_id

__all__ = [
    "ChildLog",
    "ConversionCrashed",
    "ConversionDied",
    "ConversionFailed",
    "Convert",
    "convert_in_child",
    "convert_with_engine",
    "log_crash",
]

LIBRARIES = ("pdfminer", "pdfplumber", "pypdfium2")
Convert = Callable[[Path, str, int], Conversion]


class ConversionCrashed(RuntimeError):
    """The conversion raised in its process; the message names the error's kind, not its text."""


class ConversionDied(RuntimeError):
    """The child was ended by a signal: killed for its memory, most likely."""


class ConversionFailed(RuntimeError):
    """The child exited without an answer and without a signal."""


def convert_with_engine(path: Path, name: str, max_pages: int) -> Conversion:
    return convert_file(path, engine(name), max_pages=max_pages)


async def convert_in_child(
    path: Path,
    *,
    engine: str,
    max_pages: int,
    convert: Convert = convert_with_engine,
    child_log: ChildLog | None = None,
) -> Conversion:
    """The conversion of ``path`` by ``engine`` in a child process; ConversionRefused with its
    code, ConversionCrashed, ConversionDied or ConversionFailed where there is none. ``convert``
    stands in for the conversion in tests: a function the child imports by its name."""
    told = child_log or ChildLog(level="WARNING", format="text", request_id=current_request_id())
    return await run_in_child(
        _run, (convert, str(path), engine, max_pages, told), prefix="convert-", read=_outcome
    )


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
    if exit_code == KILLED:
        raise ConversionDied(f"the conversion's process was ended by signal {-exit_code}")
    if exit_code is not None and exit_code < 0:
        raise ConversionCrashed(f"the conversion's process was ended by signal {-exit_code}")
    raise ConversionFailed(f"the conversion's process ended without an answer (exit code {exit_code})")


def _run(convert: Convert, path: str, name: str, max_pages: int, told: ChildLog, out: str) -> None:
    """The child: convert, and leave the answer in ``out``."""
    stand_alone(told, LIBRARIES)
    try:
        answer = convert(Path(path), name, max_pages).model_dump_json()
    except ConversionRefused as refused:
        write(Path(out) / "refused.json", json.dumps({"code": refused.code, "message": str(refused)}))
        return
    except Exception as error:
        log_crash(error)
        write(Path(out) / "crashed.json", json.dumps({"error": type(error).__name__}))
        raise SystemExit(1) from None
    # outside the try: an answer that cannot be written - the disk full - is no crash of the file
    write(Path(out) / "result.json", answer)
