from __future__ import annotations

from datetime import datetime
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from fastapi import HTTPException, Query
from fastapi.responses import FileResponse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph_editor import GraphEditor
from edge_intent_service import resolve_edge_creation_meta
from webui_backend.models import (
    AddEdgeRequest,
    ExportMissionsRequest,
    GenerateAutoPlanRequest,
    GeneratePlanRequest,
    HealthResponse,
    NodeMoveRequest,
    NodeUpdateRequest,
    PreviewMissionRequest,
    RemoveEdgeBetweenRequest,
    RemoveEdgeRequest,
    SaveCandidateSetRequest,
    ScopedGraphRequest,
    UpdateCanvasViewRequest,
    UpdateEdgeRequest,
    UpdateGraphGroupConfigRequest,
    UpdateGraphUiStateRequest,
)
from webui_backend.services.job_service import (
    BackgroundJobRecord as AutoPlanJobRecord,
    BackgroundJobService,
    serialize_job_status,
)
from webui_backend.services.mission_service import (
    build_mission_preview,
    export_candidate_missions,
)
from webui_backend.services.planning_service import (
    generate_auto_candidate_set,
    generate_manual_candidate_set,
)
from graph_store import (
    DATA_DIR,
    GRAPH_ROOT,
    MISSION_ROOT,
    PLAN_ROOT,
    PROGRESS_ROOT,
    PROJECT_ROOT,
    WEBUI_APP_STATE_PATH,
    ensure_data_directories,
    list_json_files,
    project_relative_path,
    relative_to_root,
    resolve_within_root,
)
from json_store import (
    consume_jsonl_text,
    read_json,
    read_json_mapping_if_ready,
    write_json_atomic,
)
from graph_canvas_view import sync_graph_gui_canvas_view
from graph_ui_state import (
    GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY,
    GRAPH_GUI_EXPORT_INPUTS_META_KEY,
    GRAPH_GUI_WEBUI_INPUTS_META_KEY,
    normalize_graph_gui_auto_plan_inputs,
    normalize_graph_gui_export_inputs,
    normalize_graph_gui_webui_inputs,
    read_graph_gui_auto_plan_inputs,
    read_graph_gui_export_inputs,
    read_graph_gui_webui_inputs,
    write_graph_gui_auto_plan_inputs,
    write_graph_gui_export_inputs,
    write_graph_gui_webui_inputs,
)
from graph_schema import (
    DEFAULT_GROUP_COLOR,
    EDGE_KIND_BRIDGE,
    EDGE_KIND_GROUP,
    GRAPH_BRIDGE_STYLE_META_KEY,
    GRAPH_GROUP_CONFIGS_META_KEY,
    GROUP_CONFIG_LABEL_KEY,
    GROUP_CONFIG_TEXT_KEYS,
    GraphSchemaError,
    RouteCandidateSet,
    RouteGraph,
    get_edge_group_color,
    get_edge_kind,
    normalize_hex_color,
    read_graph_bridge_style,
    read_graph_group_configs,
    resolve_bridge_color,
    save_candidate_set,
    save_graph,
    validate_graph,
    write_graph_bridge_style,
    write_graph_group_configs,
)
from route_planner import RoutePlanningError

DATA_ROOT = DATA_DIR
FRONTEND_DIST_ROOT = PROJECT_ROOT / "webui_frontend" / "dist"
DEFAULT_GRAPH_CANDIDATES = ("DowntownWest.json", "untitled_graph.json")
WEBUI_VERSION = "0.0.0"
AUTO_PLAN_JOB_RETENTION_SECONDS = 30 * 60
AUTO_PLAN_POST_EXIT_POLL_LIMIT = 5
AUTO_PLAN_WORKER_PATH = PROJECT_ROOT / "route_generation_worker.py"
AUTO_PLAN_RUNTIME_PREFIX = "route_graph_webui_auto_plan_"
DEFAULT_CORS_ALLOW_ORIGINS = ("http://127.0.0.1:8000", "http://127.0.0.1:5173")
LAN_ACCESS_ENV_VAR = "ROUTE_GRAPH_WEBUI_ALLOW_LAN"
CORS_ORIGINS_ENV_VAR = "ROUTE_GRAPH_WEBUI_CORS_ORIGINS"

