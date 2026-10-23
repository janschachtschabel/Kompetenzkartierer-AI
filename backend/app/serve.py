"""Start of the API: one uvicorn process that listens on the public and the internal port.

The cluster scales by replicas, not by worker processes; heavy work runs in the job worker.
One process keeps the Prometheus values in memory, without a multiprocess collector.

uvicorn parses with h11: httptools bounds neither the URL nor the headers, and uvicorn put a
long URL together piece by piece in quadratic time (compendious audit SE-19). h11 bounds the
part of a request head it has to collect over several reads (16 KB); what one read brings, it
takes whole.
"""

import contextlib
import logging
import socket
import sys

import uvicorn
from fastapi import FastAPI
from uvicorn.config import STARTUP_FAILURE

from app.api.app import create_app
from app.core.logging import configure_logging
from app.core.settings import Settings
from app.llm.budget import TokenizerMissing
from app.llm.settings import LLMSettings
from app.llm.startup import check_model_layer

log = logging.getLogger("app.serve")  # also when run as __main__


def build_server(settings: Settings) -> tuple[uvicorn.Server, list[socket.socket]]:
    """The server and its two bound sockets, public first; ``server.run(sockets=...)`` serves them."""
    app = create_app(settings)
    public = _config(app, settings, settings.public_port)
    internal = _config(app, settings, settings.internal_port)
    # uvicorn's own binding for both: IPv6 hosts, SO_REUSEADDR, a port in use ends the start
    public_socket = public.bind_socket()
    try:
        internal_socket = internal.bind_socket()
    except BaseException:  # bind_socket ends the start with SystemExit
        public_socket.close()
        raise
    return uvicorn.Server(public), [public_socket, internal_socket]


def _config(app: FastAPI, settings: Settings, port: int) -> uvicorn.Config:
    # log_config=None: uvicorn's lines go through the service's handler (app.core.logging)
    return uvicorn.Config(
        app,
        host=settings.host,
        port=port,
        http="h11",
        access_log=False,
        root_path=settings.root_path,
        log_config=None,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        server_header=False,  # no need to tell the world which server stack answers
        # psycopg's async mode needs a selector loop; uvicorn's choice on Windows is the proactor
        loop="asyncio:SelectorEventLoop",
    )


def main() -> None:
    settings = Settings()
    llm = LLMSettings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stdout)
    try:
        check_model_layer(llm)
    except (ValueError, TokenizerMissing) as error:
        log.error("%s", error)
        raise SystemExit(STARTUP_FAILURE) from None
    server, sockets = build_server(settings)
    # as uvicorn.main.run: Ctrl+C ends without a traceback
    with contextlib.suppress(KeyboardInterrupt):
        server.run(sockets=sockets)
    if not server.started:
        raise SystemExit(STARTUP_FAILURE)


if __name__ == "__main__":
    main()
