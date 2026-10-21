"""The ASGI application: routers and middlewares, built from the settings."""

from fastapi import FastAPI

from app import __version__
from app.api import internal, system
from app.api.errors import ERROR_RESPONSES, install_error_handlers
from app.api.request_log import RequestLog
from app.core.settings import Settings

SUMMARY = "Curricula captured after Curriculum-Kern 1.0, docked to competence and level schemes, linked."
DESCRIPTION = """\
Curricula of every education sector - school, early childhood, vocational, higher and adult
education - are extracted from documents or entered in forms, following the Curriculum-Kern 1.0
ontology. Their parts are docked to competence dimensions, level systems and authority files,
and linked into a knowledge map.

Probes and metrics (`/health`, `/ready`, `/metrics`) answer on the internal port only and are
not part of this specification.
"""
# Every tag an operation uses is declared here with a description (tests/api/test_openapi.py)
TAGS = [
    {"name": "system", "description": "Facts about the running service."},
]


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title=system.SERVICE_NAME,
        summary=SUMMARY,
        description=DESCRIPTION,
        version=__version__,
        openapi_tags=TAGS,
        responses=ERROR_RESPONSES,
        # FastAPI's /docs and /redoc load scripts, styles and fonts from third-party hosts into
        # the visitor's browser; the spec stays at /openapi.json
        docs_url=None,
        redoc_url=None,
    )
    install_error_handlers(app)
    app.include_router(internal.router)
    app.include_router(system.router)
    app.add_middleware(internal.InternalOnly, port=settings.internal_port)
    # Added last, so it runs first: every answer, the refused internal ones too, is named and logged
    app.add_middleware(RequestLog, routes=app.routes)
    return app