GRAPH_KIND_GROUP = EDGE_KIND_GROUP
GRAPH_KIND_BRIDGE = EDGE_KIND_BRIDGE


def _env_flag_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_cors_allow_origins(env: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    raw_origins = source.get(CORS_ORIGINS_ENV_VAR)
    if raw_origins:
        origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        if origins:
            return origins
    if _env_flag_enabled(source.get(LAN_ACCESS_ENV_VAR)):
        return ["*"]
    return list(DEFAULT_CORS_ALLOW_ORIGINS)


def _ensure_server_directories() -> None:
    ensure_data_directories()
    GRAPH_ROOT.mkdir(parents=True, exist_ok=True)
    PLAN_ROOT.mkdir(parents=True, exist_ok=True)
    MISSION_ROOT.mkdir(parents=True, exist_ok=True)
    WEBUI_APP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    auto_plan_job_service.runtime_root = PROGRESS_ROOT
    auto_plan_job_service.cleanup_orphaned_runtimes()


auto_plan_job_service = BackgroundJobService(
    worker_path=AUTO_PLAN_WORKER_PATH,
    runtime_root=PROGRESS_ROOT,
    project_root=PROJECT_ROOT,
    runtime_prefix=AUTO_PLAN_RUNTIME_PREFIX,
    retention_seconds=AUTO_PLAN_JOB_RETENTION_SECONDS,
    post_exit_poll_limit=AUTO_PLAN_POST_EXIT_POLL_LIMIT,
)
_AUTO_PLAN_JOB_LOCK = auto_plan_job_service.lock
_AUTO_PLAN_JOBS = auto_plan_job_service.jobs


def _project_relative_path(path: Path) -> str:
    return project_relative_path(path, project_root=PROJECT_ROOT, data_root=DATA_ROOT)


def _health_display_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _graph_relative_path(path: Path) -> str:
    return relative_to_root(path, GRAPH_ROOT)


def _frontend_index_path() -> Path:
    return (FRONTEND_DIST_ROOT / "index.html").resolve()


def _resolve_frontend_asset_path(requested_path: str) -> Path | None:
    sanitized_path = str(requested_path).strip().lstrip("/")
    if not sanitized_path:
        return None

    try:
        candidate = (FRONTEND_DIST_ROOT / sanitized_path).resolve()
        candidate.relative_to(FRONTEND_DIST_ROOT.resolve())
    except ValueError:
        return None

    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _serve_frontend_index() -> FileResponse:
    index_path = _frontend_index_path()
    if not index_path.exists() or not index_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Frontend build was not found. Expected "
                f"`{index_path}`. Build or package `webui_frontend/dist` first."
            ),
        )
    return FileResponse(index_path)


def _resolve_within_root(
    root: Path,
    raw_path: str | None,
    *,
    default: Path | None = None,
    expect_json: bool = True,
) -> Path:
    try:
        return resolve_within_root(
            root,
            raw_path,
            default=default,
            expect_json=expect_json,
        )
    except ValueError as exc:
        raise GraphSchemaError(str(exc)) from exc


