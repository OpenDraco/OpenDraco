"""Cross-cutting endpoints (health probe and any future server-wide
routes that don't belong to a single page)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
