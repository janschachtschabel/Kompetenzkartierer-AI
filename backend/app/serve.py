"""Start of the API: one uvicorn process that listens on the public and the internal port.

The cluster scales by replicas, not by worker processes; heavy work runs in the job worker.
One process keeps the Prometheus values in memory, without a multiprocess collector.

uvicorn parses with h11: httptools bounds neither the URL nor the headers, and uvicorn put a
long URL together piece by piece in quadratic time (compendious audit SE-19). h11 answers 400
to a request head over 16 KB.
"""

import contextlib
import socket

import uvicorn
from fastapi import FastAPI
from uvicorn.config import STARTUP_FAILURE

from app.api.app import create_app
from app.core.settings import Settings


def build_server(settings: Settings) -> tuple[uvicorn.Server, list[socket.socket]]:
    """The server and its two bound sockets, public first; ``server.run(sockets=...)`` serves them."""
    app = create_app(settings)
    public = _config(app, settings, settings.public_port)
    internal = _config(app, settings, settings.internal_port)
    # uvicorn's own binding for both: IPv6 hosts, SO_REUSEADDR, a port in use ends the start
    return uvicorn.Server(public), [public.bind_socket(), internal.bind_socket()]


def _config(app: FastAPI, settings: Settings, port: int) -> uvicorn.Config:
    return uvicorn.Config(
        app, host=settings.host, port=port, http="h11", access_log=False, root_path=settings.root_path
    )


def main() -> None:
    server, sockets = build_server(Settings())
    # as uvicorn.main.run: Ctrl+C ends without a traceback
    with contextlib.suppress(KeyboardInterrupt):
        server.run(sockets=sockets)
    if not server.started:
        raise SystemExit(STARTUP_FAILURE)


if __name__ == "__main__":
    main()