def _read_webui_app_state() -> dict[str, Any]:
    payload = read_json_mapping_if_ready(WEBUI_APP_STATE_PATH)
    if payload is None:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_webui_app_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    raw_graph = payload.get("last_graph")
    if isinstance(raw_graph, str) and raw_graph.strip():
        normalized["last_graph"] = raw_graph.strip()
    normalized["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json_atomic(WEBUI_APP_STATE_PATH, normalized, indent=None)
    return normalized


def _clear_webui_app_state() -> None:
    try:
        WEBUI_APP_STATE_PATH.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _resolve_saved_default_graph_path() -> Path | None:
    raw_last_graph = _read_webui_app_state().get("last_graph")
    if not isinstance(raw_last_graph, str) or not raw_last_graph.strip():
        return None
    try:
        candidate = _resolve_within_root(
            GRAPH_ROOT,
            raw_last_graph.strip(),
            expect_json=True,
        )
    except (GraphSchemaError, ValueError):
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        mapping, _ = _load_graph_mapping(candidate)
        RouteGraph.from_mapping(mapping)
    except Exception:
        return None
    return candidate


def _read_planner_ui_inputs(meta: Mapping[str, Any] | None) -> dict[str, str]:
    saved_webui = read_graph_gui_webui_inputs(meta)
    saved_auto = read_graph_gui_auto_plan_inputs(meta)
    planning_mode = saved_webui.get("planning_mode")
    if not planning_mode and isinstance(saved_auto.get("planning_mode"), str):
        planning_mode = str(saved_auto["planning_mode"])
    resolved = {
        "planning_mode": planning_mode or "manual",
        "max_routes": saved_webui.get("max_routes", ""),
        "max_edge_pass_factor": saved_webui.get("max_edge_pass_factor", ""),
        "min_total_length": saved_webui.get("min_total_length", ""),
        "max_total_length": saved_webui.get("max_total_length", ""),
        "min_frame_count": saved_webui.get("min_frame_count", ""),
        "max_frame_count": saved_webui.get("max_frame_count", ""),
    }
    return resolved


def _read_group_ui_inputs(meta: Mapping[str, Any] | None) -> dict[str, str]:
    saved_webui = read_graph_gui_webui_inputs(meta)
    resolved: dict[str, str] = {}
    if "active_group_color" in saved_webui:
        resolved["active_group_color"] = saved_webui.get("active_group_color", "")
    return resolved


def _read_export_ui_inputs(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    resolved = dict(read_graph_gui_export_inputs(meta))
    saved_webui = read_graph_gui_webui_inputs(meta)
    resolved["candidate_set_file_name"] = saved_webui.get("candidate_set_file_name", "")
    resolved["missions_output_dir"] = saved_webui.get("missions_output_dir", "")
    return resolved


def _serialize_group_editor_state(graph: RouteGraph) -> dict[str, Any]:
    used_group_colors = {
        get_edge_group_color(edge, default_color=DEFAULT_GROUP_COLOR) or DEFAULT_GROUP_COLOR
        for edge in graph.edges
        if get_edge_kind(edge) == GRAPH_KIND_GROUP
    }
    group_configs = {
        color: payload
        for color, payload in read_graph_group_configs(graph.meta).items()
        if color in used_group_colors
    }
    return {
        "bridge_color": resolve_bridge_color(graph.meta),
        "group_configs": group_configs,
    }


def _serialize_graph_ui_state(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "planner_inputs": _read_planner_ui_inputs(meta),
        "group_inputs": _read_group_ui_inputs(meta),
        "auto_plan_inputs": read_graph_gui_auto_plan_inputs(meta),
        "export_inputs": _read_export_ui_inputs(meta),
    }


def _merge_graph_ui_state(
    meta: dict[str, Any],
    *,
    planner_inputs: Mapping[str, Any] | None,
    group_inputs: Mapping[str, Any] | None,
    auto_plan_inputs: Mapping[str, Any] | None,
    export_inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized_planner = normalize_graph_gui_webui_inputs(planner_inputs or {})
    normalized_group = normalize_graph_gui_webui_inputs(group_inputs or {})
    normalized_auto = normalize_graph_gui_auto_plan_inputs(auto_plan_inputs or {})
    normalized_export = normalize_graph_gui_export_inputs(export_inputs or {})

    current_webui = read_graph_gui_webui_inputs(meta)
    current_auto = read_graph_gui_auto_plan_inputs(meta)
    current_export = read_graph_gui_export_inputs(meta)

    next_webui = dict(current_webui)
    next_webui.update(normalized_planner)
    next_webui.update(normalized_group)
    next_webui.update(
        normalize_graph_gui_webui_inputs(
            {
                "candidate_set_file_name": (export_inputs or {}).get("candidate_set_file_name"),
                "missions_output_dir": (export_inputs or {}).get("missions_output_dir"),
            }
        )
    )
    write_graph_gui_webui_inputs(meta, next_webui)

    next_auto = dict(current_auto)
    next_auto.update(normalized_auto)
    if "planning_mode" in normalized_planner:
        next_auto["planning_mode"] = normalized_planner["planning_mode"]
    write_graph_gui_auto_plan_inputs(meta, next_auto)

    next_export = dict(current_export)
    next_export.update(normalized_export)
    write_graph_gui_export_inputs(meta, next_export)

    return _serialize_graph_ui_state(meta)


def _clean_group_config_payload(payload: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        return {}
    cleaned: dict[str, str] = {}
    for key in (GROUP_CONFIG_LABEL_KEY, *GROUP_CONFIG_TEXT_KEYS):
        if key not in payload:
            continue
        raw_value = payload.get(key)
        cleaned[key] = "" if raw_value is None else str(raw_value)
    return cleaned


def _list_graph_paths() -> list[Path]:
    return list_json_files(GRAPH_ROOT)


def _default_graph_path() -> Path:
    graph_paths = _list_graph_paths()
    if not graph_paths:
        raise GraphSchemaError(f"No graph JSON files were found under `{GRAPH_ROOT}`")

    preferred_saved_graph = _resolve_saved_default_graph_path()
    if preferred_saved_graph is not None:
        return preferred_saved_graph

    lookup = {path.name: path for path in graph_paths}
    for file_name in DEFAULT_GRAPH_CANDIDATES:
        preferred = lookup.get(file_name)
        if preferred is not None:
            return preferred
    return graph_paths[0]


def _coerce_legacy_graph_mapping(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)

    if "graph_name" not in normalized and "id" in normalized:
        normalized["graph_name"] = str(normalized["id"])
    if "default_altitude" not in normalized:
        normalized["default_altitude"] = None
    if "meta" not in normalized or not isinstance(normalized.get("meta"), dict):
        normalized["meta"] = dict(normalized.get("meta") or {})

    normalized_nodes: list[dict[str, Any]] = []
    for raw_node in normalized.get("nodes", []):
        node = dict(raw_node)
        if "name" not in node:
            node["name"] = str(node.get("id", ""))
        if "yaw_hint" not in node:
            node["yaw_hint"] = None
        if "tags" not in node or node.get("tags") is None:
            node["tags"] = []
        if "meta" not in node or not isinstance(node.get("meta"), dict):
            node["meta"] = dict(node.get("meta") or {})
        normalized_nodes.append(node)
    normalized["nodes"] = normalized_nodes

    normalized_edges: list[dict[str, Any]] = []
    for raw_edge in normalized.get("edges", []):
        edge = dict(raw_edge)
        if "bidirectional" not in edge:
            edge["bidirectional"] = True
        if "meta" not in edge or not isinstance(edge.get("meta"), dict):
            edge["meta"] = dict(edge.get("meta") or {})
        normalized_edges.append(edge)
    normalized["edges"] = normalized_edges

    return normalized


def _load_graph_mapping(graph_path: Path) -> tuple[dict[str, Any], bool]:
    try:
        raw = read_json(graph_path)
    except FileNotFoundError as exc:
        raise GraphSchemaError(f"Graph not found: {graph_path}") from exc
    except ValueError as exc:
        raise GraphSchemaError(f"Graph JSON is invalid: {graph_path}") from exc

    if not isinstance(raw, dict):
        raise GraphSchemaError("Graph JSON root must be an object")

    legacy = "graph_name" not in raw and "id" in raw
    return (_coerce_legacy_graph_mapping(raw) if legacy else raw), legacy


def _load_graph(graph_ref: str | None) -> tuple[Path, RouteGraph, bool]:
    graph_path = _resolve_within_root(
        GRAPH_ROOT,
        graph_ref,
        default=_default_graph_path(),
        expect_json=True,
    )
    mapping, is_legacy = _load_graph_mapping(graph_path)
    return graph_path, RouteGraph.from_mapping(mapping), is_legacy


def _serialize_graph_summary(graph_path: Path, graph: RouteGraph, is_legacy: bool) -> dict[str, Any]:
    group_colors = sorted(
        {
            get_edge_group_color(edge, default_color=DEFAULT_GROUP_COLOR) or DEFAULT_GROUP_COLOR
            for edge in graph.edges
            if get_edge_kind(edge) == GRAPH_KIND_GROUP
        }
    )
    bridge_count = sum(1 for edge in graph.edges if get_edge_kind(edge) == GRAPH_KIND_BRIDGE)
    stat = graph_path.stat()

    return {
        "path": _graph_relative_path(graph_path),
        "file_name": graph_path.name,
        "graph_name": graph.graph_name,
        "env_id": graph.env_id,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "enabled_edge_count": sum(1 for edge in graph.edges if edge.enabled),
        "group_colors": group_colors,
        "bridge_count": bridge_count,
        "is_legacy": is_legacy,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _serialize_graph_payload(graph_path: Path, graph: RouteGraph, is_legacy: bool) -> dict[str, Any]:
    return {
        "path": _graph_relative_path(graph_path),
        "graph": graph.to_dict(),
        "summary": _serialize_graph_summary(graph_path, graph, is_legacy),
        "ui_state": _serialize_graph_ui_state(graph.meta),
        "group_editor_state": _serialize_group_editor_state(graph),
    }


def _serialize_validation_report(graph: RouteGraph) -> dict[str, Any]:
    report = validate_graph(graph)
    return {
        "is_valid": report.is_valid,
        "error_count": len(report.errors),
        "warning_count": len(report.warnings),
        "issues": [
            {
                "severity": issue.severity,
                "code": issue.code,
                "message": issue.message,
                "refs": list(issue.refs),
            }
            for issue in report.issues
        ],
    }


def _persist_graph(graph_path: Path, graph: RouteGraph) -> dict[str, Any]:
    save_graph(graph_path, graph)
    return _serialize_graph_payload(graph_path, graph, is_legacy=False)


def _resolve_candidate_set(request_payload: dict[str, Any]) -> RouteCandidateSet:
    try:
        return RouteCandidateSet.from_mapping(request_payload)
    except Exception as exc:
        raise GraphSchemaError("Candidate-set payload is invalid") from exc


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_plan_output_path(candidate_set: RouteCandidateSet, file_name: str | None) -> Path:
    default_name = f"{candidate_set.graph_name}_{_timestamp_slug()}.candidates.json"
    resolved = _resolve_within_root(
        PLAN_ROOT,
        file_name,
        default=PLAN_ROOT / default_name,
        expect_json=True,
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_mission_output_dir(candidate_set: RouteCandidateSet, output_dir: str | None) -> Path:
    default_dir = MISSION_ROOT / candidate_set.graph_name
    resolved = _resolve_within_root(
        MISSION_ROOT,
        output_dir,
        default=default_dir,
        expect_json=False,
    )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _consume_progress_messages(
    buffer: str,
    new_data: str,
) -> tuple[list[dict[str, Any]], str]:
    return consume_jsonl_text(buffer, new_data)


def _read_json_mapping_if_ready(path: str | Path) -> dict[str, Any] | None:
    return read_json_mapping_if_ready(path)


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds")


def _resolve_job_candidate_set(candidate_payload: dict[str, Any]) -> dict[str, Any]:
    return _resolve_candidate_set(candidate_payload).to_dict()


def _cleanup_auto_plan_runtime(record: AutoPlanJobRecord) -> None:
    auto_plan_job_service.cleanup_runtime(record)


def _next_auto_plan_job_id() -> int:
    return auto_plan_job_service.next_job_id()


def _serialize_auto_plan_job_status(record: AutoPlanJobRecord) -> dict[str, Any]:
    return serialize_job_status(record)


def _finish_auto_plan_job(
    record: AutoPlanJobRecord,
    *,
    state: str,
    candidate_set: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    auto_plan_job_service.finish_job(
        record,
        state=state,
        candidate_set=candidate_set,
        error=error,
    )


def _read_auto_plan_stderr(record: AutoPlanJobRecord) -> str:
    return auto_plan_job_service.read_stderr_summary(record)


def _update_auto_plan_job_locked(record: AutoPlanJobRecord) -> None:
    auto_plan_job_service.update_job_locked(
        record,
        resolve_candidate_set=_resolve_job_candidate_set,
    )


def _cleanup_expired_auto_plan_jobs() -> None:
    auto_plan_job_service.cleanup_expired_jobs(
        resolve_candidate_set=_resolve_job_candidate_set,
    )


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, (GraphSchemaError, RoutePlanningError, ValueError)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".healthcheck.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _worker_service_health(service: BackgroundJobService) -> dict[str, Any]:
    with service.lock:
        jobs_by_state: dict[str, int] = {}
        for record in service.jobs.values():
            jobs_by_state[record.state] = jobs_by_state.get(record.state, 0) + 1
        active_jobs = jobs_by_state.get("running", 0)

    return {
        "worker_path": _health_display_path(service.worker_path),
        "worker_exists": service.worker_path.exists() and service.worker_path.is_file(),
        "runtime_root": _health_display_path(service.runtime_root),
        "active_jobs": active_jobs,
        "jobs_by_state": jobs_by_state,
    }


async def health() -> HealthResponse:
    frontend_index = _frontend_index_path()
    dist_exists = FRONTEND_DIST_ROOT.exists() and FRONTEND_DIST_ROOT.is_dir()
    index_exists = frontend_index.exists() and frontend_index.is_file()
    data_writable = _is_writable_directory(DATA_ROOT)
    graph_count = len(list_json_files(GRAPH_ROOT))
    workers = {"auto_plan": _worker_service_health(auto_plan_job_service)}

    status = "ok"
    if not data_writable or not workers["auto_plan"]["worker_exists"]:
        status = "degraded"

    return HealthResponse(
        status=status,
        version=WEBUI_VERSION,
        frontend_dist={
            "path": _health_display_path(FRONTEND_DIST_ROOT),
            "exists": dist_exists,
            "index_exists": index_exists,
        },
        data_dir={
            "path": _health_display_path(DATA_ROOT),
            "writable": data_writable,
        },
        graphs={
            "root": _health_display_path(GRAPH_ROOT),
            "count": graph_count,
        },
        workers=workers,
    )


async def ping() -> dict[str, str]:
    return {"status": "ok"}


async def update_last_graph(request: ScopedGraphRequest) -> dict[str, Any]:
    try:
        if request.graph is None or not str(request.graph).strip():
            _clear_webui_app_state()
            return {"last_graph": None}

        graph_path, _, _ = _load_graph(request.graph)
        normalized_graph = _graph_relative_path(graph_path)
        state = _write_webui_app_state({"last_graph": normalized_graph})
        return {"last_graph": state.get("last_graph"), "updated_at": state.get("updated_at")}
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def list_graphs() -> dict[str, Any]:
    try:
        default_graph = _default_graph_path()
        graphs: list[dict[str, Any]] = []
        for graph_path in _list_graph_paths():
            try:
                _, graph, is_legacy = _load_graph(_graph_relative_path(graph_path))
            except Exception as exc:
                graphs.append(
                    {
                        "path": _graph_relative_path(graph_path),
                        "file_name": graph_path.name,
                        "graph_name": graph_path.stem,
                        "load_error": str(exc),
                    }
                )
                continue
            graphs.append(_serialize_graph_summary(graph_path, graph, is_legacy))

        return {
            "default_graph": _graph_relative_path(default_graph),
            "graphs": graphs,
        }
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def get_graph(graph: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, is_legacy = _load_graph(graph)
        return _serialize_graph_payload(graph_path, loaded_graph, is_legacy)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def validate_current_graph(graph: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        _, loaded_graph, _ = _load_graph(graph)
        return _serialize_validation_report(loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def plan_routes(request: GeneratePlanRequest) -> dict[str, Any]:
    try:
        _, loaded_graph, _ = _load_graph(request.graph)
        candidate_set = generate_manual_candidate_set(
            loaded_graph,
            start_node=request.start_node,
            end_node=request.end_node,
            via_nodes=request.via_nodes,
            max_routes=request.max_routes,
            max_edge_pass_factor=request.max_edge_pass_factor,
            min_total_length=request.min_total_length,
            max_total_length=request.max_total_length,
            min_frame_count=request.min_frame_count,
            max_frame_count=request.max_frame_count,
            export_config=request.export_config,
        )
        return candidate_set.to_dict()
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def auto_plan(request: GenerateAutoPlanRequest) -> dict[str, Any]:
    try:
        _, loaded_graph, _ = _load_graph(request.graph)
        config = request.model_dump(exclude={"graph"}, exclude_none=True)
        candidate_set = generate_auto_candidate_set(
            loaded_graph,
            config=config,
        )
        return candidate_set.to_dict()
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def create_auto_plan_job(request: GenerateAutoPlanRequest) -> dict[str, Any]:
    try:
        _cleanup_expired_auto_plan_jobs()
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        graph_ref = _graph_relative_path(graph_path)
        job_config = request.model_dump(exclude={"graph"}, exclude_none=True)
        auto_plan_job_service.worker_path = AUTO_PLAN_WORKER_PATH
        auto_plan_job_service.runtime_root = PROGRESS_ROOT
        auto_plan_job_service.project_root = PROJECT_ROOT
        auto_plan_job_service.runtime_prefix = AUTO_PLAN_RUNTIME_PREFIX
        record = auto_plan_job_service.create_worker_job(
            graph_ref=graph_ref,
            task_payload={
                "graph": loaded_graph.to_dict(),
                "planning_mode": "auto",
                "auto_config": job_config,
            },
            popen_factory=subprocess.Popen,
            python_executable=sys.executable,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _serialize_auto_plan_job_status(record)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def get_auto_plan_job(job_id: int) -> dict[str, Any]:
    _cleanup_expired_auto_plan_jobs()
    expired_record: AutoPlanJobRecord | None = None
    try:
        try:
            with _AUTO_PLAN_JOB_LOCK:
                record = _AUTO_PLAN_JOBS.get(job_id)
                if record is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Auto planning job `{job_id}` was not found",
                    )

                _update_auto_plan_job_locked(record)

                if (
                    record.finished_at is not None
                    and (datetime.now() - record.finished_at).total_seconds() >= AUTO_PLAN_JOB_RETENTION_SECONDS
                ):
                    expired_record = _AUTO_PLAN_JOBS.pop(job_id)
                else:
                    return _serialize_auto_plan_job_status(record)
        finally:
            if expired_record is not None:
                _cleanup_auto_plan_runtime(expired_record)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)
        return {}

    raise HTTPException(
        status_code=404,
        detail=f"Auto planning job `{job_id}` was not found",
    )


async def cancel_auto_plan_job(job_id: int) -> dict[str, Any]:
    _cleanup_expired_auto_plan_jobs()
    status, expired_record = auto_plan_job_service.cancel_job(
        job_id,
        resolve_candidate_set=_resolve_job_candidate_set,
    )
    if expired_record is not None:
        _cleanup_auto_plan_runtime(expired_record)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Auto planning job `{job_id}` was not found",
        )
    return status


async def move_node(request: NodeMoveRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        editor = GraphEditor(loaded_graph)
        editor.update_node_xy(request.node_id, request.x, request.y)
        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def update_node(request: NodeUpdateRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        editor = GraphEditor(loaded_graph)

        if "name" in request.model_fields_set:
            editor.rename_node(request.node_id, request.name or "")
        if "tags" in request.model_fields_set:
            editor.update_node_tags(request.node_id, request.tags or [])
        if "yaw_hint" in request.model_fields_set:
            node = loaded_graph.get_node(request.node_id)
            node.yaw_hint = None if request.yaw_hint is None else float(request.yaw_hint)
        if "sample_radius" in request.model_fields_set:
            editor.update_node_sample_radius(request.node_id, request.sample_radius)

        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def add_edge(request: AddEdgeRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        editor = GraphEditor(loaded_graph)
        edge_meta = resolve_edge_creation_meta(
            loaded_graph,
            from_node=request.from_node,
            to_node=request.to_node,
            edge_kind=request.edge_kind,
            group_color=request.group_color,
        )
        editor.add_edge(
            request.from_node,
            request.to_node,
            bidirectional=request.bidirectional,
            meta=edge_meta,
        )
        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def update_edge(request: UpdateEdgeRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        edge = loaded_graph.get_edge(request.edge_id)
        if "enabled" in request.model_fields_set and request.enabled is not None:
            edge.enabled = bool(request.enabled)
        if "bidirectional" in request.model_fields_set and request.bidirectional is not None:
            edge.bidirectional = bool(request.bidirectional)
        if "edge_kind" in request.model_fields_set:
            if request.edge_kind == GRAPH_KIND_BRIDGE:
                edge.meta["edge_kind"] = GRAPH_KIND_BRIDGE
                edge.meta.pop("group_color", None)
            elif request.edge_kind == GRAPH_KIND_GROUP:
                edge.meta["edge_kind"] = GRAPH_KIND_GROUP
                if request.group_color is None or not str(request.group_color).strip():
                    raise GraphSchemaError("组内边需要提供颜色组颜色")
                edge.meta["group_color"] = normalize_hex_color(
                    request.group_color,
                    field_name="group color",
                )
        elif "group_color" in request.model_fields_set and request.group_color is not None:
            edge.meta["edge_kind"] = GRAPH_KIND_GROUP
            edge.meta["group_color"] = normalize_hex_color(
                request.group_color,
                field_name="group color",
            )
        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def remove_edge(request: RemoveEdgeRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        editor = GraphEditor(loaded_graph)
        editor.remove_edge(request.edge_id)
        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def remove_edge_between(request: RemoveEdgeBetweenRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        editor = GraphEditor(loaded_graph)
        editor.remove_edge_between(request.from_node, request.to_node)
        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def update_canvas_view(request: UpdateCanvasViewRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        sync_graph_gui_canvas_view(
            loaded_graph.meta,
            {
                "rotation_quadrants": request.rotation_quadrants,
                "flip_horizontal": request.flip_horizontal,
                "flip_vertical": request.flip_vertical,
            },
        )
        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def update_graph_ui_state(request: UpdateGraphUiStateRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        ui_state = _merge_graph_ui_state(
            loaded_graph.meta,
            planner_inputs=request.planner_inputs,
            group_inputs=request.group_inputs,
            auto_plan_inputs=request.auto_plan_inputs,
            export_inputs=request.export_inputs,
        )
        save_graph(graph_path, loaded_graph)
        return {
            "graph": _graph_relative_path(graph_path),
            "ui_state": ui_state,
        }
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def update_graph_group_config(request: UpdateGraphGroupConfigRequest) -> dict[str, Any]:
    try:
        graph_path, loaded_graph, _ = _load_graph(request.graph)
        if "group_color" in request.model_fields_set and request.group_color is not None:
            normalized_group_color = normalize_hex_color(
                request.group_color,
                field_name="group color",
            )
            configs = read_graph_group_configs(loaded_graph.meta)
            configs[normalized_group_color] = {
                **configs.get(normalized_group_color, {}),
                **_clean_group_config_payload(request.group_config),
            }
            write_graph_group_configs(loaded_graph.meta, configs)

        if "bridge_color" in request.model_fields_set:
            write_graph_bridge_style(
                loaded_graph.meta,
                {"color": request.bridge_color},
            )

        return _persist_graph(graph_path, loaded_graph)
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def save_candidate_routes(request: SaveCandidateSetRequest) -> dict[str, Any]:
    try:
        candidate_set = _resolve_candidate_set(request.candidate_set)
        output_path = _resolve_plan_output_path(candidate_set, request.file_name)
        save_candidate_set(output_path, candidate_set)
        return {
            "path": _project_relative_path(output_path),
            "graph_name": candidate_set.graph_name,
            "candidate_count": len(candidate_set.candidates),
            "selected_candidate_ids": list(candidate_set.selected_candidate_ids),
        }
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def preview_mission(request: PreviewMissionRequest) -> dict[str, Any]:
    try:
        candidate_set = _resolve_candidate_set(request.candidate_set)
        mission = build_mission_preview(
            candidate_set,
            candidate_id=request.candidate_id,
            export_config=request.model_dump(exclude={"candidate_set", "candidate_id"}),
        )
        return {
            "candidate_id": request.candidate_id,
            "mission": mission,
        }
    except Exception as exc:
        _raise_http_error(exc)
        return {}


async def export_missions(request: ExportMissionsRequest) -> dict[str, Any]:
    try:
        candidate_set = _resolve_candidate_set(request.candidate_set)
        output_dir = _resolve_mission_output_dir(candidate_set, request.output_dir)
        summary = export_candidate_missions(
            candidate_set,
            output_dir,
            candidate_ids=request.candidate_ids or None,
            export_config=request.model_dump(
                exclude={"candidate_set", "output_dir", "candidate_ids", "candidate_id"}
            ),
        )

        return {
            **summary,
            "output_dir": _project_relative_path(output_dir),
            "written_files": {
                candidate_id: _project_relative_path(Path(path))
                for candidate_id, path in summary["written_files"].items()
            },
        }
    except Exception as exc:
        _raise_http_error(exc)
        return {}
