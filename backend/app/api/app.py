"""The ASGI application: routers and middlewares, built from the settings."""

from fastapi import FastAPI

from app import __version__
from app.api import internal
from app.core.settings import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Kompetenzkartierer-AI", version=__version__)
    app.include_router(internal.router)
    app.add_middleware(internal.InternalOnly, port=settings.internal_port)
    return app
