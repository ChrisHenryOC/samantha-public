"""Static file serving for the web frontend."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/")
async def index() -> FileResponse:
    """Serve the main frontend page."""
    return FileResponse(_STATIC_DIR / "index.html")
