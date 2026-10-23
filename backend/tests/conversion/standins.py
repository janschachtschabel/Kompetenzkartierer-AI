"""Conversions that stand in for the real one in the child process (tests/conversion/test_runners.py).

They live at module level so that the spawned child can import them by name.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import cast

from app.conversion.base import Block, Conversion
from app.conversion.convert import ConversionRefused
from app.core.logging import current_request_id


def reading(path: Path, engine: str, max_pages: int) -> Conversion:
    block = Block(
        id="p1-b1",
        page=1,
        kind="text",
        text=f"{engine} read up to {max_pages} pages",
        bbox=(56, 100, 300, 112),
        font_size=11,
        bold=False,
        italic=False,
    )
    return Conversion(engine=engine, engine_version="1", pages=1, printed_pages=("5",), blocks=(block,))


def refusing(path: Path, engine: str, max_pages: int) -> Conversion:
    raise ConversionRefused("needs_ocr", "too few pages carry a text layer")


def crashing(path: Path, engine: str, max_pages: int) -> Conversion:
    raise RuntimeError(f"broke on {path}")


def answering_nothing(path: Path, engine: str, max_pages: int) -> Conversion:
    """A conversion that is none: the child fails to write it down."""
    return cast(Conversion, None)


def exiting(path: Path, engine: str, max_pages: int) -> Conversion:
    os._exit(3)


def segfaulting(path: Path, engine: str, max_pages: int) -> Conversion:
    if sys.platform != "win32":  # the test runs on POSIX alone
        os.kill(os.getpid(), signal.SIGSEGV)  # as a parser fault on a broken file ends a process
    raise AssertionError("not ended")


def telling_the_libraries_levels(path: Path, engine: str, max_pages: int) -> Conversion:
    """Says the levels the PDF libraries log at, in the text of its block."""
    levels = [logging.getLevelName(logging.getLogger(name).getEffectiveLevel()) for name in LIBRARIES]
    found = reading(path, engine, max_pages)
    return found.model_copy(
        update={"blocks": (found.blocks[0].model_copy(update={"text": " ".join(levels)}),)}
    )


LIBRARIES = ("pdfminer.psparser", "pdfplumber", "pypdfium2")


def telling_its_logging(path: Path, engine: str, max_pages: int) -> Conversion:
    """Says how the child logs, in the text of its block: the root's level and format, the request."""
    root = logging.getLogger()
    formats = sorted({type(handler.formatter).__name__ for handler in root.handlers})
    found = reading(path, engine, max_pages)
    text = f"{logging.getLevelName(root.level)} {','.join(formats)} {current_request_id()}"
    return found.model_copy(update={"blocks": (found.blocks[0].model_copy(update={"text": text}),)})


def vanishing(path: Path, engine: str, max_pages: int) -> Conversion:
    if sys.platform != "win32":  # the test runs on POSIX alone
        os.kill(os.getpid(), signal.SIGKILL)  # as the kernel ends a process out of memory
    raise AssertionError("not killed")


def beat_once(beat: Path, count: int) -> None:
    """The count, whole: a reader never finds the file emptied for the writing."""
    part = beat.with_suffix(".part")
    part.write_text(str(count), encoding="ascii")
    os.replace(part, beat)


def working(path: Path, engine: str, max_pages: int) -> Conversion:
    """Counts into ``<path>.beat`` until it is stopped."""
    beat = path.with_suffix(".beat")
    count = 0
    while True:
        count += 1
        beat_once(beat, count)
        time.sleep(0.05)


def spawning(path: Path, engine: str, max_pages: int) -> Conversion:
    """Starts a grandchild that counts into ``<path>.beat``, then waits."""
    beat = path.with_suffix(".beat")
    script = (
        "import os, pathlib, sys, time\n"
        "beat = pathlib.Path(sys.argv[1])\n"
        "count = 0\n"
        "while True:\n"
        "    count += 1\n"
        "    beat.with_suffix('.part').write_text(str(count))\n"
        "    os.replace(beat.with_suffix('.part'), beat)\n"
        "    time.sleep(0.05)\n"
    )
    subprocess.Popen([sys.executable, "-c", script, str(beat)])  # noqa: S603 - the test's own script
    while True:
        time.sleep(1)


def inspecting(path: Path, engine: str, max_pages: int) -> Conversion:
    """Says its process group and its OOM score in the text of its block (Linux alone)."""
    if sys.platform == "win32":
        raise AssertionError("a test of Linux")
    score = Path("/proc/self/oom_score_adj").read_text(encoding="ascii").strip()
    found = reading(path, engine, max_pages)
    text = f"group={os.getpgid(0)} pid={os.getpid()} oom={score}"
    return found.model_copy(update={"blocks": (found.blocks[0].model_copy(update={"text": text}),)})
