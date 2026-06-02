from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from route_graph_webui.backend.models import GenerateAutoPlanRequest
from route_graph_webui.backend.services import api_service


router = APIRouter(tags=["jobs"])


@router.post("/api/plan/auto/jobs")
async def create_auto_plan_job(request: GenerateAutoPlanRequest) -> dict[str, Any]:
    return await api_service.create_auto_plan_job(request)


@router.get("/api/plan/auto/jobs/{job_id}")
async def get_auto_plan_job(job_id: int) -> dict[str, Any]:
    return await api_service.get_auto_plan_job(job_id)


@router.post("/api/plan/auto/jobs/{job_id}/cancel")
async def cancel_auto_plan_job(job_id: int) -> dict[str, Any]:
    return await api_service.cancel_auto_plan_job(job_id)
