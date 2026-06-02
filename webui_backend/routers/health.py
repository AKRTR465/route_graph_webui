from __future__ import annotations

from fastapi import APIRouter

from webui_backend.models import HealthResponse
from webui_backend.services import api_service


router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return await api_service.health()


@router.get("/api/ping")
async def ping() -> dict[str, str]:
    return await api_service.ping()
