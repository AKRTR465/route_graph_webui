from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from route_graph_webui.backend.models import (
    AddEdgeRequest,
    NodeMoveRequest,
    NodeUpdateRequest,
    RemoveEdgeBetweenRequest,
    RemoveEdgeRequest,
    UpdateEdgeRequest,
    UpdateGraphGroupConfigRequest,
)
from route_graph_webui.backend.services import api_service


router = APIRouter(tags=["graphs"])


@router.get("/api/graphs")
async def list_graphs() -> dict[str, Any]:
    return await api_service.list_graphs()


@router.get("/api/graph")
async def get_graph(graph: str | None = Query(default=None)) -> dict[str, Any]:
    return await api_service.get_graph(graph)


@router.get("/api/graph/validate")
async def validate_current_graph(graph: str | None = Query(default=None)) -> dict[str, Any]:
    return await api_service.validate_current_graph(graph)


@router.post("/api/node/move")
async def move_node(request: NodeMoveRequest) -> dict[str, Any]:
    return await api_service.move_node(request)


@router.post("/api/node/update")
async def update_node(request: NodeUpdateRequest) -> dict[str, Any]:
    return await api_service.update_node(request)


@router.post("/api/edge/add")
async def add_edge(request: AddEdgeRequest) -> dict[str, Any]:
    return await api_service.add_edge(request)


@router.post("/api/edge/update")
async def update_edge(request: UpdateEdgeRequest) -> dict[str, Any]:
    return await api_service.update_edge(request)


@router.post("/api/edge/remove")
async def remove_edge(request: RemoveEdgeRequest) -> dict[str, Any]:
    return await api_service.remove_edge(request)


@router.post("/api/edge/remove-between")
async def remove_edge_between(request: RemoveEdgeBetweenRequest) -> dict[str, Any]:
    return await api_service.remove_edge_between(request)


@router.post("/api/graph/group-config")
async def update_graph_group_config(request: UpdateGraphGroupConfigRequest) -> dict[str, Any]:
    return await api_service.update_graph_group_config(request)
