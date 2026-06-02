from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from webui_backend.models import GenerateAutoPlanRequest, GeneratePlanRequest, SaveCandidateSetRequest
from webui_backend.services import api_service


router = APIRouter(tags=["plans"])


@router.post("/api/plan")
async def plan_routes(request: GeneratePlanRequest) -> dict[str, Any]:
    return await api_service.plan_routes(request)


@router.post("/api/plan/auto")
async def auto_plan(request: GenerateAutoPlanRequest) -> dict[str, Any]:
    return await api_service.auto_plan(request)


@router.post("/api/candidate-set/save")
async def save_candidate_routes(request: SaveCandidateSetRequest) -> dict[str, Any]:
    return await api_service.save_candidate_routes(request)
