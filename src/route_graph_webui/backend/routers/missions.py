from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from route_graph_webui.backend.models import ExportMissionsRequest, PreviewMissionRequest
from route_graph_webui.backend.services import api_service


router = APIRouter(tags=["missions"])


@router.post("/api/missions/preview")
async def preview_mission(request: PreviewMissionRequest) -> dict[str, Any]:
    return await api_service.preview_mission(request)


@router.post("/api/missions/export")
async def export_missions(request: ExportMissionsRequest) -> dict[str, Any]:
    return await api_service.export_missions(request)
