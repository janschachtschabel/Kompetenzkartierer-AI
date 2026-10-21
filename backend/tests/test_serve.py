"""One uvicorn process answers on two real sockets: the public port and the internal one."""

import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

from app.core.settings import Settings
from app.serve import build_server

START_TIMEOUT_S = 10.0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def status_of(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - fixed local URL
            status: int = response.status
            return status
    except urllib.error.HTTPError as error:
        return error.code


@pytest.fixture
def running() -> Iterator[Settings]:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://kka:fake@localhost/kka",
            "host": "127.0.0.1",
            "public_port": free_port(),
            "internal_port": free_port(),
            "root_path": "/kka",
        }
    )
    server, sockets = build_server(settings)
    thread = threading.Thread(target=server.run, kwargs={"sockets": sockets}, daemon=True)
    thread.start()
    deadline = time.monotonic() + START_TIMEOUT_S
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    yield settings
    server.should_exit = True
    thread.join(timeout=START_TIMEOUT_S)


def test_both_sockets_answer_and_only_the_internal_one_has_health(running: Settings) -> None:
    public = f"http://127.0.0.1:{running.public_port}"
    internal = f"http://127.0.0.1:{running.internal_port}"

    assert status_of(f"{internal}/health") == 200
    assert status_of(f"{public}/health") == 404
    assert status_of(f"{public}/openapi.json") == 200
