from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import subprocess
import sys
import types

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webui_backend.routers import (
    graphs_router,
    health_router,
    jobs_router,
    missions_router,
    plans_router,
    ui_state_router,
)
from webui_backend.services import api_service


DATA_ROOT = api_service.DATA_ROOT
FRONTEND_DIST_ROOT = api_service.FRONTEND_DIST_ROOT
GRAPH_ROOT = api_service.GRAPH_ROOT
PROGRESS_ROOT = api_service.PROGRESS_ROOT
WEBUI_APP_STATE_PATH = api_service.WEBUI_APP_STATE_PATH
DEFAULT_GRAPH_CANDIDATES = api_service.DEFAULT_GRAPH_CANDIDATES
WEBUI_VERSION = api_service.WEBUI_VERSION
AUTO_PLAN_JOB_RETENTION_SECONDS = api_service.AUTO_PLAN_JOB_RETENTION_SECONDS
AUTO_PLAN_WORKER_PATH = api_service.AUTO_PLAN_WORKER_PATH
DEFAULT_CORS_ALLOW_ORIGINS = api_service.DEFAULT_CORS_ALLOW_ORIGINS
LAN_ACCESS_ENV_VAR = api_service.LAN_ACCESS_ENV_VAR
CORS_ORIGINS_ENV_VAR = api_service.CORS_ORIGINS_ENV_VAR
auto_plan_job_service = api_service.auto_plan_job_service
_AUTO_PLAN_JOB_LOCK = api_service._AUTO_PLAN_JOB_LOCK
_AUTO_PLAN_JOBS = api_service._AUTO_PLAN_JOBS
_cleanup_auto_plan_runtime = api_service._cleanup_auto_plan_runtime
_ensure_server_directories = api_service._ensure_server_directories
_project_relative_path = api_service._project_relative_path
_resolve_cors_allow_origins = api_service._resolve_cors_allow_origins
_resolve_mission_output_dir = api_service._resolve_mission_output_dir
export_candidate_missions = api_service.export_candidate_missions


_PROXIED_SERVICE_ATTRS = {
    "DATA_ROOT",
    "AUTO_PLAN_JOB_RETENTION_SECONDS",
    "AUTO_PLAN_WORKER_PATH",
    "DEFAULT_GRAPH_CANDIDATES",
    "FRONTEND_DIST_ROOT",
    "GRAPH_ROOT",
    "PROGRESS_ROOT",
    "WEBUI_VERSION",
    "WEBUI_APP_STATE_PATH",
    "_project_relative_path",
    "_resolve_mission_output_dir",
    "export_candidate_missions",
}


class _ServerModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name in _PROXIED_SERVICE_ATTRS:
            setattr(api_service, name, value)


sys.modules[__name__].__class__ = _ServerModule


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    api_service._ensure_server_directories()
    yield


app = FastAPI(title="Route Graph WebUI API", lifespan=_app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(graphs_router)
app.include_router(plans_router)
app.include_router(jobs_router)
app.include_router(missions_router)
app.include_router(ui_state_router)


@app.get("/", include_in_schema=False)
async def serve_frontend_root() -> FileResponse:
    return api_service._serve_frontend_index()


@app.get("/{requested_path:path}", include_in_schema=False)
async def serve_frontend_path(requested_path: str) -> FileResponse:
    normalized_path = str(requested_path or "").lstrip("/")
    if not normalized_path:
        return api_service._serve_frontend_index()
    if normalized_path == "api" or normalized_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    asset_path = api_service._resolve_frontend_asset_path(normalized_path)
    if asset_path is not None:
        return FileResponse(asset_path)

    return api_service._serve_frontend_index()
