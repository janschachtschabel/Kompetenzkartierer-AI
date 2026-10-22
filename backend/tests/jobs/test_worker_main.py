"""``python -m app.jobs.worker`` as the deployment starts it: it comes up, says what it takes, and
stops cleanly on SIGTERM."""

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.migrate import migrate
from tests.support import without_settings_variables

pytestmark = pytest.mark.pg

BACKEND = Path(__file__).resolve().parents[2]
START_S = 30.0


def start_worker(database_url: str) -> subprocess.Popen[str]:
    with without_settings_variables():
        environment = {**os.environ}
    environment.update(DATABASE_URL=database_url, JOB_POLL_S="0.1", PYTHONUNBUFFERED="1")
    return subprocess.Popen(
        [sys.executable, "-m", "app.jobs.worker"],
        cwd=BACKEND,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def lines_of(process: subprocess.Popen[str]) -> Iterator[str]:
    """The process's output line by line, given up after START_S."""
    found: queue.Queue[str | None] = queue.Queue()

    def read() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            found.put(line)
        found.put(None)

    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + START_S
    while (left := deadline - time.monotonic()) > 0:
        try:
            line = found.get(timeout=left)
        except queue.Empty:
            return
        if line is None:
            return
        yield line


def wait_until_it_takes(process: subprocess.Popen[str]) -> list[str]:
    seen = []
    for line in lines_of(process):
        seen.append(line)
        if " takes " in line:
            return seen
    raise AssertionError(f"the worker did not start: {''.join(seen)[-2000:]}")


def test_the_worker_process_comes_up_and_says_what_it_takes(database_url: str) -> None:
    migrate(database_url)
    process = start_worker(database_url)
    try:
        seen = wait_until_it_takes(process)
    finally:
        process.kill()
        process.wait(10)

    assert any("no job handlers are registered" in line for line in seen)


@pytest.mark.skipif(os.name != "posix", reason="SIGTERM ends a Windows process without a word")
def test_sigterm_stops_the_worker_cleanly(database_url: str) -> None:
    migrate(database_url)
    process = start_worker(database_url)
    try:
        wait_until_it_takes(process)
        process.send_signal(signal.SIGTERM)
        code = process.wait(10)
    finally:
        process.kill()

    assert code == 0
