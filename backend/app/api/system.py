"""Public facts about the running service."""

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

SERVICE_NAME = "Kompetenzkartierer-AI"

router = APIRouter(prefix="/api/v1", tags=["system"])


class Info(BaseModel):
    name: str
    version: str


@router.get("/info", summary="Name and version of the service")
async def info() -> Info:
    return Info(name=SERVICE_NAME, version=__version__)
