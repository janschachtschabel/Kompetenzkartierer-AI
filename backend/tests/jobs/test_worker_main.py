"""``python -m app.jobs.worker`` as the deployment starts it: it comes up, says what it takes, and
stops cleanly on SIGTERM; without its store, or told a kind it has no handler for, it does not."""

import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.migrate import migrate
from tests.support import throwaway_store, without_settings_variables

pytestmark = pytest.mark.pg

BACKEND = Path(__file__).resolve().parents[2]
START_S = 30.0


def start_worker(database_url: str, **settings: str) -> subprocess.Popen[str]:
    """The worker process with these settings; a throwaway store unless ``settings`` say otherwise."""
    with without_settings_variables():
        environment = {**os.environ}
    environment.update(
        DATABASE_URL=database_url, JOB_POLL_S="0.1", PYTHONUNBUFFERED="1", STORAGE_DIR=str(throwaway_store())
    )
    environment.update(settings)
    for name in [name for name, value in settings.items() if value == ""]:
        del environment[name]
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


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def test_the_running_worker_answers_its_liveness_probe_on_the_internal_port(database_url: str) -> None:
    migrate(database_url)
    port = free_port()
    process = start_worker(database_url, INTERNAL_PORT=str(port))
    try:
        wait_until_it_takes(process)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as answer:
            status = answer.status
    finally:
        process.kill()
        process.wait(10)

    assert status == 200


def ended_with(process: subprocess.Popen[str]) -> tuple[int, str]:
    output, _ = process.communicate(timeout=START_S)
    return process.returncode, output


def test_without_its_store_the_worker_does_not_start(database_url: str) -> None:
    # its jobs read and write objects; failing at the first job would cost an attempt each
    code, output = ended_with(start_worker(database_url, STORAGE_DIR=""))

    assert code == 1
    assert "STORAGE_DIR" in output


def test_a_kind_without_a_handler_stops_the_worker(database_url: str) -> None:
    code, output = ended_with(start_worker(database_url, WORKER_KINDS="test.nothing"))

    assert code == 1
    assert "test.nothing" in output
