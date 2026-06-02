from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from webui_backend.models import ScopedGraphRequest, UpdateCanvasViewRequest, UpdateGraphUiStateRequest
from webui_backend.services import api_service


router = APIRouter(tags=["ui-state"])


@router.post("/api/app/last-graph")
async def update_last_graph(request: ScopedGraphRequest) -> dict[str, Any]:
    return await api_service.update_last_graph(request)


@router.post("/api/graph/canvas-view")
async def update_canvas_view(request: UpdateCanvasViewRequest) -> dict[str, Any]:
    return await api_service.update_canvas_view(request)


@router.post("/api/graph/ui-state")
async def update_graph_ui_state(request: UpdateGraphUiStateRequest) -> dict[str, Any]:
    return await api_service.update_graph_ui_state(request)
