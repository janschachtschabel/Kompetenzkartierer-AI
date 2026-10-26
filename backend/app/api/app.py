"""The ASGI application: routers and middlewares, built from the settings."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import (
    accounts,
    conversions,
    document_findings,
    document_tree,
    documents,
    internal,
    jobs,
    node_editing,
    profiles,
    source_checks,
    source_register,
    sources,
    statement_editing,
    system,
    usage,
)
from app.api.body_limit import JSON_BODY_LIMIT, MIB, BodyLimit
from app.api.errors import ERROR_RESPONSES, install_error_handlers
from app.api.request_log import RequestLog
from app.api.security_headers import SecurityHeaders
from app.core.settings import Settings
from app.core.storage import open_storage
from app.core.storage_async import AsyncStorage
from app.db.migrate import load_migrations
from app.db.pool import create_pool

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
    {"name": "accounts", "description": "Accounts, roles and API tokens; managed by admins."},
    {"name": "usage", "description": "What an account may spend on the language model, and has spent."},
    {"name": "jobs", "description": "Fetching, converting, extracting run as jobs: their state, a cancel."},
    {"name": "sources", "description": "The register of curriculum documents: uploads and their files."},
    {"name": "conversions", "description": "A register file converted into named blocks (X0), page by page."},
    {"name": "documents", "description": "Documents of a conversion and their extraction, one at a time."},
    {"name": "profiles", "description": "A sector's profile as the editor offers it: its form and values."},
]


def create_app(settings: Settings) -> FastAPI:
    if settings.api_key_pepper is None:
        raise ValueError("API_KEY_PEPPER is required for the API: API keys are checked against it")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Without its store the API does not start (StorageNotConfigured names the setting): an
        # upload failing later would cost the caller the file. Opening may ask the service
        # (S3's head_bucket), so it runs in a thread
        app.state.storage = AsyncStorage(await asyncio.to_thread(open_storage, settings))
        # Opened without waiting: the process starts and answers /health while the database
        # is away; /ready says so
        pool = create_pool(settings)
        await pool.open(wait=False)
        app.state.pool = pool
        try:
            yield
        finally:
            await pool.close()

    app = FastAPI(
        lifespan=lifespan,
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
    app.state.settings = settings
    app.state.expected_migrations = frozenset(migration.version for migration in load_migrations())
    install_error_handlers(app)
    app.include_router(internal.router)
    app.include_router(system.router)
    app.include_router(accounts.router)
    app.include_router(usage.router)
    app.include_router(jobs.router)
    app.include_router(sources.router)
    app.include_router(source_register.router)
    app.include_router(source_checks.router)
    app.include_router(conversions.router)
    app.include_router(documents.router)
    app.include_router(document_findings.router)
    app.include_router(document_tree.router)
    app.include_router(node_editing.router)
    app.include_router(statement_editing.router)
    app.include_router(profiles.router)
    app.add_middleware(internal.InternalOnly, port=settings.internal_port)
    # an upload takes a file and the form around it; every other body is JSON
    upload_limit = (settings.max_upload_mb + 1) * MIB
    app.add_middleware(
        BodyLimit, default=JSON_BODY_LIMIT, limits={("POST", sources.UPLOAD_PATH): upload_limit}
    )
    # Added after InternalOnly, so it runs before: every answer, the refused internal ones too, is
    # named and logged
    app.add_middleware(RequestLog, routes=app.routes)
    # Added last, so it runs first: the 500 the request log answers itself carries the headers too
    app.add_middleware(SecurityHeaders)
    return app
