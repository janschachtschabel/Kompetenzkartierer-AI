"""Public facts about the running service."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__
from app.core.settings import Settings

SERVICE_NAME = "Kompetenzkartierer-AI"

router = APIRouter(prefix="/api/v1", tags=["system"])


class Info(BaseModel):
    name: str
    version: str
    # What a visitor without a token may do (PUBLIC_ACCESS): the start page offers that much
    public_access: Literal["off", "lookup", "search"]
    # MAX_UPLOAD_MB: the page checks a file against it before sending megabytes to a refusal
    max_upload_mb: int


@router.get("/info", summary="Name, version, what visitors may do and the upload limit")
async def info(request: Request) -> Info:
    settings: Settings = request.app.state.settings
    return Info(
        name=SERVICE_NAME,
        version=__version__,
        public_access=settings.public_access,
        max_upload_mb=settings.max_upload_mb,
    )
