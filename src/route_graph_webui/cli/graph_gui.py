from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from route_graph_webui.apps.workers import route_generation as route_generation_worker_module
from route_graph_webui.graph.canvas_view import (
    GRAPH_GUI_CANVAS_VIEW_BOOL_KEYS,
    GRAPH_GUI_CANVAS_VIEW_DEFAULTS,
    GRAPH_GUI_CANVAS_VIEW_META_KEY,
    read_graph_gui_canvas_view as shared_read_graph_gui_canvas_view,
    resolve_graph_gui_canvas_view as shared_resolve_graph_gui_canvas_view,
    sync_graph_gui_canvas_view,
    write_graph_gui_canvas_view as shared_write_graph_gui_canvas_view,
)
from route_graph_webui.graph.conversion import candidate_to_plan
from route_graph_webui.graph.edge_intent import resolve_edge_creation_intent
from route_graph_webui.graph.editor import GraphEditor
from route_graph_webui.graph.grouping import (
    derive_graph_color_grouping,
    get_edge_group_color,
    get_edge_kind,
    normalize_hex_color,
    read_graph_bridge_style,
    read_graph_group_configs,
    resolve_bridge_color,
    write_graph_bridge_style,
    write_graph_group_configs,
)
from route_graph_webui.graph.io import load_graph, save_candidate_set
from route_graph_webui.graph.meta import (
    DEFAULT_BRIDGE_COLOR,
    DEFAULT_GROUP_COLOR,
    EDGE_KIND_BRIDGE,
    EDGE_KIND_GROUP,
    GRAPH_BRIDGE_STYLE_META_KEY,
    GRAPH_GROUP_CONFIGS_META_KEY,
    GROUP_CONFIG_LABEL_KEY,
    NODE_SAMPLE_RADIUS_META_KEY,
)
from route_graph_webui.graph.model import GraphSchemaError, RouteCandidate, RouteCandidateSet, RouteGraph
from route_graph_webui.graph.ui_state import (
    GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY as SHARED_GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY,
    GRAPH_GUI_AUTO_PLAN_LIST_KEYS as SHARED_GRAPH_GUI_AUTO_PLAN_LIST_KEYS,
    GRAPH_GUI_EXPORT_BOOL_KEYS as SHARED_GRAPH_GUI_EXPORT_BOOL_KEYS,
    GRAPH_GUI_EXPORT_INPUTS_META_KEY as SHARED_GRAPH_GUI_EXPORT_INPUTS_META_KEY,
    GRAPH_GUI_GLOBAL_EXPORT_TEXT_KEYS as SHARED_GRAPH_GUI_GLOBAL_EXPORT_TEXT_KEYS,
    GRAPH_GUI_GROUP_EXPORT_TEXT_KEYS as SHARED_GRAPH_GUI_GROUP_EXPORT_TEXT_KEYS,
    GRAPH_GUI_WEBUI_INPUTS_META_KEY as SHARED_GRAPH_GUI_WEBUI_INPUTS_META_KEY,
    has_graph_gui_export_input as shared_has_graph_gui_export_input,
    read_graph_gui_auto_plan_inputs as shared_read_graph_gui_auto_plan_inputs,
    read_graph_gui_export_inputs as shared_read_graph_gui_export_inputs,
    write_graph_gui_auto_plan_inputs as shared_write_graph_gui_auto_plan_inputs,
    write_graph_gui_export_inputs as shared_write_graph_gui_export_inputs,
)
from route_graph_webui.graph.validation import validate_graph
from route_graph_webui.mission_export import (
    DEFAULT_CORNER_MAX_YAW_STEP_DEG,
    DEFAULT_CORNER_MIN_ANGLE_DEG,
    DEFAULT_CORNER_RADIUS,
    DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
    DEFAULT_TURN_SMOOTHING_ENABLED,
    DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    DEFAULT_U_TURN_THRESHOLD_DEG,
    DEFAULT_U_TURN_TRANSITION_DISTANCE,
    MissionExportOptions,
    export_candidate_set_missions,
    export_mission,
)
from route_graph_webui.planning.auto_route_planner import AutoPlanningConfig, AutoPlanningExportConfig
from route_graph_webui.runtime_support.runtime import resolve_data_path, timestamp_now
from route_graph_webui.shared.geometry import distance_point_to_segment_2d, project_point_to_segment_2d
from route_graph_webui.cli.visualize_graph import (
    CanvasViewState,
    build_canvas_projection,
    compute_canvas_view_center,
    compute_edge_pass_label_layout,
    inverse_canvas_view_position,
    project_point,
    render_graph_preview,
    transform_canvas_view_position,
    unproject_point,
)
from route_graph_webui.backend.services.job_service import BackgroundJobRecord, BackgroundJobService


DEFAULT_ENV_ID = "UnrealTrack-DowntownWest-ContinuousColor-v0"
EXPORT_ALTITUDE_MODES = ("fixed", "follow_nodes")
PREVIEW_STATUS_NO_CANDIDATE = "请先生成并选中一条候选轨迹。"
PREVIEW_STATUS_IDLE = "尚未刷新轨迹预览"
PREVIEW_STATUS_STALE = "预览已过期，请点击“刷新轨迹预览”"
PREVIEW_AUTO_REFRESH_DELAY_MS = 250
ROUTE_GENERATION_POLL_MS = 100
ROUTE_GENERATION_MAX_MESSAGES_PER_POLL = 20
UI_HEARTBEAT_MS = 200
UI_STALL_DUMP_SECONDS = 2.5
CANVAS_NODE_HIT_RADIUS_PX = 10.0
CANVAS_EDGE_HIT_RADIUS_PX = 8.0
CANVAS_SECONDARY_DRAG_THRESHOLD_PX = 6.0
CANVAS_EDGE_INSERT_ENDPOINT_GUARD_PX = 10.0
GRAPH_GUI_EXPORT_INPUTS_META_KEY = SHARED_GRAPH_GUI_EXPORT_INPUTS_META_KEY
GRAPH_GUI_WEBUI_INPUTS_META_KEY = SHARED_GRAPH_GUI_WEBUI_INPUTS_META_KEY
GRAPH_GUI_EXPORT_INPUT_AUTOSAVE_DELAY_MS = 350
GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY = SHARED_GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY
GRAPH_GUI_AUTO_PLAN_LIST_KEYS = SHARED_GRAPH_GUI_AUTO_PLAN_LIST_KEYS
GRAPH_GUI_CANVAS_VIEW_AUTOSAVE_DELAY_MS = 350
GRAPH_GUI_GLOBAL_EXPORT_TEXT_KEYS = SHARED_GRAPH_GUI_GLOBAL_EXPORT_TEXT_KEYS
GRAPH_GUI_EXPORT_BOOL_KEYS = SHARED_GRAPH_GUI_EXPORT_BOOL_KEYS
GRAPH_GUI_GROUP_EXPORT_TEXT_KEYS = SHARED_GRAPH_GUI_GROUP_EXPORT_TEXT_KEYS


def _validate_loaded_graph(graph: RouteGraph, *, source: str | Path | None = None) -> RouteGraph:
    report = validate_graph(graph)
    if report.errors:
        if source is None:
            message = report.format_text()
        else:
            message = f"Graph `{Path(source).resolve()}` failed validation:\n{report.format_text()}"
        raise GraphSchemaError(message)
    return graph


def _load_validated_graph(path: str | Path) -> RouteGraph:
    return _validate_loaded_graph(load_graph(path), source=path)


@dataclass(slots=True)
class PreviewStateModel:
    mission: dict[str, Any] | None = None
    has_plan: bool = False
    is_stale: bool = False

    def clear(self) -> None:
        self.mission = None
        self.has_plan = False
        self.is_stale = False

    def select_candidate(self) -> None:
        self.mission = None
        self.has_plan = True
        self.is_stale = True

    def mark_stale(self) -> None:
        self.has_plan = True
        self.is_stale = True

    def invalidate(self) -> bool:
        if not self.has_plan or (self.mission is None and self.is_stale):
            return False
        self.mark_stale()
        return True

    def set_preview(self, mission: dict[str, Any]) -> None:
        self.mission = mission
        self.has_plan = True
        self.is_stale = False

    def status_text(self) -> str:
        if not self.has_plan:
            return PREVIEW_STATUS_NO_CANDIDATE
        if self.mission is None:
            return PREVIEW_STATUS_STALE if self.is_stale else PREVIEW_STATUS_IDLE
        frame_count = len(self.mission.get("positions", []))
        if self.is_stale:
            return f"{PREVIEW_STATUS_STALE} (showing cached preview, {frame_count} frames)"
        return f"已生成轨迹预览，共 {frame_count} 帧"


PENDING_GROUP_STATUS_PREFIX = "待创建颜色组: "
PAINT_MODE_STATUS_DISABLED = "染色模式：关闭"
INSERT_MODE_STATUS_DISABLED = "插点模式：关闭"


@dataclass(frozen=True, slots=True)
class CanvasEdgeHit:
    edge_id: str
    projection_ratio: float
    projected_point: tuple[float, float]
    segment_start: tuple[float, float]
    segment_end: tuple[float, float]


@dataclass(slots=True)
class GroupControlState:
    used_colors: list[str]
    selected_color: str | None
    editor_color: str | None
    staged_color: str | None
    combo_value: str
    staged_label: str


@dataclass(slots=True)
class GroupConfigSyncResult:
    configs: dict[str, dict[str, str]]
    staged_color: str | None
    staged_config: dict[str, str] | None
    meta_changed: bool


def derive_used_group_colors(graph: RouteGraph) -> list[str]:
    grouping = derive_graph_color_grouping(graph)
    return sorted(grouping.group_edge_ids.keys())


def derive_palette_colors(
    used_colors: Iterable[str],
    session_palette_colors: Iterable[str],
) -> tuple[list[str], list[str]]:
    normalized_used_colors = sorted(
        {
            normalize_hex_color(color, field_name="group color")
            for color in used_colors
        }
    )
    used_lookup = set(normalized_used_colors)
    normalized_session_colors = sorted(
        {
            normalize_hex_color(color, field_name="group color")
            for color in session_palette_colors
            if normalize_hex_color(color, field_name="group color") not in used_lookup
        }
    )
    return normalized_used_colors, normalized_session_colors


def resolve_palette_brush_color(
    used_colors: Iterable[str],
    session_palette_colors: Iterable[str],
    current_color: str | None,
    *,
    preferred_color: str | None = None,
) -> str | None:
    normalized_used_colors, normalized_session_colors = derive_palette_colors(
        used_colors,
        session_palette_colors,
    )
    available_colors = [*normalized_used_colors, *normalized_session_colors]
    available_lookup = set(available_colors)
    normalized_current_color = (
        None
        if current_color is None
        else normalize_hex_color(current_color, field_name="group color")
    )
    if normalized_current_color in available_lookup:
        return normalized_current_color
    normalized_preferred_color = (
        None
        if preferred_color is None
        else normalize_hex_color(preferred_color, field_name="group color")
    )
    if normalized_preferred_color in available_lookup:
        return normalized_preferred_color
    return available_colors[0] if available_colors else None


def format_paint_mode_status(
    paint_mode_enabled: bool,
    paint_color: str | None,
) -> str:
    normalized_color = (
        None
        if paint_color is None
        else normalize_hex_color(paint_color, field_name="group color")
    )
    if normalized_color is None:
        return PAINT_MODE_STATUS_DISABLED
    if paint_mode_enabled:
        return f"染色模式：开启（当前画笔 {normalized_color}）"
    return f"染色模式：关闭（当前画笔 {normalized_color}）"


def format_insert_mode_status(insert_mode_enabled: bool) -> str:
    if insert_mode_enabled:
        return "插点模式：开启（右键点击组内边插点）"
    return INSERT_MODE_STATUS_DISABLED


def resolve_canvas_primary_click_action(
    *,
    paint_mode_enabled: bool,
    nearest_node_id: str | None,
    nearest_edge_id: str | None,
    additive: bool,
) -> str:
    if paint_mode_enabled:
        return "paint_edge" if nearest_edge_id is not None else "noop"
    if nearest_node_id is None:
        if additive:
            return "noop"
        return "select_edge" if nearest_edge_id is not None else "noop"
    return "toggle_node" if additive else "select_node"


def resolve_canvas_secondary_release_action(
    *,
    insert_mode_enabled: bool,
    nearest_edge_id: str | None,
    movement_distance_px: float,
    drag_threshold_px: float = CANVAS_SECONDARY_DRAG_THRESHOLD_PX,
) -> str:
    if float(movement_distance_px) > float(drag_threshold_px):
        return "pan"
    if insert_mode_enabled and nearest_edge_id is not None:
        return "insert_edge"
    return "noop"


def ideal_text_color_for_background(color: str) -> str:
    normalized_color = normalize_hex_color(color, field_name="group color")
    red = int(normalized_color[1:3], 16)
    green = int(normalized_color[3:5], 16)
    blue = int(normalized_color[5:7], 16)
    luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
    return "#111827" if luminance >= 160.0 else "#F8FAFC"


def prune_group_configs_to_used_colors(
    configs: Mapping[str, Mapping[str, str]],
    used_colors: Iterable[str],
) -> dict[str, dict[str, str]]:
    allowed = {normalize_hex_color(color, field_name="group color") for color in used_colors}
    pruned: dict[str, dict[str, str]] = {}
    for color, payload in configs.items():
        normalized_color = normalize_hex_color(color, field_name="group color")
        if normalized_color in allowed:
            pruned[normalized_color] = dict(payload)
    return pruned


def reconcile_group_configs_for_used_colors(
    configs: Mapping[str, Mapping[str, str]],
    used_colors: Iterable[str],
    *,
    default_payload: Mapping[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    normalized_used_colors = [
        normalize_hex_color(color, field_name="group color")
        for color in used_colors
    ]
    reconciled = prune_group_configs_to_used_colors(configs, normalized_used_colors)
    if default_payload is None:
        return reconciled
    normalized_defaults = {str(key): str(value) for key, value in default_payload.items()}
    for color in sorted(normalized_used_colors):
        reconciled.setdefault(color, dict(normalized_defaults))
    return reconciled


def build_group_control_state(
    used_colors: Iterable[str],
    *,
    active_group_color: str | None,
    staged_group_color: str | None,
) -> GroupControlState:
    normalized_used_colors = [
        normalize_hex_color(color, field_name="group color")
        for color in used_colors
    ]
    normalized_active_color = (
        None
        if active_group_color is None
        else normalize_hex_color(active_group_color, field_name="group color")
    )
    normalized_staged_color = (
        None
        if staged_group_color is None
        else normalize_hex_color(staged_group_color, field_name="group color")
    )
    used_lookup = set(normalized_used_colors)
    if normalized_staged_color is not None and normalized_staged_color in used_lookup:
        return GroupControlState(
            used_colors=normalized_used_colors,
            selected_color=normalized_staged_color,
            editor_color=normalized_staged_color,
            staged_color=None,
            combo_value=normalized_staged_color,
            staged_label="",
        )
    if normalized_staged_color is not None:
        return GroupControlState(
            used_colors=normalized_used_colors,
            selected_color=None,
            editor_color=normalized_staged_color,
            staged_color=normalized_staged_color,
            combo_value="",
            staged_label=f"{PENDING_GROUP_STATUS_PREFIX}{normalized_staged_color}",
        )
    selected_color = (
        normalized_active_color
        if normalized_active_color in used_lookup
        else (normalized_used_colors[0] if normalized_used_colors else None)
    )
    return GroupControlState(
        used_colors=normalized_used_colors,
        selected_color=selected_color,
        editor_color=selected_color,
        staged_color=None,
        combo_value=selected_color or "",
        staged_label="",
    )


def sync_group_config_state(
    configs: Mapping[str, Mapping[str, str]],
    used_colors: Iterable[str],
    *,
    default_payload: Mapping[str, str],
    active_group_color: str | None,
    staged_group_color: str | None,
    staged_group_config: Mapping[str, str] | None,
    current_payload: Mapping[str, str],
) -> GroupConfigSyncResult:
    normalized_configs = {
        normalize_hex_color(color, field_name="group color"): dict(payload)
        for color, payload in configs.items()
    }
    normalized_used_colors = [
        normalize_hex_color(color, field_name="group color")
        for color in used_colors
    ]
    reconciled = reconcile_group_configs_for_used_colors(
        normalized_configs,
        normalized_used_colors,
        default_payload=default_payload,
    )
    meta_changed = reconciled != normalized_configs
    normalized_active_color = (
        None
        if active_group_color is None
        else normalize_hex_color(active_group_color, field_name="group color")
    )
    normalized_staged_color = (
        None
        if staged_group_color is None
        else normalize_hex_color(staged_group_color, field_name="group color")
    )
    normalized_current_payload = {
        str(key): str(value)
        for key, value in current_payload.items()
    }
    used_lookup = set(normalized_used_colors)
    next_staged_color = normalized_staged_color
    next_staged_config = (
        None
        if staged_group_config is None
        else {str(key): str(value) for key, value in staged_group_config.items()}
    )
    if normalized_staged_color is not None:
        if normalized_staged_color in used_lookup:
            if reconciled.get(normalized_staged_color) != normalized_current_payload:
                reconciled[normalized_staged_color] = dict(normalized_current_payload)
                meta_changed = True
            next_staged_color = None
            next_staged_config = None
        else:
            next_staged_config = dict(normalized_current_payload)
    elif normalized_active_color is not None and normalized_active_color in used_lookup:
        if reconciled.get(normalized_active_color) != normalized_current_payload:
            reconciled[normalized_active_color] = dict(normalized_current_payload)
            meta_changed = True
    return GroupConfigSyncResult(
        configs=reconciled,
        staged_color=next_staged_color,
        staged_config=next_staged_config,
        meta_changed=meta_changed,
    )


def resolve_graph_gui_edge_creation_meta(
    graph: RouteGraph,
    from_node: str,
    to_node: str,
    *,
    fallback_group_color: str | None,
) -> dict[str, Any]:
    return resolve_edge_creation_intent(
        graph,
        from_node=from_node,
        to_node=to_node,
        fallback_group_color=fallback_group_color,
    ).to_edge_meta()


def resolve_export_options(
    *,
    step_distance_text: str,
    fps_text: str,
    altitude_mode: str,
    fixed_z_text: str,
    altitude_offset_text: str,
    takeoff_landing_relative_z_text: str,
    takeoff_landing_step_distance_text: str,
    node_sample_radius_text: str,
    random_seed_text: str,
    turn_smoothing_enabled: bool,
    corner_radius_text: str,
    small_turn_yaw_blend_threshold_deg_text: str,
    corner_min_angle_deg_text: str,
    u_turn_threshold_deg_text: str,
    u_turn_transition_distance_text: str,
    corner_max_yaw_step_deg_text: str,
    u_turn_pivot_yaw_step_deg_text: str,
) -> dict[str, float | int | None | str | bool]:
    try:
        step_distance = float(step_distance_text.strip() or "0")
    except ValueError as exc:
        raise GraphSchemaError("Step Distance must be numeric.") from exc
    if step_distance <= 0:
        raise GraphSchemaError("Step Distance must be greater than 0.")

    try:
        fps = float(fps_text.strip() or "0")
    except ValueError as exc:
        raise GraphSchemaError("FPS must be numeric.") from exc
    if fps <= 0:
        raise GraphSchemaError("FPS must be greater than 0.")

    altitude_mode = altitude_mode.strip()
    if altitude_mode not in EXPORT_ALTITUDE_MODES:
        raise GraphSchemaError(
            f"Altitude Mode must be one of: {', '.join(EXPORT_ALTITUDE_MODES)}."
        )

    altitude_offset_text = altitude_offset_text.strip()
    try:
        altitude_offset = float(altitude_offset_text or "0")
    except ValueError as exc:
        raise GraphSchemaError("Altitude Offset must be numeric.") from exc

    takeoff_landing_relative_z_text = takeoff_landing_relative_z_text.strip()
    if takeoff_landing_relative_z_text:
        try:
            takeoff_landing_relative_z = float(takeoff_landing_relative_z_text)
        except ValueError as exc:
            raise GraphSchemaError("Takeoff/Landing Relative Z must be numeric or left empty.") from exc
        if takeoff_landing_relative_z < 0:
            raise GraphSchemaError("Takeoff/Landing Relative Z must be non-negative.")
    else:
        takeoff_landing_relative_z = None

    takeoff_landing_step_distance_text = takeoff_landing_step_distance_text.strip()
    if takeoff_landing_step_distance_text:
        try:
            takeoff_landing_step_distance = float(takeoff_landing_step_distance_text)
        except ValueError as exc:
            raise GraphSchemaError(
                "Takeoff/Landing Step Distance must be numeric or left empty."
            ) from exc
        if takeoff_landing_step_distance <= 0:
            raise GraphSchemaError("Takeoff/Landing Step Distance must be greater than 0.")
    else:
        takeoff_landing_step_distance = None

    node_sample_radius_text = node_sample_radius_text.strip()
    try:
        node_sample_radius = float(node_sample_radius_text or "0")
    except ValueError as exc:
        raise GraphSchemaError("Node Sample Radius must be numeric.") from exc
    if node_sample_radius < 0:
        raise GraphSchemaError("Node Sample Radius must be non-negative.")

    fixed_z: float | None
    if altitude_mode == "fixed":
        fixed_z_text = fixed_z_text.strip()
        if fixed_z_text:
            try:
                fixed_z = float(fixed_z_text)
            except ValueError as exc:
                raise GraphSchemaError("Fixed Z must be numeric or left empty.") from exc
        else:
            fixed_z = None
    else:
        fixed_z = None

    random_seed_text = random_seed_text.strip()
    if random_seed_text:
        try:
            random_seed = int(random_seed_text)
        except ValueError as exc:
            raise GraphSchemaError("Random Seed must be an integer or left empty.") from exc
    else:
        random_seed = None

    if turn_smoothing_enabled:
        try:
            corner_radius = float(corner_radius_text.strip() or "0")
        except ValueError as exc:
            raise GraphSchemaError("Corner Radius must be numeric.") from exc
        if corner_radius <= 0:
            raise GraphSchemaError("Corner Radius must be greater than 0.")

        try:
            small_turn_yaw_blend_threshold_deg = float(
                small_turn_yaw_blend_threshold_deg_text.strip() or "0"
            )
        except ValueError as exc:
            raise GraphSchemaError("Small Turn Yaw Blend Threshold must be numeric.") from exc
        if small_turn_yaw_blend_threshold_deg < 0:
            raise GraphSchemaError("Small Turn Yaw Blend Threshold must be non-negative.")

        try:
            corner_min_angle_deg = float(corner_min_angle_deg_text.strip() or "0")
        except ValueError as exc:
            raise GraphSchemaError("Corner Min Angle must be numeric.") from exc
        if corner_min_angle_deg < 0 or corner_min_angle_deg >= 180:
            raise GraphSchemaError("Corner Min Angle must be in [0, 180).")

        try:
            u_turn_threshold_deg = float(u_turn_threshold_deg_text.strip() or "0")
        except ValueError as exc:
            raise GraphSchemaError("U-turn Threshold must be numeric.") from exc
        if u_turn_threshold_deg <= corner_min_angle_deg or u_turn_threshold_deg > 180:
            raise GraphSchemaError(
                "U-turn Threshold must be greater than Corner Min Angle and at most 180."
            )

        try:
            u_turn_transition_distance = float(u_turn_transition_distance_text.strip() or "0")
        except ValueError as exc:
            raise GraphSchemaError("U-turn Transition Distance must be numeric.") from exc
        if u_turn_transition_distance <= 0:
            raise GraphSchemaError("U-turn Transition Distance must be greater than 0.")

        try:
            corner_max_yaw_step_deg = float(corner_max_yaw_step_deg_text.strip() or "0")
        except ValueError as exc:
            raise GraphSchemaError("Corner Max Yaw Step must be numeric.") from exc
        if corner_max_yaw_step_deg <= 0:
            raise GraphSchemaError("Corner Max Yaw Step must be greater than 0.")

        try:
            u_turn_pivot_yaw_step_deg = float(u_turn_pivot_yaw_step_deg_text.strip() or "0")
        except ValueError as exc:
            raise GraphSchemaError("U-turn Pivot Yaw Step must be numeric.") from exc
        if u_turn_pivot_yaw_step_deg <= 0:
            raise GraphSchemaError("U-turn Pivot Yaw Step must be greater than 0.")
    else:
        corner_radius = DEFAULT_CORNER_RADIUS
        corner_min_angle_deg = DEFAULT_CORNER_MIN_ANGLE_DEG
        u_turn_threshold_deg = DEFAULT_U_TURN_THRESHOLD_DEG
        u_turn_transition_distance = DEFAULT_U_TURN_TRANSITION_DISTANCE
        corner_max_yaw_step_deg = DEFAULT_CORNER_MAX_YAW_STEP_DEG
        u_turn_pivot_yaw_step_deg = DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG
        small_turn_yaw_blend_threshold_deg = DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG

    return MissionExportOptions.from_mapping(
        {
            "step_distance": step_distance,
            "fps": fps,
            "altitude_mode": altitude_mode,
            "fixed_z": fixed_z,
            "altitude_offset": altitude_offset,
            "takeoff_landing_relative_z": takeoff_landing_relative_z,
            "takeoff_landing_step_distance": takeoff_landing_step_distance,
            "node_sample_radius": node_sample_radius,
            "random_seed": random_seed,
            "turn_smoothing_enabled": bool(turn_smoothing_enabled),
            "corner_radius": corner_radius,
            "small_turn_yaw_blend_threshold_deg": small_turn_yaw_blend_threshold_deg,
            "corner_min_angle_deg": corner_min_angle_deg,
            "u_turn_threshold_deg": u_turn_threshold_deg,
            "u_turn_transition_distance": u_turn_transition_distance,
            "corner_max_yaw_step_deg": corner_max_yaw_step_deg,
            "u_turn_pivot_yaw_step_deg": u_turn_pivot_yaw_step_deg,
        }
    ).to_mission_kwargs()


def format_auto_excluded_endpoint_groups_status(*, selected_count: int, available_count: int) -> str:
    selected_count = max(int(selected_count), 0)
    available_count = max(int(available_count), 0)
    if available_count <= 0:
        return "已选 0 个组；当前图没有可排除的颜色组。"
    return f"已选 {selected_count} 个组；已选中的颜色组不会作为自动规划的起点或终点。"


def format_auto_allowed_route_groups_status(*, selected_count: int, available_count: int) -> str:
    selected_count = max(int(selected_count), 0)
    available_count = max(int(available_count), 0)
    if available_count <= 0:
        return "已选 0 个组；当前图没有可用于自动规划的颜色组。"
    return f"已选 {selected_count} 个组；留空表示不限制。"


def normalize_auto_group_selection(
    available_colors: Iterable[str],
    selected_colors: Iterable[str],
) -> list[str]:
    normalized_available: list[str] = []
    available_lookup: set[str] = set()
    for color in available_colors:
        normalized = normalize_hex_color(color, field_name="group color")
        if normalized in available_lookup:
            continue
        available_lookup.add(normalized)
        normalized_available.append(normalized)

    normalized_selected: list[str] = []
    seen_selected: set[str] = set()
    for color in selected_colors:
        try:
            normalized = normalize_hex_color(color, field_name="group color")
        except GraphSchemaError:
            continue
        if normalized not in available_lookup or normalized in seen_selected:
            continue
        seen_selected.add(normalized)
        normalized_selected.append(normalized)
    return normalized_selected


def resolve_auto_endpoint_group_choices(
    used_colors: Iterable[str],
    allowed_route_group_colors: Iterable[str],
) -> list[str]:
    normalized_used = normalize_auto_group_selection(used_colors, used_colors)
    normalized_allowed = normalize_auto_group_selection(normalized_used, allowed_route_group_colors)
    return normalized_allowed if normalized_allowed else normalized_used


def is_fixed_z_enabled(altitude_mode: str) -> bool:
    return altitude_mode.strip() == "fixed"


def resolve_node_sample_radius_override_text(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        radius = float(text)
    except ValueError as exc:
        raise GraphSchemaError("Node Sample Radius Override must be numeric or left empty.") from exc
    if radius < 0:
        raise GraphSchemaError("Node Sample Radius Override must be non-negative.")
    return radius


def resolve_length_limit_text(value: str, *, label: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        length = float(text)
    except ValueError as exc:
        raise GraphSchemaError(f"{label} must be numeric or left empty.") from exc
    if length <= 0:
        raise GraphSchemaError(f"{label} must be greater than 0.")
    return length


def resolve_frame_limit_text(value: str, *, label: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    try:
        frame_count = int(text)
    except ValueError as exc:
        raise GraphSchemaError(f"{label} must be an integer or left empty.") from exc
    if frame_count <= 0:
        raise GraphSchemaError(f"{label} must be greater than 0.")
    return frame_count


def resolve_max_total_length_text(value: str) -> float | None:
    return resolve_length_limit_text(value, label="Max Total Length")


def resolve_min_total_length_text(value: str) -> float | None:
    return resolve_length_limit_text(value, label="Min Total Length")


def resolve_min_frame_count_text(value: str) -> int | None:
    return resolve_frame_limit_text(value, label="Min Trajectory Frame Count")


def resolve_max_frame_count_text(value: str) -> int | None:
    return resolve_frame_limit_text(value, label="Max Trajectory Frame Count")


def filters_require_auto_keep(
    *,
    min_total_length_text: str,
    max_total_length_text: str,
    min_frame_count_text: str,
    max_frame_count_text: str,
) -> bool:
    return all(
        value is not None
        for value in (
            resolve_min_total_length_text(min_total_length_text),
            resolve_max_total_length_text(max_total_length_text),
            resolve_min_frame_count_text(min_frame_count_text),
            resolve_max_frame_count_text(max_frame_count_text),
        )
    )


def distance_point_to_segment(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> float:
    return distance_point_to_segment_2d(point, segment_start, segment_end)


def project_point_onto_segment(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> tuple[float, tuple[float, float]]:
    return project_point_to_segment_2d(point, segment_start, segment_end)


def project_point_to_segment_ratio(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> float:
    projection_ratio, _ = project_point_onto_segment(point, segment_start, segment_end)
    return projection_ratio


def _blend_hex_color(color: str, *, target: str = "#FFFFFF", ratio: float = 0.65) -> str:
    def _parse_hex(value: str) -> tuple[int, int, int]:
        normalized = value.strip()
        if not normalized.startswith("#") or len(normalized) != 7:
            raise GraphSchemaError("Color must be in #RRGGBB format")
        return (
            int(normalized[1:3], 16),
            int(normalized[3:5], 16),
            int(normalized[5:7], 16),
        )

    ratio = max(0.0, min(1.0, float(ratio)))
    source_rgb = _parse_hex(color)
    target_rgb = _parse_hex(target)
    blended = []
    for source_channel, target_channel in zip(source_rgb, target_rgb, strict=True):
        channel = round(source_channel + ((target_channel - source_channel) * ratio))
        blended.append(max(0, min(255, channel)))
    return "#{:02X}{:02X}{:02X}".format(*blended)


def resolve_canvas_edge_draw_style(
    *,
    base_color: str,
    enabled: bool,
    selected: bool,
    active_group_selected: bool,
    belongs_to_active_group: bool,
) -> tuple[str, int, tuple[int, int] | tuple[()]]:
    color = base_color
    width = 3 if selected else 2
    if active_group_selected:
        if belongs_to_active_group:
            width = 4 if not selected else 5
        else:
            color = _blend_hex_color(base_color, target="#FFFFFF", ratio=0.72)
            width = 2 if selected else 1
    dash: tuple[int, int] | tuple[()] = () if enabled else (4, 4)
    return color, width, dash


def read_graph_gui_export_inputs(meta: Mapping[str, Any] | None) -> dict[str, str | bool]:
    return shared_read_graph_gui_export_inputs(meta)


def write_graph_gui_export_inputs(
    meta: dict[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, str | bool]:
    return shared_write_graph_gui_export_inputs(meta, payload)


def has_graph_gui_export_input(meta: Mapping[str, Any] | None, key: str) -> bool:
    return shared_has_graph_gui_export_input(meta, key)


def read_graph_gui_auto_plan_inputs(meta: Mapping[str, Any] | None) -> dict[str, str | bool | list[str]]:
    return shared_read_graph_gui_auto_plan_inputs(meta)


def write_graph_gui_auto_plan_inputs(
    meta: dict[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, str | bool | list[str]]:
    return shared_write_graph_gui_auto_plan_inputs(meta, payload)


def read_graph_gui_canvas_view(meta: Mapping[str, Any] | None) -> dict[str, int | bool]:
    return shared_read_graph_gui_canvas_view(meta)


def resolve_graph_gui_canvas_view(meta: Mapping[str, Any] | None) -> dict[str, int | bool]:
    return shared_resolve_graph_gui_canvas_view(meta)


def write_graph_gui_canvas_view(
    meta: dict[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, int | bool]:
    return shared_write_graph_gui_canvas_view(meta, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop editor for route_graph_webui graphs.")
    parser.add_argument("--graph", help="Existing graph JSON to open")
    parser.add_argument("--output", help="Default graph output path for new files")
    parser.add_argument("--mode", default="edit", choices=["edit"])
    parser.add_argument("--env-id", default=DEFAULT_ENV_ID)
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--step-distance", type=float, default=60.0)
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--max-routes", type=int, default=10)
    parser.add_argument("--max-edge-pass-factor", type=float, default=2.5)
    parser.add_argument("--min-total-length", type=float, default=None)
    parser.add_argument("--max-total-length", type=float, default=None)
    parser.add_argument("--min-frame-count", type=int, default=None)
    parser.add_argument("--max-frame-count", type=int, default=None)
    parser.add_argument("--altitude-mode", choices=list(EXPORT_ALTITUDE_MODES), default="fixed")
    parser.add_argument("--fixed-z", type=float, default=None)
    parser.add_argument("--altitude-offset", type=float, default=0.0)
    parser.add_argument("--takeoff-landing-relative-z", type=float, default=None)
    parser.add_argument("--takeoff-landing-step-distance", type=float, default=None)
    parser.add_argument("--node-sample-radius", type=float, default=0.0)
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument("--no-turn-smoothing", dest="turn_smoothing_enabled", action="store_false")
    parser.set_defaults(turn_smoothing_enabled=DEFAULT_TURN_SMOOTHING_ENABLED)
    parser.add_argument("--corner-radius", type=float, default=DEFAULT_CORNER_RADIUS)
    parser.add_argument("--corner-min-angle-deg", type=float, default=DEFAULT_CORNER_MIN_ANGLE_DEG)
    parser.add_argument("--u-turn-threshold-deg", type=float, default=DEFAULT_U_TURN_THRESHOLD_DEG)
    parser.add_argument("--u-turn-transition-distance", type=float, default=DEFAULT_U_TURN_TRANSITION_DISTANCE)
    parser.add_argument("--corner-max-yaw-step-deg", type=float, default=DEFAULT_CORNER_MAX_YAW_STEP_DEG)
    parser.add_argument("--u-turn-pivot-yaw-step-deg", type=float, default=DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG)
    return parser


def _blank_graph(env_id: str, graph_name: str) -> RouteGraph:
    return RouteGraph(
        env_id=env_id,
        graph_name=graph_name,
        default_altitude=None,
        nodes=[],
        edges=[],
        meta={"created_at": timestamp_now(), "creator": "route_graph_webui.graph_gui"},
    )


def launch_gui(args: argparse.Namespace) -> int:
    import tkinter as tk
    from tkinter import colorchooser, filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    class GraphGuiApp:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.root.title("route_graph_webui 轨迹图编辑器")
            self.root.geometry(f"{args.width}x{args.height}")

            self.graph_path = Path(args.graph).resolve() if args.graph else None
            self.default_output = (
                Path(args.output).resolve()
                if args.output
                else resolve_data_path("graphs", "untitled_graph.json")
            )
            if self.graph_path and self.graph_path.exists():
                self.graph = _load_validated_graph(self.graph_path)
            else:
                self.graph = _blank_graph(args.env_id, self.default_output.stem)
                self.graph_path = self.default_output

            self.editor = GraphEditor(self.graph)
            self.selected_nodes: list[str] = []
            self.selected_edge_id: str | None = None
            self.start_node: str | None = None
            self.end_node: str | None = None
            self.via_nodes: list[str] = []
            self.current_candidate_set: RouteCandidateSet | None = None
            self.current_candidate_id: str | None = None
            self.current_plan = None
            self.preview_state = PreviewStateModel()
            self._preview_cache: dict[tuple[str, tuple[Any, ...]], dict[str, Any]] = {}
            self._preview_refresh_after_id: str | None = None
            self._syncing_candidate_tree = False
            self.zoom = 1.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            self._pan_origin: tuple[int, int] | None = None
            self._secondary_button_press_origin: tuple[int, int] | None = None
            self._secondary_button_press_edge_id: str | None = None
            self._secondary_button_drag_active = False
            initial_canvas_view = resolve_graph_gui_canvas_view(self.graph.meta)
            self.canvas_view_rotation_quadrants = int(initial_canvas_view["rotation_quadrants"])
            self.canvas_view_flip_horizontal = bool(initial_canvas_view["flip_horizontal"])
            self.canvas_view_flip_vertical = bool(initial_canvas_view["flip_vertical"])
            self._route_generation_worker_module = "route_graph_webui.apps.workers.route_generation"
            self._route_generation_worker_path = Path(route_generation_worker_module.__file__).resolve()
            self._route_generation_job_service = BackgroundJobService(
                worker_path=self._route_generation_worker_path,
                worker_module=self._route_generation_worker_module,
                runtime_root=resolve_data_path("progress") / "gui_route_generation",
                project_root=Path(__file__).resolve().parent,
                runtime_prefix="route_generation_",
                retention_seconds=60,
                post_exit_poll_limit=5,
            )
            self._route_generation_job_service.cleanup_orphaned_runtimes()
            self._generation_sensitive_widgets = []
            self._route_generation_job_id = 0
            self._route_generation_active = False
            self._route_generation_job_record: BackgroundJobRecord | None = None
            self._route_generation_poll_after_id: str | None = None
            self._last_route_progress: dict[str, Any] | None = None
            self._route_generation_summary = ""
            self._preview_trace_tokens = []
            self._invalid_canvas_edge_ids_logged: set[str] = set()
            self._debug_log_dir = resolve_data_path("logs")
            self._debug_log_dir.mkdir(parents=True, exist_ok=True)
            self._debug_log_path = self._debug_log_dir / "graph_gui_debug.log"
            self._stackdump_path = self._debug_log_dir / "graph_gui_stackdump.log"
            self._ui_heartbeat_after_id: str | None = None
            self._last_ui_heartbeat = time.monotonic()
            self._main_thread_id = threading.get_ident()
            self._watchdog_stop_event = threading.Event()
            self._watchdog_dumped = False
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="graph-gui-watchdog",
                daemon=True,
            )
            self._launch_args = args
            self._selection_panel_node_id: str | None = None
            self._export_inputs_trace_tokens = []
            self._export_input_autosave_after_id: str | None = None
            self._export_inputs_dirty = False
            self._suspend_export_input_autosave = False
            self._canvas_view_autosave_after_id: str | None = None
            self._canvas_view_dirty = False
            initial_export_inputs = self._resolve_initial_export_inputs(self.graph)
            self._group_defaults = self._build_group_config_defaults(initial_export_inputs)
            self._active_group_color: str | None = None
            self._staged_group_color: str | None = None
            self._staged_group_config: dict[str, str] | None = None
            self._session_palette_colors: set[str] = set()
            self._paint_color: str | None = None
            self._paint_mode_enabled = False
            self._insert_mode_enabled = False
            self._group_combo_labels: list[str] = []
            self._group_combo_color_lookup: dict[str, str] = {}
            self._auto_allowed_group_label_lookup: dict[str, str] = {}
            self._auto_endpoint_group_label_lookup: dict[str, str] = {}
            self._suspend_group_selection = False
            self.max_routes_var = tk.StringVar(value=str(args.max_routes))
            self.edge_pass_factor_var = tk.StringVar(value=str(args.max_edge_pass_factor))
            self.min_total_length_var = tk.StringVar(
                value="" if args.min_total_length is None else str(args.min_total_length)
            )
            self.max_total_length_var = tk.StringVar(
                value="" if args.max_total_length is None else str(args.max_total_length)
            )
            self.min_frame_count_var = tk.StringVar(
                value="" if args.min_frame_count is None else str(args.min_frame_count)
            )
            self.max_frame_count_var = tk.StringVar(
                value="" if args.max_frame_count is None else str(args.max_frame_count)
            )
            initial_auto_plan_inputs = self._resolve_initial_auto_plan_inputs(self.graph)
            self.planning_mode_var = tk.StringVar(value=str(initial_auto_plan_inputs["planning_mode"]))
            self.auto_max_output_routes_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_max_output_routes"])
            )
            self.auto_max_routes_per_pair_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_max_routes_per_pair"])
            )
            self.auto_max_anchor_pairs_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_max_anchor_pairs_to_evaluate"])
            )
            self.auto_distance_per_frame_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_distance_per_frame"])
            )
            self.auto_min_total_length_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_min_total_length"])
            )
            self.auto_max_total_length_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_max_total_length"])
            )
            self.auto_min_frame_count_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_min_frame_count"])
            )
            self.auto_max_frame_count_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_max_frame_count"])
            )
            self.auto_min_endpoint_distance_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_min_endpoint_distance"])
            )
            self.auto_max_search_states_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_max_search_states"])
            )
            self.auto_coverage_weight_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_coverage_weight"])
            )
            self.auto_diversity_weight_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_diversity_weight"])
            )
            self.auto_anchor_weight_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_anchor_weight"])
            )
            self.auto_reverse_penalty_weight_var = tk.StringVar(
                value=str(initial_auto_plan_inputs["auto_reverse_penalty_weight"])
            )
            self.auto_prefer_connected_anchors_var = tk.BooleanVar(
                value=bool(initial_auto_plan_inputs["auto_prefer_connected_anchors"])
            )
            self.auto_prefer_route_diversity_var = tk.BooleanVar(
                value=bool(initial_auto_plan_inputs["auto_prefer_route_diversity"])
            )
            self.auto_allow_reverse_direction_counterparts_var = tk.BooleanVar(
                value=bool(initial_auto_plan_inputs["auto_allow_reverse_direction_counterparts"])
            )
            self.auto_enable_global_coverage_var = tk.BooleanVar(
                value=bool(initial_auto_plan_inputs["auto_enable_global_coverage"])
            )
            self._auto_allowed_route_group_colors = [
                str(color) for color in initial_auto_plan_inputs["auto_allowed_route_group_colors"]
            ]
            self._auto_excluded_endpoint_group_colors = [
                str(color) for color in initial_auto_plan_inputs["auto_excluded_endpoint_group_colors"]
            ]
            self.auto_coverage_stats_var = tk.StringVar(value="尚未执行自动规划")
            self.auto_allowed_route_groups_status_var = tk.StringVar(value="")
            self.auto_excluded_endpoint_groups_status_var = tk.StringVar(value="")
            self.step_distance_var = tk.StringVar(value=str(initial_export_inputs["step_distance"]))
            self.node_sample_radius_var = tk.StringVar(
                value=str(self._group_defaults["node_sample_radius"])
            )
            self.fps_var = tk.StringVar(value=str(initial_export_inputs["fps"]))
            self.altitude_mode_var = tk.StringVar(value=str(self._group_defaults["altitude_mode"]))
            self.fixed_z_var = tk.StringVar(value=str(self._group_defaults["fixed_z"]))
            self.altitude_offset_var = tk.StringVar(value=str(self._group_defaults["altitude_offset"]))
            self.takeoff_landing_relative_z_var = tk.StringVar(
                value=str(self._group_defaults["takeoff_landing_relative_z"])
            )
            self.takeoff_landing_step_distance_var = tk.StringVar(
                value=str(self._group_defaults["takeoff_landing_step_distance"])
            )
            self.random_seed_var = tk.StringVar(value=str(initial_export_inputs["random_seed"]))
            self.turn_smoothing_enabled_var = tk.BooleanVar(
                value=bool(initial_export_inputs["turn_smoothing_enabled"])
            )
            self.corner_radius_var = tk.StringVar(value=str(initial_export_inputs["corner_radius"]))
            self.small_turn_yaw_blend_threshold_deg_var = tk.StringVar(
                value=str(initial_export_inputs["small_turn_yaw_blend_threshold_deg"])
            )
            self.corner_min_angle_deg_var = tk.StringVar(
                value=str(initial_export_inputs["corner_min_angle_deg"])
            )
            self.u_turn_threshold_deg_var = tk.StringVar(
                value=str(initial_export_inputs["u_turn_threshold_deg"])
            )
            self.u_turn_transition_distance_var = tk.StringVar(
                value=str(initial_export_inputs["u_turn_transition_distance"])
            )
            self.corner_max_yaw_step_deg_var = tk.StringVar(
                value=str(initial_export_inputs["corner_max_yaw_step_deg"])
            )
            self.u_turn_pivot_yaw_step_deg_var = tk.StringVar(
                value=str(initial_export_inputs["u_turn_pivot_yaw_step_deg"])
            )
            self.canvas_view_rotation_var = tk.StringVar()
            self.canvas_view_flip_horizontal_var = tk.BooleanVar(
                value=self.canvas_view_flip_horizontal
            )
            self.canvas_view_flip_vertical_var = tk.BooleanVar(
                value=self.canvas_view_flip_vertical
            )
            self.active_group_color_var = tk.StringVar(value="")
            self.staged_group_status_var = tk.StringVar(value="")
            self.paint_color_var = tk.StringVar(value="")
            self.paint_mode_status_var = tk.StringVar(value=PAINT_MODE_STATUS_DISABLED)
            self.paint_mode_button_var = tk.StringVar(value="进入染色模式")
            self.insert_mode_status_var = tk.StringVar(value=INSERT_MODE_STATUS_DISABLED)
            self.insert_mode_button_var = tk.StringVar(value="进入插点模式")
            self.selected_edge_kind_var = tk.StringVar(value="未选中边")
            self.selected_edge_color_var = tk.StringVar(value="")
            self.bridge_color_var = tk.StringVar(value="")
            self._sync_canvas_view_controls()

            self._build_layout(ttk, tk)
            self._sync_planning_mode_controls()
            self._refresh_group_controls(preserve_current=False)
            self._bind_shortcuts()
            self._bind_node_editor_autosave()
            self._register_preview_invalidation_traces()
            self._register_export_input_persistence_traces()
            self._sync_export_controls()
            self.root.protocol("WM_DELETE_WINDOW", self.on_close)
            self._watchdog_thread.start()
            self._schedule_ui_heartbeat()
            self._refresh_all()
            self._debug_log("GUI initialized")
            self.log(f"已加载图文件：{self.graph_path}")

        def _build_layout(self, ttk, tk) -> None:
            self.root.columnconfigure(1, weight=1)
            self.root.rowconfigure(0, weight=1)
            self.root.rowconfigure(1, weight=0)

            left = ttk.Frame(self.root, padding=8)
            center = ttk.Frame(self.root, padding=8)
            right = ttk.Frame(self.root, padding=8)
            bottom = ttk.Frame(self.root, padding=8)

            left.grid(row=0, column=0, sticky="nsew")
            center.grid(row=0, column=1, sticky="nsew")
            right.grid(row=0, column=2, sticky="nsew")
            bottom.grid(row=1, column=0, columnspan=3, sticky="ew")

            self.root.columnconfigure(0, weight=0)
            self.root.columnconfigure(1, weight=1)
            self.root.columnconfigure(2, weight=0)
            center.rowconfigure(0, weight=0)
            center.rowconfigure(1, weight=1)
            center.columnconfigure(0, weight=1)
            right.rowconfigure(0, weight=1)
            right.columnconfigure(0, weight=1)

            self.open_graph_button = ttk.Button(left, text="打开图文件", command=self.open_graph)
            self.open_graph_button.pack(fill="x")
            self.save_graph_button = ttk.Button(left, text="保存图文件", command=self.save_graph_to_disk)
            self.save_graph_button.pack(fill="x", pady=(6, 0))
            self.validate_graph_button = ttk.Button(left, text="校验图结构", command=self.validate_graph_ui)
            self.validate_graph_button.pack(fill="x", pady=(6, 12))

            ttk.Label(left, text="节点").pack(anchor="w")
            self.node_listbox = tk.Listbox(left, selectmode=tk.EXTENDED, height=18, exportselection=False)
            self.node_listbox.pack(fill="both", expand=True)
            self.node_listbox.bind("<<ListboxSelect>>", self.on_node_list_select)

            ttk.Label(left, text="边").pack(anchor="w", pady=(12, 0))
            self.edge_listbox = tk.Listbox(left, selectmode=tk.BROWSE, height=16, exportselection=False)
            self.edge_listbox.pack(fill="both", expand=True)
            self.edge_listbox.bind("<<ListboxSelect>>", self.on_edge_list_select)

            self.canvas_toolbar = ttk.Frame(center)
            self.canvas_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
            self.rotate_left_button = ttk.Button(
                self.canvas_toolbar,
                text="Rotate Left",
                command=self.rotate_canvas_left,
            )
            self.rotate_left_button.pack(side="left")
            self.rotate_right_button = ttk.Button(
                self.canvas_toolbar,
                text="Rotate Right",
                command=self.rotate_canvas_right,
            )
            self.rotate_right_button.pack(side="left", padx=(6, 0))
            self.flip_horizontal_button = ttk.Checkbutton(
                self.canvas_toolbar,
                text="Flip H",
                variable=self.canvas_view_flip_horizontal_var,
                command=self.toggle_canvas_flip_horizontal,
            )
            self.flip_horizontal_button.pack(side="left", padx=(12, 0))
            self.flip_vertical_button = ttk.Checkbutton(
                self.canvas_toolbar,
                text="Flip V",
                variable=self.canvas_view_flip_vertical_var,
                command=self.toggle_canvas_flip_vertical,
            )
            self.flip_vertical_button.pack(side="left", padx=(6, 0))
            self.reset_view_button = ttk.Button(
                self.canvas_toolbar,
                text="Reset View",
                command=self.reset_canvas_view,
            )
            self.reset_view_button.pack(side="left", padx=(12, 0))
            self.canvas_view_rotation_label = ttk.Label(
                self.canvas_toolbar,
                textvariable=self.canvas_view_rotation_var,
            )
            self.canvas_view_rotation_label.pack(side="right")

            self.canvas = tk.Canvas(center, bg="#f8fafc", highlightthickness=1, highlightbackground="#cbd5e1")
            self.canvas.grid(row=1, column=0, sticky="nsew")
            self.canvas.bind("<Button-1>", self.on_canvas_click)
            self.canvas.bind("<Shift-Button-1>", self.on_canvas_shift_click)
            self.canvas.bind("<Double-Button-1>", self.on_canvas_double_set_start)
            self.canvas.bind("<Double-Button-3>", self.on_canvas_double_set_end)
            self.canvas.bind("<Double-Button-2>", self.on_canvas_double_toggle_via)
            self.canvas.bind("<ButtonPress-3>", self.on_canvas_secondary_press)
            self.canvas.bind("<B3-Motion>", self.on_canvas_secondary_move)
            self.canvas.bind("<ButtonRelease-3>", self.on_canvas_secondary_release)
            self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
            self.canvas.bind("<Configure>", lambda _event: self.refresh_canvas())

            self.right_scroll_canvas = tk.Canvas(right, highlightthickness=0, borderwidth=0)
            self.right_scroll_canvas.grid(row=0, column=0, sticky="nsew")
            right_scrollbar = ttk.Scrollbar(right, orient="vertical", command=self.right_scroll_canvas.yview)
            right_scrollbar.grid(row=0, column=1, sticky="ns")
            self.right_scroll_canvas.configure(yscrollcommand=right_scrollbar.set)
            self.right_content = ttk.Frame(self.right_scroll_canvas)
            self.right_content_window = self.right_scroll_canvas.create_window(
                (0, 0),
                window=self.right_content,
                anchor="nw",
            )
            self.right_content.bind(
                "<Configure>",
                lambda _event: self.right_scroll_canvas.configure(
                    scrollregion=self.right_scroll_canvas.bbox("all")
                ),
            )
            self.right_scroll_canvas.bind("<Configure>", self._on_right_canvas_configure)

            panel = self.right_content

            ttk.Label(panel, text="当前选中节点").pack(anchor="w")
            self.selected_node_var = tk.StringVar(value="")
            self.selected_node_label = ttk.Label(panel, textvariable=self.selected_node_var)
            self.selected_node_label.pack(anchor="w", pady=(0, 8))

            ttk.Label(panel, text="名称").pack(anchor="w")
            self.name_entry = ttk.Entry(panel)
            self.name_entry.pack(fill="x")

            ttk.Label(panel, text="标签（空格分隔）").pack(anchor="w", pady=(8, 0))
            self.tags_entry = ttk.Entry(panel)
            self.tags_entry.pack(fill="x")
            ttk.Label(panel, text="节点采样半径覆盖").pack(anchor="w", pady=(8, 0))
            self.node_sample_radius_override_entry = ttk.Entry(panel)
            self.node_sample_radius_override_entry.pack(fill="x")
            self.apply_node_edits_button = ttk.Button(panel, text="应用节点修改", command=self.apply_node_edits)
            self.apply_node_edits_button.pack(fill="x", pady=(8, 6))
            self.delete_node_button = ttk.Button(panel, text="删除该点", command=self.delete_current_node)
            self.delete_node_button.pack(fill="x", pady=(0, 12))

            ttk.Label(panel, text="边操作").pack(anchor="w")
            self.create_edge_button = ttk.Button(panel, text="创建边", command=self.create_edge)
            self.create_edge_button.pack(fill="x")
            self.remove_edge_button = ttk.Button(panel, text="删除边", command=self.remove_edge)
            self.remove_edge_button.pack(fill="x", pady=(6, 0))
            self.enable_edge_button = ttk.Button(
                panel,
                text="启用边",
                command=lambda: self.set_edge_enabled(True),
            )
            self.enable_edge_button.pack(fill="x", pady=(6, 0))
            self.disable_edge_button = ttk.Button(
                panel,
                text="禁用边",
                command=lambda: self.set_edge_enabled(False),
            )
            self.disable_edge_button.pack(fill="x", pady=(6, 12))
            self.edge_kind_label = ttk.Label(panel, textvariable=self.selected_edge_kind_var, wraplength=300)
            self.edge_kind_label.pack(anchor="w")
            self.edge_color_label = ttk.Label(panel, textvariable=self.selected_edge_color_var, wraplength=300)
            self.edge_color_label.pack(anchor="w", pady=(2, 0))
            self.set_edge_bridge_button = ttk.Button(
                panel,
                text="设为桥接边",
                command=self.set_selected_edge_bridge,
            )
            self.set_edge_bridge_button.pack(fill="x", pady=(8, 12))

            insert_frame = ttk.LabelFrame(panel, text="插点模式", padding=8)
            insert_frame.pack(fill="x", pady=(0, 12))
            self.insert_mode_status_label = ttk.Label(
                insert_frame,
                textvariable=self.insert_mode_status_var,
                wraplength=300,
            )
            self.insert_mode_status_label.pack(anchor="w")
            self.toggle_insert_mode_button = ttk.Button(
                insert_frame,
                textvariable=self.insert_mode_button_var,
                command=self.toggle_insert_mode,
            )
            self.toggle_insert_mode_button.pack(fill="x", pady=(8, 0))

            palette_frame = ttk.LabelFrame(panel, text="调色盘", padding=8)
            palette_frame.pack(fill="x", pady=(0, 12))
            ttk.Label(palette_frame, text="当前画笔颜色").pack(anchor="w")
            self.paint_color_label = ttk.Label(palette_frame, textvariable=self.paint_color_var)
            self.paint_color_label.pack(anchor="w")
            self.paint_mode_status_label = ttk.Label(
                palette_frame,
                textvariable=self.paint_mode_status_var,
                wraplength=300,
            )
            self.paint_mode_status_label.pack(anchor="w", pady=(4, 0))
            self.toggle_paint_mode_button = ttk.Button(
                palette_frame,
                textvariable=self.paint_mode_button_var,
                command=self.toggle_paint_mode,
            )
            self.toggle_paint_mode_button.pack(fill="x", pady=(8, 0))
            self.add_palette_color_button = ttk.Button(
                palette_frame,
                text="新增调色盘颜色",
                command=self.add_palette_color,
            )
            self.add_palette_color_button.pack(fill="x", pady=(6, 0))
            ttk.Label(palette_frame, text="已使用颜色").pack(anchor="w", pady=(8, 0))
            self.used_palette_colors_frame = tk.Frame(palette_frame, bg="#f8fafc")
            self.used_palette_colors_frame.pack(fill="x")
            ttk.Label(palette_frame, text="会话新增颜色").pack(anchor="w", pady=(8, 0))
            self.session_palette_colors_frame = tk.Frame(palette_frame, bg="#f8fafc")
            self.session_palette_colors_frame.pack(fill="x")

            group_frame = ttk.LabelFrame(panel, text="颜色组参数", padding=8)
            group_frame.pack(fill="x", pady=(0, 12))
            ttk.Label(group_frame, text="当前颜色组").pack(anchor="w")
            self.group_color_combo = ttk.Combobox(
                group_frame,
                textvariable=self.active_group_color_var,
                state="readonly",
            )
            self.group_color_combo.pack(fill="x")
            self.group_color_combo.bind("<<ComboboxSelected>>", self.on_group_selection_changed)
            ttk.Label(group_frame, text="桥接边颜色").pack(anchor="w", pady=(8, 0))
            self.bridge_color_display = ttk.Label(group_frame, textvariable=self.bridge_color_var)
            self.bridge_color_display.pack(anchor="w")
            self.choose_bridge_color_button = ttk.Button(
                group_frame,
                text="设置桥接边颜色",
                command=self.choose_bridge_color,
            )
            self.choose_bridge_color_button.pack(fill="x", pady=(6, 0))

            ttk.Label(panel, text="锚点设置").pack(anchor="w")
            self.set_start_button = ttk.Button(panel, text="设为起点", command=self.set_start)
            self.set_start_button.pack(fill="x")
            self.set_end_button = ttk.Button(panel, text="设为终点", command=self.set_end)
            self.set_end_button.pack(fill="x", pady=(6, 0))
            self.add_via_button = ttk.Button(panel, text="添加途经点", command=self.add_via)
            self.add_via_button.pack(fill="x", pady=(6, 0))
            self.clear_via_button = ttk.Button(panel, text="清空途经点", command=self.clear_via)
            self.clear_via_button.pack(fill="x", pady=(6, 12))

            ttk.Label(panel, text="途经点列表").pack(anchor="w")
            self.via_listbox = tk.Listbox(panel, selectmode=tk.BROWSE, height=6, exportselection=False)
            self.via_listbox.pack(fill="x")
            self.via_up_button = ttk.Button(panel, text="上移途经点", command=lambda: self.reorder_via(-1))
            self.via_up_button.pack(fill="x", pady=(6, 0))
            self.via_down_button = ttk.Button(panel, text="下移途经点", command=lambda: self.reorder_via(1))
            self.via_down_button.pack(fill="x", pady=(6, 12))

            route_frame = ttk.LabelFrame(panel, text="候选轨迹生成", padding=8)
            route_frame.pack(fill="x", pady=(12, 0))
            ttk.Label(route_frame, text="规划模式").pack(anchor="w")
            self.planning_mode_combo = ttk.Combobox(
                route_frame,
                textvariable=self.planning_mode_var,
                values=("manual", "auto"),
                state="readonly",
            )
            self.planning_mode_combo.pack(fill="x")
            self.planning_mode_combo.bind("<<ComboboxSelected>>", self.on_planning_mode_changed)
            self.manual_route_controls_frame = ttk.Frame(route_frame)
            self.manual_route_controls_frame.pack(fill="x")
            ttk.Label(self.manual_route_controls_frame, text="最大候选数").pack(anchor="w", pady=(8, 0))
            self.max_routes_entry = ttk.Entry(self.manual_route_controls_frame, textvariable=self.max_routes_var)
            self.max_routes_entry.pack(fill="x")
            ttk.Label(self.manual_route_controls_frame, text="最大边经过倍数").pack(anchor="w", pady=(8, 0))
            self.edge_pass_factor_entry = ttk.Entry(self.manual_route_controls_frame, textvariable=self.edge_pass_factor_var)
            self.edge_pass_factor_entry.pack(fill="x")
            ttk.Label(self.manual_route_controls_frame, text="最小长度下限（可留空）").pack(anchor="w", pady=(8, 0))
            self.min_total_length_entry = ttk.Entry(self.manual_route_controls_frame, textvariable=self.min_total_length_var)
            self.min_total_length_entry.pack(fill="x")
            ttk.Label(self.manual_route_controls_frame, text="最大长度上限（可留空）").pack(anchor="w", pady=(8, 0))
            self.max_total_length_entry = ttk.Entry(self.manual_route_controls_frame, textvariable=self.max_total_length_var)
            self.max_total_length_entry.pack(fill="x")
            ttk.Label(self.manual_route_controls_frame, text="最小轨迹帧数下限（可留空）").pack(anchor="w", pady=(8, 0))
            self.min_frame_count_entry = ttk.Entry(self.manual_route_controls_frame, textvariable=self.min_frame_count_var)
            self.min_frame_count_entry.pack(fill="x")
            ttk.Label(self.manual_route_controls_frame, text="最大轨迹帧数上限（可留空）").pack(anchor="w", pady=(8, 0))
            self.max_frame_count_entry = ttk.Entry(self.manual_route_controls_frame, textvariable=self.max_frame_count_var)
            self.max_frame_count_entry.pack(fill="x")
            self.auto_route_controls_frame = ttk.LabelFrame(route_frame, text="自动规划参数", padding=6)
            self.auto_route_controls_frame.pack(fill="x", pady=(8, 0))
            ttk.Label(self.auto_route_controls_frame, text="最终输出路线数上限").pack(anchor="w")
            self.auto_max_output_routes_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_max_output_routes_var,
            )
            self.auto_max_output_routes_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="每组起终点最大候选数").pack(anchor="w", pady=(8, 0))
            self.auto_max_routes_per_pair_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_max_routes_per_pair_var,
            )
            self.auto_max_routes_per_pair_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="最大评估起终点对数量").pack(anchor="w", pady=(8, 0))
            self.auto_max_anchor_pairs_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_max_anchor_pairs_var,
            )
            self.auto_max_anchor_pairs_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="每帧对应距离").pack(anchor="w", pady=(8, 0))
            self.auto_distance_per_frame_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_distance_per_frame_var,
            )
            self.auto_distance_per_frame_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="自动规划最小长度（可留空）").pack(anchor="w", pady=(8, 0))
            self.auto_min_total_length_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_min_total_length_var,
            )
            self.auto_min_total_length_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="自动规划最大长度（可留空）").pack(anchor="w", pady=(8, 0))
            self.auto_max_total_length_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_max_total_length_var,
            )
            self.auto_max_total_length_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="自动规划最小帧数（可留空）").pack(anchor="w", pady=(8, 0))
            self.auto_min_frame_count_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_min_frame_count_var,
            )
            self.auto_min_frame_count_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="自动规划最大帧数（可留空）").pack(anchor="w", pady=(8, 0))
            self.auto_max_frame_count_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_max_frame_count_var,
            )
            self.auto_max_frame_count_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="起终点最小直线距离").pack(anchor="w", pady=(8, 0))
            self.auto_min_endpoint_distance_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_min_endpoint_distance_var,
            )
            self.auto_min_endpoint_distance_entry.pack(fill="x")
            ttk.Label(
                self.auto_route_controls_frame,
                text="仅使用以下颜色组生成轨迹（留空表示不限）",
            ).pack(anchor="w", pady=(8, 0))
            self.auto_allowed_route_groups_frame = ttk.Frame(self.auto_route_controls_frame)
            self.auto_allowed_route_groups_frame.pack(fill="x")
            self.auto_allowed_route_groups_frame.columnconfigure(0, weight=1)
            self.auto_allowed_route_groups_listbox = tk.Listbox(
                self.auto_allowed_route_groups_frame,
                selectmode=tk.MULTIPLE,
                height=6,
                exportselection=False,
            )
            self.auto_allowed_route_groups_listbox.grid(row=0, column=0, sticky="nsew")
            self.auto_allowed_route_groups_scrollbar = ttk.Scrollbar(
                self.auto_allowed_route_groups_frame,
                orient="vertical",
                command=self.auto_allowed_route_groups_listbox.yview,
            )
            self.auto_allowed_route_groups_scrollbar.grid(row=0, column=1, sticky="ns")
            self.auto_allowed_route_groups_listbox.configure(
                yscrollcommand=self.auto_allowed_route_groups_scrollbar.set
            )
            self.auto_allowed_route_groups_listbox.bind(
                "<<ListboxSelect>>",
                self.on_auto_allowed_route_groups_changed,
            )
            self.auto_allowed_route_groups_listbox.bind(
                "<MouseWheel>",
                self._on_auto_allowed_route_groups_mouse_wheel,
                add="+",
            )
            self.auto_allowed_route_groups_listbox.bind(
                "<Button-4>",
                self._on_auto_allowed_route_groups_mouse_wheel,
                add="+",
            )
            self.auto_allowed_route_groups_listbox.bind(
                "<Button-5>",
                self._on_auto_allowed_route_groups_mouse_wheel,
                add="+",
            )
            self.auto_allowed_route_groups_scrollbar.bind(
                "<MouseWheel>",
                self._on_auto_allowed_route_groups_mouse_wheel,
                add="+",
            )
            self.auto_allowed_route_groups_scrollbar.bind(
                "<Button-4>",
                self._on_auto_allowed_route_groups_mouse_wheel,
                add="+",
            )
            self.auto_allowed_route_groups_scrollbar.bind(
                "<Button-5>",
                self._on_auto_allowed_route_groups_mouse_wheel,
                add="+",
            )
            ttk.Label(
                self.auto_route_controls_frame,
                textvariable=self.auto_allowed_route_groups_status_var,
                wraplength=300,
            ).pack(anchor="w", pady=(4, 0))
            ttk.Label(self.auto_route_controls_frame, text="以下颜色组不作为起终点").pack(anchor="w", pady=(8, 0))
            self.auto_excluded_endpoint_groups_frame = ttk.Frame(self.auto_route_controls_frame)
            self.auto_excluded_endpoint_groups_frame.pack(fill="x")
            self.auto_excluded_endpoint_groups_frame.columnconfigure(0, weight=1)
            self.auto_excluded_endpoint_groups_listbox = tk.Listbox(
                self.auto_excluded_endpoint_groups_frame,
                selectmode=tk.MULTIPLE,
                height=6,
                exportselection=False,
            )
            self.auto_excluded_endpoint_groups_listbox.grid(row=0, column=0, sticky="nsew")
            self.auto_excluded_endpoint_groups_scrollbar = ttk.Scrollbar(
                self.auto_excluded_endpoint_groups_frame,
                orient="vertical",
                command=self.auto_excluded_endpoint_groups_listbox.yview,
            )
            self.auto_excluded_endpoint_groups_scrollbar.grid(row=0, column=1, sticky="ns")
            self.auto_excluded_endpoint_groups_listbox.configure(
                yscrollcommand=self.auto_excluded_endpoint_groups_scrollbar.set
            )
            self.auto_excluded_endpoint_groups_listbox.bind(
                "<<ListboxSelect>>",
                self.on_auto_excluded_endpoint_groups_changed,
            )
            self.auto_excluded_endpoint_groups_listbox.bind(
                "<MouseWheel>",
                self._on_auto_excluded_endpoint_groups_mouse_wheel,
                add="+",
            )
            self.auto_excluded_endpoint_groups_listbox.bind(
                "<Button-4>",
                self._on_auto_excluded_endpoint_groups_mouse_wheel,
                add="+",
            )
            self.auto_excluded_endpoint_groups_listbox.bind(
                "<Button-5>",
                self._on_auto_excluded_endpoint_groups_mouse_wheel,
                add="+",
            )
            self.auto_excluded_endpoint_groups_scrollbar.bind(
                "<MouseWheel>",
                self._on_auto_excluded_endpoint_groups_mouse_wheel,
                add="+",
            )
            self.auto_excluded_endpoint_groups_scrollbar.bind(
                "<Button-4>",
                self._on_auto_excluded_endpoint_groups_mouse_wheel,
                add="+",
            )
            self.auto_excluded_endpoint_groups_scrollbar.bind(
                "<Button-5>",
                self._on_auto_excluded_endpoint_groups_mouse_wheel,
                add="+",
            )
            ttk.Label(
                self.auto_route_controls_frame,
                textvariable=self.auto_excluded_endpoint_groups_status_var,
                wraplength=300,
            ).pack(anchor="w", pady=(4, 0))
            ttk.Label(self.auto_route_controls_frame, text="自动规划最大搜索状态数").pack(anchor="w", pady=(8, 0))
            self.auto_max_search_states_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_max_search_states_var,
            )
            self.auto_max_search_states_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="覆盖收益权重").pack(anchor="w", pady=(8, 0))
            self.auto_coverage_weight_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_coverage_weight_var,
            )
            self.auto_coverage_weight_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="多样性惩罚权重").pack(anchor="w", pady=(8, 0))
            self.auto_diversity_weight_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_diversity_weight_var,
            )
            self.auto_diversity_weight_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="锚点连接度权重").pack(anchor="w", pady=(8, 0))
            self.auto_anchor_weight_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_anchor_weight_var,
            )
            self.auto_anchor_weight_entry.pack(fill="x")
            ttk.Label(self.auto_route_controls_frame, text="反向重复惩罚权重").pack(anchor="w", pady=(8, 0))
            self.auto_reverse_penalty_weight_entry = ttk.Entry(
                self.auto_route_controls_frame,
                textvariable=self.auto_reverse_penalty_weight_var,
            )
            self.auto_reverse_penalty_weight_entry.pack(fill="x")
            self.auto_prefer_connected_anchors_checkbutton = ttk.Checkbutton(
                self.auto_route_controls_frame,
                text="偏好高连接度起终点",
                variable=self.auto_prefer_connected_anchors_var,
            )
            self.auto_prefer_connected_anchors_checkbutton.pack(anchor="w", pady=(8, 0))
            self.auto_prefer_route_diversity_checkbutton = ttk.Checkbutton(
                self.auto_route_controls_frame,
                text="偏好全局多样性",
                variable=self.auto_prefer_route_diversity_var,
            )
            self.auto_prefer_route_diversity_checkbutton.pack(anchor="w")
            self.auto_allow_reverse_direction_counterparts_checkbutton = ttk.Checkbutton(
                self.auto_route_controls_frame,
                text="保留正反方向对应路线",
                variable=self.auto_allow_reverse_direction_counterparts_var,
            )
            self.auto_allow_reverse_direction_counterparts_checkbutton.pack(anchor="w")
            self.auto_enable_global_coverage_checkbutton = ttk.Checkbutton(
                self.auto_route_controls_frame,
                text="启用全局覆盖率优化",
                variable=self.auto_enable_global_coverage_var,
            )
            self.auto_enable_global_coverage_checkbutton.pack(anchor="w")
            ttk.Label(self.auto_route_controls_frame, textvariable=self.auto_coverage_stats_var, wraplength=300).pack(
                anchor="w",
                pady=(8, 0),
            )
            self.generate_routes_button = ttk.Button(
                route_frame,
                text="生成候选轨迹",
                command=self.generate_routes,
            )
            self.generate_routes_button.pack(fill="x", pady=(8, 0))
            self.route_generation_status_var = tk.StringVar(value="就绪")
            ttk.Label(route_frame, textvariable=self.route_generation_status_var, wraplength=300).pack(
                anchor="w",
                pady=(8, 0),
            )
            self.route_generation_progress = ttk.Progressbar(
                route_frame,
                mode="indeterminate",
                maximum=1.0,
                value=0.0,
            )
            self.route_generation_progress.pack(fill="x", pady=(6, 0))

            self.refresh_preview_button = ttk.Button(
                panel,
                text="刷新轨迹预览",
                command=self.refresh_mission_preview_ui,
            )
            self.refresh_preview_button.pack(fill="x", pady=(12, 0))
            self.toggle_keep_button = ttk.Button(
                panel,
                text="切换保留状态",
                command=self.toggle_keep_current_candidate,
            )
            self.toggle_keep_button.pack(fill="x", pady=(6, 0))
            self.keep_selected_candidates_button = ttk.Button(
                panel,
                text="保留当前多选项",
                command=self.keep_selected_candidates,
            )
            self.keep_selected_candidates_button.pack(fill="x", pady=(6, 0))
            self.unkeep_selected_candidates_button = ttk.Button(
                panel,
                text="取消保留当前多选项",
                command=self.unkeep_selected_candidates,
            )
            self.unkeep_selected_candidates_button.pack(fill="x", pady=(6, 0))
            self.save_candidate_set_button = ttk.Button(
                panel,
                text="保存候选集 JSON",
                command=self.save_candidate_set_ui,
            )
            self.save_candidate_set_button.pack(fill="x", pady=(6, 0))
            self.export_mission_button = ttk.Button(
                panel,
                text="导出当前 Mission JSON",
                command=self.export_mission_ui,
            )
            self.export_mission_button.pack(fill="x", pady=(6, 0))
            self.export_selected_missions_button = ttk.Button(
                panel,
                text="导出当前多选项 Mission",
                command=self.export_selected_missions_ui,
            )
            self.export_selected_missions_button.pack(fill="x", pady=(6, 0))
            self.export_kept_missions_button = ttk.Button(
                panel,
                text="导出已保留 Mission",
                command=self.export_kept_missions_ui,
            )
            self.export_kept_missions_button.pack(fill="x", pady=(6, 0))
            self.export_preview_png_button = ttk.Button(
                panel,
                text="导出预览 PNG",
                command=self.export_preview_png,
            )
            self.export_preview_png_button.pack(fill="x", pady=(6, 0))

            ttk.Label(panel, text="候选列表").pack(anchor="w", pady=(12, 0))
            self.candidate_tree_frame = ttk.Frame(panel)
            self.candidate_tree_frame.pack(fill="both", expand=True)
            self.candidate_tree = ttk.Treeview(
                self.candidate_tree_frame,
                columns=(
                    "keep",
                    "rank",
                    "candidate_id",
                    "start_node",
                    "end_node",
                    "length",
                    "frame_count",
                    "edge_passes",
                    "repeats",
                ),
                show="headings",
                height=8,
                selectmode="extended",
            )
            self.candidate_tree_scrollbar = ttk.Scrollbar(
                self.candidate_tree_frame,
                orient="vertical",
                command=self.candidate_tree.yview,
            )
            self.candidate_tree.configure(yscrollcommand=self.candidate_tree_scrollbar.set)
            self.candidate_tree.heading("keep", text="保留")
            self.candidate_tree.heading("rank", text="排名")
            self.candidate_tree.heading("candidate_id", text="候选ID")
            self.candidate_tree.heading("start_node", text="起点")
            self.candidate_tree.heading("end_node", text="终点")
            self.candidate_tree.heading("length", text="长度")
            self.candidate_tree.heading("frame_count", text="帧数")
            self.candidate_tree.heading("edge_passes", text="边经过数")
            self.candidate_tree.heading("repeats", text="重复节点数")
            self.candidate_tree.column("keep", width=50, anchor="center")
            self.candidate_tree.column("rank", width=45, anchor="center")
            self.candidate_tree.column("candidate_id", width=90, anchor="center")
            self.candidate_tree.column("start_node", width=75, anchor="center")
            self.candidate_tree.column("end_node", width=75, anchor="center")
            self.candidate_tree.column("length", width=80, anchor="e")
            self.candidate_tree.column("frame_count", width=70, anchor="center")
            self.candidate_tree.column("edge_passes", width=90, anchor="center")
            self.candidate_tree.column("repeats", width=95, anchor="center")
            self.candidate_tree.pack(side="left", fill="both", expand=True)
            self.candidate_tree_scrollbar.pack(side="right", fill="y")
            self.candidate_tree.bind("<<TreeviewSelect>>", self.on_candidate_tree_select)
            self.candidate_tree.bind("<Double-1>", self.on_candidate_tree_double_click)
            self.candidate_tree.bind("<Control-a>", self.on_candidate_tree_select_all)
            self.candidate_tree.bind("<Control-A>", self.on_candidate_tree_select_all)
            self.candidate_tree.bind("<MouseWheel>", self._on_candidate_tree_mouse_wheel, add="+")
            self.candidate_tree.bind("<Button-4>", self._on_candidate_tree_mouse_wheel, add="+")
            self.candidate_tree.bind("<Button-5>", self._on_candidate_tree_mouse_wheel, add="+")

            self.route_info_var = tk.StringVar(value="尚未生成候选轨迹")
            ttk.Label(panel, textvariable=self.route_info_var, wraplength=300).pack(anchor="w", pady=(12, 0))
            self.preview_status_var = tk.StringVar(value=self.preview_state.status_text())
            ttk.Label(panel, textvariable=self.preview_status_var, wraplength=300).pack(anchor="w", pady=(6, 0))

            mission_frame = ttk.LabelFrame(panel, text="Mission 导出", padding=8)
            mission_frame.pack(fill="x", pady=(12, 0))
            ttk.Label(mission_frame, text="插值步长").pack(anchor="w")
            self.step_distance_entry = ttk.Entry(mission_frame, textvariable=self.step_distance_var)
            self.step_distance_entry.pack(fill="x")
            ttk.Label(mission_frame, text="当前组节点采样半径").pack(anchor="w", pady=(8, 0))
            self.node_sample_radius_entry = ttk.Entry(
                mission_frame,
                textvariable=self.node_sample_radius_var,
            )
            self.node_sample_radius_entry.pack(fill="x")

            advanced_frame = ttk.LabelFrame(panel, text="高级导出参数", padding=8)
            advanced_frame.pack(fill="x", pady=(12, 0))
            ttk.Label(advanced_frame, text="FPS").pack(anchor="w")
            self.fps_entry = ttk.Entry(advanced_frame, textvariable=self.fps_var)
            self.fps_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="高度模式").pack(anchor="w", pady=(8, 0))
            self.altitude_mode_combo = ttk.Combobox(
                advanced_frame,
                textvariable=self.altitude_mode_var,
                values=EXPORT_ALTITUDE_MODES,
                state="readonly",
            )
            self.altitude_mode_combo.pack(fill="x")
            self.altitude_mode_combo.bind("<<ComboboxSelected>>", self.on_altitude_mode_changed)
            ttk.Label(advanced_frame, text="当前组固定高度 Z").pack(anchor="w", pady=(8, 0))
            self.fixed_z_entry = ttk.Entry(advanced_frame, textvariable=self.fixed_z_var)
            self.fixed_z_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="当前组高度偏移").pack(anchor="w", pady=(8, 0))
            self.altitude_offset_entry = ttk.Entry(advanced_frame, textvariable=self.altitude_offset_var)
            self.altitude_offset_entry.pack(fill="x")
            ttk.Label(
                advanced_frame,
                text="当前组起降相对航线下偏移（可选）",
            ).pack(anchor="w", pady=(8, 0))
            self.takeoff_landing_relative_z_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.takeoff_landing_relative_z_var,
            )
            self.takeoff_landing_relative_z_entry.pack(fill="x")
            ttk.Label(
                advanced_frame,
                text="当前组起飞 / 降落插值步长（可留空继承全局）",
            ).pack(anchor="w", pady=(8, 0))
            self.takeoff_landing_step_distance_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.takeoff_landing_step_distance_var,
            )
            self.takeoff_landing_step_distance_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="随机种子（可选）").pack(anchor="w", pady=(8, 0))
            self.random_seed_entry = ttk.Entry(advanced_frame, textvariable=self.random_seed_var)
            self.random_seed_entry.pack(fill="x")
            self.turn_smoothing_checkbutton = ttk.Checkbutton(
                advanced_frame,
                text="启用转角平滑",
                variable=self.turn_smoothing_enabled_var,
            )
            self.turn_smoothing_checkbutton.pack(anchor="w", pady=(8, 0))
            ttk.Label(advanced_frame, text="转角半径").pack(anchor="w", pady=(8, 0))
            self.corner_radius_entry = ttk.Entry(advanced_frame, textvariable=self.corner_radius_var)
            self.corner_radius_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="小角度航向平滑阈值（度）").pack(anchor="w", pady=(8, 0))
            self.small_turn_yaw_blend_threshold_deg_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.small_turn_yaw_blend_threshold_deg_var,
            )
            self.small_turn_yaw_blend_threshold_deg_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="转角最小角度（度）").pack(anchor="w", pady=(8, 0))
            self.corner_min_angle_deg_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.corner_min_angle_deg_var,
            )
            self.corner_min_angle_deg_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="调头阈值（度）").pack(anchor="w", pady=(8, 0))
            self.u_turn_threshold_deg_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.u_turn_threshold_deg_var,
            )
            self.u_turn_threshold_deg_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="调头过渡距离").pack(anchor="w", pady=(8, 0))
            self.u_turn_transition_distance_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.u_turn_transition_distance_var,
            )
            self.u_turn_transition_distance_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="转角最大航向步进（度）").pack(anchor="w", pady=(8, 0))
            self.corner_max_yaw_step_deg_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.corner_max_yaw_step_deg_var,
            )
            self.corner_max_yaw_step_deg_entry.pack(fill="x")
            ttk.Label(advanced_frame, text="调头轴点航向步进（度）").pack(anchor="w", pady=(8, 0))
            self.u_turn_pivot_yaw_step_deg_entry = ttk.Entry(
                advanced_frame,
                textvariable=self.u_turn_pivot_yaw_step_deg_var,
            )
            self.u_turn_pivot_yaw_step_deg_entry.pack(fill="x")
            self._bind_right_scroll_recursive(self.right_scroll_canvas)
            self._bind_right_scroll_recursive(panel)

            self.status_var = tk.StringVar(value="就绪")
            ttk.Label(bottom, textvariable=self.status_var).pack(anchor="w")
            self.log_widget = ScrolledText(bottom, height=8, wrap="word")
            self.log_widget.pack(fill="both", expand=True, pady=(6, 0))
            self.log_widget.configure(state="disabled")
            self._generation_sensitive_widgets = [
                self.open_graph_button,
                self.save_graph_button,
                self.validate_graph_button,
                self.apply_node_edits_button,
                self.delete_node_button,
                self.create_edge_button,
                self.remove_edge_button,
                self.enable_edge_button,
                self.disable_edge_button,
                self.set_edge_bridge_button,
                self.toggle_insert_mode_button,
                self.toggle_paint_mode_button,
                self.add_palette_color_button,
                self.group_color_combo,
                self.choose_bridge_color_button,
                self.set_start_button,
                self.set_end_button,
                self.add_via_button,
                self.clear_via_button,
                self.via_up_button,
                self.via_down_button,
                self.max_routes_entry,
                self.edge_pass_factor_entry,
                self.auto_max_output_routes_entry,
                self.auto_max_routes_per_pair_entry,
                self.auto_max_anchor_pairs_entry,
                self.auto_distance_per_frame_entry,
                self.auto_min_total_length_entry,
                self.auto_max_total_length_entry,
                self.auto_min_frame_count_entry,
                self.auto_max_frame_count_entry,
                self.auto_min_endpoint_distance_entry,
                self.auto_allowed_route_groups_listbox,
                self.auto_excluded_endpoint_groups_listbox,
                self.auto_max_search_states_entry,
                self.auto_coverage_weight_entry,
                self.auto_diversity_weight_entry,
                self.auto_anchor_weight_entry,
                self.auto_reverse_penalty_weight_entry,
                self.auto_prefer_connected_anchors_checkbutton,
                self.auto_prefer_route_diversity_checkbutton,
                self.auto_allow_reverse_direction_counterparts_checkbutton,
                self.auto_enable_global_coverage_checkbutton,
                self.planning_mode_combo,
                self.generate_routes_button,
                self.refresh_preview_button,
                self.toggle_keep_button,
                self.save_candidate_set_button,
                self.export_mission_button,
                self.export_kept_missions_button,
                self.export_preview_png_button,
                self.candidate_tree,
            ]

        def _on_right_canvas_configure(self, event) -> None:
            self.right_scroll_canvas.itemconfigure(self.right_content_window, width=event.width)

        def on_planning_mode_changed(self, _event=None) -> None:
            self._sync_planning_mode_controls()
            self._schedule_export_input_autosave()

        def _sync_planning_mode_controls(self) -> None:
            planning_mode = self.planning_mode_var.get().strip().lower()
            if planning_mode == "auto":
                self.manual_route_controls_frame.pack_forget()
                if not self.auto_route_controls_frame.winfo_ismapped():
                    self.auto_route_controls_frame.pack(fill="x", pady=(8, 0), before=self.generate_routes_button)
                self.set_start_button.state(["disabled"])
                self.set_end_button.state(["disabled"])
                self.add_via_button.state(["disabled"])
                self.clear_via_button.state(["disabled"])
                self.via_up_button.state(["disabled"])
                self.via_down_button.state(["disabled"])
                self.auto_coverage_stats_var.set("自动规划将执行全局覆盖率优化")
            else:
                self.auto_route_controls_frame.pack_forget()
                if not self.manual_route_controls_frame.winfo_ismapped():
                    self.manual_route_controls_frame.pack(fill="x", before=self.generate_routes_button)
                self.set_start_button.state(["!disabled"])
                self.set_end_button.state(["!disabled"])
                self.add_via_button.state(["!disabled"])
                self.clear_via_button.state(["!disabled"])
                self.via_up_button.state(["!disabled"])
                self.via_down_button.state(["!disabled"])
                self.auto_coverage_stats_var.set("尚未执行自动规划")

        def _bind_right_scroll_recursive(self, widget) -> None:
            if widget in {
                getattr(self, "candidate_tree", None),
                getattr(self, "candidate_tree_scrollbar", None),
                getattr(self, "auto_allowed_route_groups_listbox", None),
                getattr(self, "auto_allowed_route_groups_scrollbar", None),
                getattr(self, "auto_excluded_endpoint_groups_listbox", None),
                getattr(self, "auto_excluded_endpoint_groups_scrollbar", None),
            }:
                return
            widget.bind("<MouseWheel>", self._on_right_mouse_wheel, add="+")
            widget.bind("<Button-4>", self._on_right_mouse_wheel, add="+")
            widget.bind("<Button-5>", self._on_right_mouse_wheel, add="+")
            for child in widget.winfo_children():
                self._bind_right_scroll_recursive(child)

        def _bind_shortcuts(self) -> None:
            for sequence in ("<KeyPress-w>", "<KeyPress-W>"):
                self.root.bind_all(sequence, self.on_toggle_keep_shortcut, add="+")
            for sequence in ("<KeyPress-s>", "<KeyPress-S>"):
                self.root.bind_all(sequence, self.on_export_kept_shortcut, add="+")

        def _bind_node_editor_autosave(self) -> None:
            for widget in (
                self.name_entry,
                self.tags_entry,
                self.node_sample_radius_override_entry,
            ):
                widget.bind("<FocusOut>", self._on_node_editor_focus_out, add="+")
                widget.bind("<Return>", self._on_node_editor_return, add="+")
                widget.bind("<KP_Enter>", self._on_node_editor_return, add="+")

        def _on_node_editor_focus_out(self, _event=None) -> None:
            self._apply_current_node_edits(show_errors=False)

        def _on_node_editor_return(self, _event=None):
            self._apply_current_node_edits(show_errors=False)
            return "break"

        def _build_export_input_defaults(self, graph: RouteGraph) -> dict[str, str | bool]:
            initial_fixed_z = self._launch_args.fixed_z
            if initial_fixed_z is None:
                initial_fixed_z = graph.default_altitude
            return {
                "step_distance": str(self._launch_args.step_distance),
                "node_sample_radius": str(self._launch_args.node_sample_radius),
                "fps": str(self._launch_args.fps),
                "altitude_mode": str(self._launch_args.altitude_mode),
                "fixed_z": "" if initial_fixed_z is None else str(initial_fixed_z),
                "altitude_offset": str(self._launch_args.altitude_offset),
                "takeoff_landing_relative_z": ""
                if self._launch_args.takeoff_landing_relative_z is None
                else str(self._launch_args.takeoff_landing_relative_z),
                "takeoff_landing_step_distance": ""
                if self._launch_args.takeoff_landing_step_distance is None
                else str(self._launch_args.takeoff_landing_step_distance),
                "random_seed": ""
                if self._launch_args.random_seed is None
                else str(self._launch_args.random_seed),
                "turn_smoothing_enabled": bool(self._launch_args.turn_smoothing_enabled),
                "corner_radius": str(self._launch_args.corner_radius),
                "small_turn_yaw_blend_threshold_deg": str(
                    DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG
                ),
                "corner_min_angle_deg": str(self._launch_args.corner_min_angle_deg),
                "u_turn_threshold_deg": str(self._launch_args.u_turn_threshold_deg),
                "u_turn_transition_distance": str(self._launch_args.u_turn_transition_distance),
                "corner_max_yaw_step_deg": str(self._launch_args.corner_max_yaw_step_deg),
                "u_turn_pivot_yaw_step_deg": str(self._launch_args.u_turn_pivot_yaw_step_deg),
            }

        def _build_group_config_defaults(
            self,
            export_defaults: Mapping[str, str | bool],
        ) -> dict[str, str]:
            return {
                "node_sample_radius": str(export_defaults.get("node_sample_radius", "0")),
                "altitude_mode": str(export_defaults.get("altitude_mode", "fixed")),
                "fixed_z": str(export_defaults.get("fixed_z", "")),
                "altitude_offset": str(export_defaults.get("altitude_offset", "0")),
                "takeoff_landing_relative_z": str(export_defaults.get("takeoff_landing_relative_z", "")),
                "takeoff_landing_step_distance": str(export_defaults.get("takeoff_landing_step_distance", "")),
            }

        def _build_auto_plan_input_defaults(self) -> dict[str, str | bool | list[str]]:
            return {
                "planning_mode": "manual",
                "auto_max_output_routes": "20",
                "auto_max_routes_per_pair": "3",
                "auto_max_anchor_pairs_to_evaluate": "100",
                "auto_distance_per_frame": str(self._launch_args.step_distance),
                "auto_min_total_length": "",
                "auto_max_total_length": "",
                "auto_min_frame_count": "",
                "auto_max_frame_count": "",
                "auto_min_endpoint_distance": "0",
                "auto_max_search_states": "50000",
                "auto_coverage_weight": "1.0",
                "auto_diversity_weight": "0.45",
                "auto_anchor_weight": "0.35",
                "auto_reverse_penalty_weight": "0.2",
                "auto_prefer_connected_anchors": True,
                "auto_prefer_route_diversity": True,
                "auto_allow_reverse_direction_counterparts": True,
                "auto_enable_global_coverage": True,
                "auto_allowed_route_group_colors": [],
                "auto_excluded_endpoint_group_colors": [],
            }

        def _resolve_initial_auto_plan_inputs(self, graph: RouteGraph) -> dict[str, str | bool | list[str]]:
            resolved = self._build_auto_plan_input_defaults()
            resolved.update(read_graph_gui_auto_plan_inputs(graph.meta))
            return resolved

        def _resolve_initial_export_inputs(self, graph: RouteGraph) -> dict[str, str | bool]:
            resolved = self._build_export_input_defaults(graph)
            saved = read_graph_gui_export_inputs(graph.meta)
            resolved.update(saved)
            return resolved

        def _read_group_configs(self) -> dict[str, dict[str, str]]:
            return read_graph_group_configs(self.graph.meta)

        def _write_group_configs(self, configs: Mapping[str, Mapping[str, Any]]) -> None:
            write_graph_group_configs(self.graph.meta, configs)

        def _normalize_group_color_or_none(self, color: str | None) -> str | None:
            if color is None:
                return None
            try:
                return normalize_hex_color(color, field_name="group color")
            except GraphSchemaError:
                return None

        def _current_group_editor_color(self) -> str | None:
            return self._staged_group_color or self._active_group_color

        def _used_group_colors(self) -> list[str]:
            return derive_used_group_colors(self.graph)

        def _reconcile_group_configs(
            self,
            configs: Mapping[str, Mapping[str, str]] | None = None,
        ) -> tuple[dict[str, dict[str, str]], list[str], bool]:
            source_configs = self._read_group_configs() if configs is None else {
                color: dict(payload)
                for color, payload in configs.items()
            }
            used_colors = self._used_group_colors()
            reconciled = reconcile_group_configs_for_used_colors(
                source_configs,
                used_colors,
                default_payload=self._group_defaults,
            )
            return reconciled, used_colors, reconciled != source_configs

        def _stage_group_config(self, color: str, payload: Mapping[str, str]) -> None:
            self._staged_group_color = color
            self._staged_group_config = {str(key): str(value) for key, value in payload.items()}

        def _clear_staged_group_config(self) -> None:
            self._staged_group_color = None
            self._staged_group_config = None

        def _palette_colors(self) -> tuple[list[str], list[str]]:
            return derive_palette_colors(
                self._used_group_colors(),
                self._session_palette_colors,
            )

        def _refresh_canvas_interaction_cursor(self) -> None:
            if not hasattr(self, "canvas"):
                return
            if self._paint_mode_enabled:
                cursor = "tcross"
            elif self._insert_mode_enabled:
                cursor = "crosshair"
            else:
                cursor = ""
            self.canvas.configure(cursor=cursor)

        def _set_paint_mode_enabled(self, enabled: bool) -> None:
            enabled = bool(enabled) and self._paint_color is not None
            self._paint_mode_enabled = enabled
            self.paint_mode_button_var.set(
                "退出染色模式" if self._paint_mode_enabled else "进入染色模式"
            )
            self.paint_mode_status_var.set(
                format_paint_mode_status(self._paint_mode_enabled, self._paint_color)
            )
            self._refresh_canvas_interaction_cursor()

        def _set_insert_mode_enabled(self, enabled: bool) -> None:
            self._insert_mode_enabled = bool(enabled)
            self.insert_mode_button_var.set(
                "退出插点模式" if self._insert_mode_enabled else "进入插点模式"
            )
            self.insert_mode_status_var.set(
                format_insert_mode_status(self._insert_mode_enabled)
            )
            self._refresh_canvas_interaction_cursor()

        def _reset_secondary_canvas_interaction(self) -> None:
            self._secondary_button_press_origin = None
            self._secondary_button_press_edge_id = None
            self._secondary_button_drag_active = False
            self._pan_origin = None

        def _select_paint_color(self, color: str | None) -> None:
            normalized_color = self._normalize_group_color_or_none(color)
            self._paint_color = normalized_color
            self.paint_color_var.set(normalized_color or "未选择")
            self._set_paint_mode_enabled(self._paint_mode_enabled)

        def _on_palette_color_selected(self, color: str) -> None:
            self._select_paint_color(color)
            self._refresh_palette_controls()
            self.status_var.set(f"当前画笔颜色：{color}")

        def _render_palette_color_buttons(
            self,
            frame,
            colors: Iterable[str],
            *,
            empty_text: str,
        ) -> None:
            for child in frame.winfo_children():
                child.destroy()
            rendered = list(colors)
            if not rendered:
                tk.Label(frame, text=empty_text, bg="#f8fafc", fg="#64748b").pack(anchor="w")
                return
            for index, color in enumerate(rendered):
                button = tk.Button(
                    frame,
                    text=color,
                    command=lambda selected=color: self._on_palette_color_selected(selected),
                    bg=color,
                    fg=ideal_text_color_for_background(color),
                    activebackground=color,
                    activeforeground=ideal_text_color_for_background(color),
                    relief="sunken" if color == self._paint_color else "raised",
                    bd=3 if color == self._paint_color else 1,
                    padx=8,
                    pady=4,
                )
                row = index // 2
                column = index % 2
                button.grid(row=row, column=column, sticky="ew", padx=(0, 6), pady=(0, 6))
                frame.grid_columnconfigure(column, weight=1)

        def _refresh_palette_controls(self, *, preserve_paint_color: bool = True) -> None:
            used_colors, session_colors = self._palette_colors()
            preferred_color = (
                self._paint_color
                if preserve_paint_color and self._paint_color is not None
                else self._active_group_color
            )
            self._session_palette_colors = set(session_colors)
            next_paint_color = resolve_palette_brush_color(
                used_colors,
                session_colors,
                self._paint_color if preserve_paint_color else None,
                preferred_color=preferred_color,
            )
            self._select_paint_color(next_paint_color)
            self._render_palette_color_buttons(
                self.used_palette_colors_frame,
                used_colors,
                empty_text="暂无已使用颜色",
            )
            self._render_palette_color_buttons(
                self.session_palette_colors_frame,
                session_colors,
                empty_text="暂无会话新增颜色",
            )

        def _resolve_group_config(self, color: str | None) -> dict[str, str]:
            resolved = dict(self._group_defaults)
            if color:
                normalized_color = self._normalize_group_color_or_none(color)
                if normalized_color is not None and normalized_color == self._staged_group_color:
                    resolved.update(self._staged_group_config or {})
                else:
                    resolved.update(self._read_group_configs().get(color, {}))
            return resolved

        def _current_group_config_payload(self) -> dict[str, str]:
            return {
                "node_sample_radius": self.node_sample_radius_var.get(),
                "altitude_mode": self.altitude_mode_var.get(),
                "fixed_z": self.fixed_z_var.get(),
                "altitude_offset": self.altitude_offset_var.get(),
                "takeoff_landing_relative_z": self.takeoff_landing_relative_z_var.get(),
                "takeoff_landing_step_distance": self.takeoff_landing_step_distance_var.get(),
            }

        def _current_export_input_payload(self) -> dict[str, str | bool]:
            return {
                "step_distance": self.step_distance_var.get(),
                "fps": self.fps_var.get(),
                "random_seed": self.random_seed_var.get(),
                "turn_smoothing_enabled": bool(self.turn_smoothing_enabled_var.get()),
                "corner_radius": self.corner_radius_var.get(),
                "small_turn_yaw_blend_threshold_deg": self.small_turn_yaw_blend_threshold_deg_var.get(),
                "corner_min_angle_deg": self.corner_min_angle_deg_var.get(),
                "u_turn_threshold_deg": self.u_turn_threshold_deg_var.get(),
                "u_turn_transition_distance": self.u_turn_transition_distance_var.get(),
                "corner_max_yaw_step_deg": self.corner_max_yaw_step_deg_var.get(),
                "u_turn_pivot_yaw_step_deg": self.u_turn_pivot_yaw_step_deg_var.get(),
            }

        def _current_canvas_view_payload(self) -> dict[str, int | bool]:
            return {
                "rotation_quadrants": int(self.canvas_view_rotation_quadrants) % 4,
                "flip_horizontal": bool(self.canvas_view_flip_horizontal),
                "flip_vertical": bool(self.canvas_view_flip_vertical),
            }

        def _current_canvas_view_state(self) -> CanvasViewState:
            payload = self._current_canvas_view_payload()
            return CanvasViewState(
                rotation_quadrants=int(payload["rotation_quadrants"]),
                flip_horizontal=bool(payload["flip_horizontal"]),
                flip_vertical=bool(payload["flip_vertical"]),
            )

        def _sync_canvas_view_controls(self) -> None:
            self.canvas_view_rotation_var.set(
                f"View: {int(self.canvas_view_rotation_quadrants) * 90} deg"
            )
            self.canvas_view_flip_horizontal_var.set(bool(self.canvas_view_flip_horizontal))
            self.canvas_view_flip_vertical_var.set(bool(self.canvas_view_flip_vertical))

        def _sync_export_inputs_to_graph_meta(self) -> bool:
            current = self._current_export_input_payload()
            existing = read_graph_gui_export_inputs(self.graph.meta)
            current_auto = self._collect_auto_plan_inputs()
            existing_auto = read_graph_gui_auto_plan_inputs(self.graph.meta)
            group_changed = self._sync_current_group_config_to_graph_meta()
            changed = group_changed
            if existing != current:
                write_graph_gui_export_inputs(self.graph.meta, current)
                changed = True
            if existing_auto != current_auto:
                write_graph_gui_auto_plan_inputs(self.graph.meta, current_auto)
                changed = True
            return changed

        def _sync_current_group_config_to_graph_meta(self) -> bool:
            result = sync_group_config_state(
                self._read_group_configs(),
                self._used_group_colors(),
                default_payload=self._group_defaults,
                active_group_color=self._active_group_color,
                staged_group_color=self._staged_group_color,
                staged_group_config=self._staged_group_config,
                current_payload=self._current_group_config_payload(),
            )
            self._staged_group_color = result.staged_color
            self._staged_group_config = (
                None
                if result.staged_config is None
                else dict(result.staged_config)
            )
            if result.meta_changed:
                self._write_group_configs(result.configs)
            return result.meta_changed

        def _edge_group_colors(self) -> list[str]:
            return self._used_group_colors()

        def _format_group_display_label(self, color: str) -> str:
            group_label = self._read_group_configs().get(color, {}).get(GROUP_CONFIG_LABEL_KEY, "").strip()
            if group_label and group_label != color:
                return f"{group_label} ({color})"
            return color

        def _format_group_combo_label(self, color: str) -> str:
            return color

        def _refresh_auto_allowed_route_group_controls(self) -> None:
            if not hasattr(self, "auto_allowed_route_groups_listbox"):
                return
            used_colors = self._used_group_colors()
            preserved_colors = normalize_auto_group_selection(
                used_colors,
                self._auto_allowed_route_group_colors,
            )
            if preserved_colors != self._auto_allowed_route_group_colors:
                self._auto_allowed_route_group_colors = preserved_colors
                self._export_inputs_dirty = True
                if not self._suspend_export_input_autosave:
                    self._schedule_export_input_autosave()

            self._auto_allowed_group_label_lookup = {
                self._format_group_display_label(color): color
                for color in used_colors
            }
            self.auto_allowed_route_groups_listbox.configure(state="normal")
            self.auto_allowed_route_groups_listbox.configure(
                height=min(max(len(used_colors), 4), 8)
            )
            self.auto_allowed_route_groups_listbox.delete(0, "end")
            for label in self._auto_allowed_group_label_lookup:
                self.auto_allowed_route_groups_listbox.insert("end", label)
            selected_colors = set(self._auto_allowed_route_group_colors)
            for index, label in enumerate(self._auto_allowed_group_label_lookup):
                color = self._auto_allowed_group_label_lookup[label]
                if color in selected_colors:
                    self.auto_allowed_route_groups_listbox.selection_set(index)
            self.auto_allowed_route_groups_status_var.set(
                format_auto_allowed_route_groups_status(
                    selected_count=len(self._auto_allowed_route_group_colors),
                    available_count=len(used_colors),
                )
            )
            if not used_colors:
                self.auto_allowed_route_groups_listbox.configure(state="disabled")

        def _refresh_auto_endpoint_group_controls(self) -> None:
            if not hasattr(self, "auto_excluded_endpoint_groups_listbox"):
                return
            used_colors = self._used_group_colors()
            available_colors = resolve_auto_endpoint_group_choices(
                used_colors,
                self._auto_allowed_route_group_colors,
            )
            preserved_colors = normalize_auto_group_selection(
                available_colors,
                self._auto_excluded_endpoint_group_colors,
            )
            if preserved_colors != self._auto_excluded_endpoint_group_colors:
                self._auto_excluded_endpoint_group_colors = preserved_colors
                self._export_inputs_dirty = True
                if not self._suspend_export_input_autosave:
                    self._schedule_export_input_autosave()

            self._auto_endpoint_group_label_lookup = {
                self._format_group_display_label(color): color
                for color in available_colors
            }
            self.auto_excluded_endpoint_groups_listbox.configure(state="normal")
            self.auto_excluded_endpoint_groups_listbox.configure(
                height=min(max(len(available_colors), 4), 8)
            )
            self.auto_excluded_endpoint_groups_listbox.delete(0, "end")
            for label in self._auto_endpoint_group_label_lookup:
                self.auto_excluded_endpoint_groups_listbox.insert("end", label)
            selected_colors = set(self._auto_excluded_endpoint_group_colors)
            for index, label in enumerate(self._auto_endpoint_group_label_lookup):
                color = self._auto_endpoint_group_label_lookup[label]
                if color in selected_colors:
                    self.auto_excluded_endpoint_groups_listbox.selection_set(index)
            self.auto_excluded_endpoint_groups_status_var.set(
                format_auto_excluded_endpoint_groups_status(
                    selected_count=len(self._auto_excluded_endpoint_group_colors),
                    available_count=len(available_colors),
                )
            )
            if not available_colors:
                self.auto_excluded_endpoint_groups_listbox.configure(state="disabled")

        def on_auto_allowed_route_groups_changed(self, _event=None) -> None:
            if not hasattr(self, "auto_allowed_route_groups_listbox"):
                return
            selected_colors: list[str] = []
            seen_colors: set[str] = set()
            for index in self.auto_allowed_route_groups_listbox.curselection():
                try:
                    label = str(self.auto_allowed_route_groups_listbox.get(index))
                except Exception:
                    continue
                color = self._auto_allowed_group_label_lookup.get(label)
                if color is None or color in seen_colors:
                    continue
                seen_colors.add(color)
                selected_colors.append(color)
            if selected_colors == self._auto_allowed_route_group_colors:
                return
            self._auto_allowed_route_group_colors = selected_colors
            self.auto_allowed_route_groups_status_var.set(
                format_auto_allowed_route_groups_status(
                    selected_count=len(self._auto_allowed_route_group_colors),
                    available_count=len(self._auto_allowed_group_label_lookup),
                )
            )
            self._refresh_auto_endpoint_group_controls()
            self._export_inputs_dirty = True
            if not self._suspend_export_input_autosave:
                self._schedule_export_input_autosave()

        def on_auto_excluded_endpoint_groups_changed(self, _event=None) -> None:
            if not hasattr(self, "auto_excluded_endpoint_groups_listbox"):
                return
            selected_colors: list[str] = []
            seen_colors: set[str] = set()
            for index in self.auto_excluded_endpoint_groups_listbox.curselection():
                try:
                    label = str(self.auto_excluded_endpoint_groups_listbox.get(index))
                except Exception:
                    continue
                color = self._auto_endpoint_group_label_lookup.get(label)
                if color is None or color in seen_colors:
                    continue
                seen_colors.add(color)
                selected_colors.append(color)
            if selected_colors == self._auto_excluded_endpoint_group_colors:
                return
            self._auto_excluded_endpoint_group_colors = selected_colors
            self.auto_excluded_endpoint_groups_status_var.set(
                format_auto_excluded_endpoint_groups_status(
                    selected_count=len(self._auto_excluded_endpoint_group_colors),
                    available_count=len(self._auto_endpoint_group_label_lookup),
                )
            )
            self._export_inputs_dirty = True
            if not self._suspend_export_input_autosave:
                self._schedule_export_input_autosave()

        def _on_auto_allowed_route_groups_mouse_wheel(self, event) -> str:
            delta_units = self._scroll_units_from_event(event)
            if delta_units == 0:
                return "break"
            first, last = self.auto_allowed_route_groups_listbox.yview()
            if first <= 0.0 and last >= 1.0:
                return self._on_right_mouse_wheel(event)
            self.auto_allowed_route_groups_listbox.yview_scroll(delta_units, "units")
            return "break"

        def _on_auto_excluded_endpoint_groups_mouse_wheel(self, event) -> str:
            delta_units = self._scroll_units_from_event(event)
            if delta_units == 0:
                return "break"
            first, last = self.auto_excluded_endpoint_groups_listbox.yview()
            if first <= 0.0 and last >= 1.0:
                return self._on_right_mouse_wheel(event)
            self.auto_excluded_endpoint_groups_listbox.yview_scroll(delta_units, "units")
            return "break"

        def _refresh_group_controls(self, *, preserve_current: bool = True) -> None:
            if not preserve_current:
                self._active_group_color = None
                self._clear_staged_group_config()
            configs, colors, configs_changed = self._reconcile_group_configs()
            if configs_changed:
                self._write_group_configs(configs)
                self._export_inputs_dirty = True
                if not self._suspend_export_input_autosave:
                    self._schedule_export_input_autosave()
            control_state = build_group_control_state(
                colors,
                active_group_color=self._normalize_group_color_or_none(self._active_group_color),
                staged_group_color=self._normalize_group_color_or_none(self._staged_group_color),
            )
            if control_state.staged_color is None:
                self._clear_staged_group_config()
            self._group_combo_labels = [
                self._format_group_combo_label(color)
                for color in control_state.used_colors
            ]
            self._group_combo_color_lookup = {
                label: color
                for label, color in zip(self._group_combo_labels, control_state.used_colors, strict=False)
            }
            self.group_color_combo.configure(values=self._group_combo_labels)
            self._suspend_group_selection = True
            try:
                self.active_group_color_var.set(control_state.combo_value)
            finally:
                self._suspend_group_selection = False
            self._active_group_color = control_state.selected_color
            self.staged_group_status_var.set(control_state.staged_label)
            if control_state.staged_color is not None and self._staged_group_config is None:
                self._stage_group_config(control_state.staged_color, self._group_defaults)
            if control_state.editor_color is not None:
                self._load_group_config_into_vars(control_state.editor_color)
            else:
                self._load_group_config_into_vars(None)
            self.bridge_color_var.set(resolve_bridge_color(self.graph.meta, default_color=DEFAULT_BRIDGE_COLOR))
            if hasattr(self, "used_palette_colors_frame"):
                self._refresh_palette_controls(preserve_paint_color=True)
            self._refresh_auto_allowed_route_group_controls()
            self._refresh_auto_endpoint_group_controls()
            self._refresh_edge_controls()
            if hasattr(self, "canvas"):
                self.refresh_canvas()

        def _load_group_config_into_vars(self, color: str | None) -> None:
            resolved = self._resolve_group_config(color)
            self._cancel_export_input_autosave()
            self._suspend_export_input_autosave = True
            try:
                self.node_sample_radius_var.set(str(resolved["node_sample_radius"]))
                self.altitude_mode_var.set(str(resolved["altitude_mode"]))
                self.fixed_z_var.set(str(resolved["fixed_z"]))
                self.altitude_offset_var.set(str(resolved["altitude_offset"]))
                self.takeoff_landing_relative_z_var.set(str(resolved["takeoff_landing_relative_z"]))
                self.takeoff_landing_step_distance_var.set(str(resolved["takeoff_landing_step_distance"]))
            finally:
                self._suspend_export_input_autosave = False
            self._sync_export_controls()

        def _select_group_color(self, color: str | None, *, preserve_unsaved: bool = True) -> None:
            if preserve_unsaved:
                self._sync_current_group_config_to_graph_meta()
            normalized_color = self._normalize_group_color_or_none(color)
            used_colors = set(self._used_group_colors())
            if normalized_color is not None and normalized_color not in used_colors:
                if normalized_color == self._staged_group_color and self._staged_group_config is not None:
                    staged_payload = dict(self._staged_group_config)
                else:
                    staged_payload = dict(self._group_defaults)
                self._active_group_color = None
                self._stage_group_config(normalized_color, staged_payload)
            else:
                self._active_group_color = normalized_color
                self._clear_staged_group_config()
            self._refresh_group_controls(preserve_current=True)

        def _sync_canvas_view_to_graph_meta(self) -> bool:
            current = self._current_canvas_view_payload()
            return sync_graph_gui_canvas_view(self.graph.meta, current)

        def _register_export_input_persistence_traces(self) -> None:
            export_vars = [
                self.step_distance_var,
                self.node_sample_radius_var,
                self.fps_var,
                self.altitude_mode_var,
                self.fixed_z_var,
                self.altitude_offset_var,
                self.takeoff_landing_relative_z_var,
                self.takeoff_landing_step_distance_var,
                self.random_seed_var,
                self.turn_smoothing_enabled_var,
                self.corner_radius_var,
                self.corner_min_angle_deg_var,
                self.u_turn_threshold_deg_var,
                self.u_turn_transition_distance_var,
                self.corner_max_yaw_step_deg_var,
                self.u_turn_pivot_yaw_step_deg_var,
                self.auto_max_output_routes_var,
                self.auto_max_routes_per_pair_var,
                self.auto_max_anchor_pairs_var,
                self.auto_distance_per_frame_var,
                self.auto_min_total_length_var,
                self.auto_max_total_length_var,
                self.auto_min_frame_count_var,
                self.auto_max_frame_count_var,
                self.auto_min_endpoint_distance_var,
                self.auto_max_search_states_var,
                self.auto_coverage_weight_var,
                self.auto_diversity_weight_var,
                self.auto_anchor_weight_var,
                self.auto_reverse_penalty_weight_var,
                self.auto_prefer_connected_anchors_var,
                self.auto_prefer_route_diversity_var,
                self.auto_allow_reverse_direction_counterparts_var,
                self.auto_enable_global_coverage_var,
            ]
            for variable in export_vars:
                token = variable.trace_add("write", self._on_export_inputs_changed)
                self._export_inputs_trace_tokens.append((variable, token))

        def _on_export_inputs_changed(self, *_args) -> None:
            if self._suspend_export_input_autosave:
                return
            self._export_inputs_dirty = True
            self._schedule_export_input_autosave()

        def _cancel_export_input_autosave(self) -> None:
            if self._export_input_autosave_after_id is None:
                return
            try:
                self.root.after_cancel(self._export_input_autosave_after_id)
            except Exception:
                pass
            self._export_input_autosave_after_id = None

        def _cancel_canvas_view_autosave(self) -> None:
            if self._canvas_view_autosave_after_id is None:
                return
            try:
                self.root.after_cancel(self._canvas_view_autosave_after_id)
            except Exception:
                pass
            self._canvas_view_autosave_after_id = None

        def _schedule_export_input_autosave(self) -> None:
            self._cancel_export_input_autosave()
            self._export_input_autosave_after_id = self.root.after(
                GRAPH_GUI_EXPORT_INPUT_AUTOSAVE_DELAY_MS,
                lambda: self._flush_export_input_autosave(force=False),
            )

        def _schedule_canvas_view_autosave(self) -> None:
            self._cancel_canvas_view_autosave()
            self._canvas_view_autosave_after_id = self.root.after(
                GRAPH_GUI_CANVAS_VIEW_AUTOSAVE_DELAY_MS,
                lambda: self._flush_canvas_view_autosave(force=False),
            )

        def _flush_graph_meta_autosave(self, *, force: bool) -> bool:
            self._cancel_export_input_autosave()
            self._cancel_canvas_view_autosave()
            if not force and not self._export_inputs_dirty and not self._canvas_view_dirty:
                return False
            if self.graph_path is None:
                return False
            export_inputs_dirty = self._export_inputs_dirty
            canvas_view_dirty = self._canvas_view_dirty
            changed = False
            if export_inputs_dirty:
                changed = self._sync_export_inputs_to_graph_meta() or changed
            if canvas_view_dirty:
                changed = self._sync_canvas_view_to_graph_meta() or changed
            if not changed:
                self._export_inputs_dirty = False
                self._canvas_view_dirty = False
                return False
            try:
                self.editor.save(self.graph_path)
            except GraphSchemaError as exc:
                self.log(f"GUI state autosave failed: {exc}")
                return False
            except OSError as exc:
                self.log(f"GUI state autosave failed: {exc}")
                return False
            self._export_inputs_dirty = False
            self._canvas_view_dirty = False
            return True

        def _flush_export_input_autosave(self, *, force: bool) -> bool:
            return self._flush_graph_meta_autosave(force=force)

        def _flush_canvas_view_autosave(self, *, force: bool) -> bool:
            return self._flush_graph_meta_autosave(force=force)

        def _load_export_inputs_from_graph(self) -> None:
            resolved = self._resolve_initial_export_inputs(self.graph)
            auto_resolved = self._resolve_initial_auto_plan_inputs(self.graph)
            self._cancel_export_input_autosave()
            self._suspend_export_input_autosave = True
            try:
                self.step_distance_var.set(str(resolved["step_distance"]))
                self.fps_var.set(str(resolved["fps"]))
                self.random_seed_var.set(str(resolved["random_seed"]))
                self.turn_smoothing_enabled_var.set(bool(resolved["turn_smoothing_enabled"]))
                self.corner_radius_var.set(str(resolved["corner_radius"]))
                self.corner_min_angle_deg_var.set(str(resolved["corner_min_angle_deg"]))
                self.u_turn_threshold_deg_var.set(str(resolved["u_turn_threshold_deg"]))
                self.u_turn_transition_distance_var.set(str(resolved["u_turn_transition_distance"]))
                self.corner_max_yaw_step_deg_var.set(str(resolved["corner_max_yaw_step_deg"]))
                self.u_turn_pivot_yaw_step_deg_var.set(str(resolved["u_turn_pivot_yaw_step_deg"]))
                self.planning_mode_var.set(str(auto_resolved["planning_mode"]))
                self.auto_max_output_routes_var.set(str(auto_resolved["auto_max_output_routes"]))
                self.auto_max_routes_per_pair_var.set(str(auto_resolved["auto_max_routes_per_pair"]))
                self.auto_max_anchor_pairs_var.set(str(auto_resolved["auto_max_anchor_pairs_to_evaluate"]))
                self.auto_distance_per_frame_var.set(str(auto_resolved["auto_distance_per_frame"]))
                self.auto_min_total_length_var.set(str(auto_resolved["auto_min_total_length"]))
                self.auto_max_total_length_var.set(str(auto_resolved["auto_max_total_length"]))
                self.auto_min_frame_count_var.set(str(auto_resolved["auto_min_frame_count"]))
                self.auto_max_frame_count_var.set(str(auto_resolved["auto_max_frame_count"]))
                self.auto_min_endpoint_distance_var.set(str(auto_resolved["auto_min_endpoint_distance"]))
                self.auto_max_search_states_var.set(str(auto_resolved["auto_max_search_states"]))
                self.auto_coverage_weight_var.set(str(auto_resolved["auto_coverage_weight"]))
                self.auto_diversity_weight_var.set(str(auto_resolved["auto_diversity_weight"]))
                self.auto_anchor_weight_var.set(str(auto_resolved["auto_anchor_weight"]))
                self.auto_reverse_penalty_weight_var.set(str(auto_resolved["auto_reverse_penalty_weight"]))
                self.auto_prefer_connected_anchors_var.set(bool(auto_resolved["auto_prefer_connected_anchors"]))
                self.auto_prefer_route_diversity_var.set(bool(auto_resolved["auto_prefer_route_diversity"]))
                self.auto_allow_reverse_direction_counterparts_var.set(
                    bool(auto_resolved["auto_allow_reverse_direction_counterparts"])
                )
                self.auto_enable_global_coverage_var.set(bool(auto_resolved["auto_enable_global_coverage"]))
                self._auto_allowed_route_group_colors = [
                    str(color) for color in auto_resolved["auto_allowed_route_group_colors"]
                ]
                self._auto_excluded_endpoint_group_colors = [
                    str(color) for color in auto_resolved["auto_excluded_endpoint_group_colors"]
                ]
            finally:
                self._suspend_export_input_autosave = False
            self._group_defaults = self._build_group_config_defaults(resolved)
            self._refresh_group_controls(preserve_current=False)
            self._sync_planning_mode_controls()
            self._export_inputs_dirty = False

        def _load_canvas_view_from_graph(self, *, reset_pan_zoom: bool) -> None:
            resolved = resolve_graph_gui_canvas_view(self.graph.meta)
            self._cancel_canvas_view_autosave()
            self._reset_secondary_canvas_interaction()
            self.canvas_view_rotation_quadrants = int(resolved["rotation_quadrants"])
            self.canvas_view_flip_horizontal = bool(resolved["flip_horizontal"])
            self.canvas_view_flip_vertical = bool(resolved["flip_vertical"])
            self._sync_canvas_view_controls()
            if reset_pan_zoom:
                self.zoom = 1.0
                self.pan_x = 0.0
                self.pan_y = 0.0
            self._canvas_view_dirty = False

        def _focused_widget_blocks_shortcuts(self) -> bool:
            focus_widget = self.root.focus_get()
            if focus_widget is None:
                return False
            return focus_widget.winfo_class() in {
                "Entry",
                "TEntry",
                "Text",
                "TCombobox",
                "Spinbox",
            }

        def _should_ignore_shortcut(self, event) -> bool:
            if self._focused_widget_blocks_shortcuts():
                return True
            if getattr(event, "state", 0) & 0x000C:
                return True
            return False

        def on_toggle_keep_shortcut(self, event):
            if self._should_ignore_shortcut(event):
                return None
            self._debug_log("Shortcut triggered: toggle keep")
            self.toggle_keep_current_candidate()
            return "break"

        def on_export_kept_shortcut(self, event):
            if self._should_ignore_shortcut(event):
                return None
            self._debug_log("Shortcut triggered: export kept missions")
            self.export_kept_missions_ui()
            return "break"

        def _scroll_units_from_event(self, event) -> int:
            if getattr(event, "num", None) == 4:
                return -1
            if getattr(event, "num", None) == 5:
                return 1
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return 0
            delta_units = int(-1 * (delta / 120))
            if delta_units == 0:
                return -1 if delta > 0 else 1
            return delta_units

        def _on_right_mouse_wheel(self, event) -> str:
            delta_units = self._scroll_units_from_event(event)
            if delta_units == 0:
                return "break"
            self.right_scroll_canvas.yview_scroll(delta_units, "units")
            return "break"

        def _on_candidate_tree_mouse_wheel(self, event) -> str:
            delta_units = self._scroll_units_from_event(event)
            if delta_units == 0:
                return "break"
            first, last = self.candidate_tree.yview()
            if first <= 0.0 and last >= 1.0:
                return self._on_right_mouse_wheel(event)
            self.candidate_tree.yview_scroll(delta_units, "units")
            return "break"

        def log(self, message: str) -> None:
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", f"{message}\n")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")
            self.status_var.set(message)
            self._debug_log(f"UI log: {message}")

        def _debug_log(self, message: str) -> None:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            line = f"[{timestamp}] {message}\n"
            try:
                with self._debug_log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
            except OSError:
                pass

        def _schedule_ui_heartbeat(self) -> None:
            if self._ui_heartbeat_after_id is None:
                self._ui_heartbeat_after_id = self.root.after(UI_HEARTBEAT_MS, self._ui_heartbeat)

        def _ui_heartbeat(self) -> None:
            self._ui_heartbeat_after_id = None
            self._last_ui_heartbeat = time.monotonic()
            self._schedule_ui_heartbeat()

        def _cancel_ui_heartbeat(self) -> None:
            if self._ui_heartbeat_after_id is None:
                return
            try:
                self.root.after_cancel(self._ui_heartbeat_after_id)
            except Exception:
                pass
            self._ui_heartbeat_after_id = None

        def _dump_thread_stacks(self, reason: str) -> None:
            frames = sys._current_frames()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            lines = [f"\n===== {timestamp} {reason} =====\n"]
            for thread in threading.enumerate():
                frame = frames.get(thread.ident)
                lines.append(
                    f"--- Thread name={thread.name!r} ident={thread.ident} daemon={thread.daemon} ---\n"
                )
                if frame is None:
                    lines.append("No frame available\n")
                    continue
                lines.extend(traceback.format_stack(frame))
            try:
                with self._stackdump_path.open("a", encoding="utf-8") as handle:
                    handle.writelines(lines)
            except OSError:
                pass

        def _watchdog_loop(self) -> None:
            while not self._watchdog_stop_event.wait(0.5):
                stall_seconds = time.monotonic() - self._last_ui_heartbeat
                if stall_seconds >= UI_STALL_DUMP_SECONDS:
                    if not self._watchdog_dumped:
                        self._watchdog_dumped = True
                        self._debug_log(f"UI stall detected: {stall_seconds:.2f}s")
                        self._dump_thread_stacks(f"UI stall {stall_seconds:.2f}s")
                else:
                    self._watchdog_dumped = False

        def _register_preview_invalidation_traces(self) -> None:
            preview_vars = [
                self.step_distance_var,
                self.node_sample_radius_var,
                self.fps_var,
                self.altitude_mode_var,
                self.fixed_z_var,
                self.altitude_offset_var,
                self.takeoff_landing_relative_z_var,
                self.takeoff_landing_step_distance_var,
                self.random_seed_var,
                self.turn_smoothing_enabled_var,
                self.corner_radius_var,
                self.corner_min_angle_deg_var,
                self.u_turn_threshold_deg_var,
                self.u_turn_transition_distance_var,
                self.corner_max_yaw_step_deg_var,
                self.u_turn_pivot_yaw_step_deg_var,
            ]
            for variable in preview_vars:
                token = variable.trace_add("write", self._on_preview_inputs_changed)
                self._preview_trace_tokens.append((variable, token))

        def _on_preview_inputs_changed(self, *_args) -> None:
            if self.current_plan is None or self.current_candidate_id is None:
                return
            if self._restore_cached_preview():
                self._cancel_preview_refresh()
                self._refresh_preview_status()
                self.refresh_canvas()
                return
            self.preview_state.mark_stale()
            self._refresh_preview_status()
            self.refresh_canvas()
            self._schedule_preview_refresh(delay_ms=PREVIEW_AUTO_REFRESH_DELAY_MS, show_errors=False)

        def _refresh_preview_status(self) -> None:
            self.preview_status_var.set(self.preview_state.status_text())

        def _preview_cache_key(
            self,
            *,
            candidate_id: str | None = None,
        ) -> tuple[str, tuple[Any, ...]] | None:
            resolved_candidate_id = candidate_id or self.current_candidate_id
            if resolved_candidate_id is None:
                return None
            sync_result = sync_group_config_state(
                self._read_group_configs(),
                self._used_group_colors(),
                default_payload=self._group_defaults,
                active_group_color=self._active_group_color,
                staged_group_color=self._staged_group_color,
                staged_group_config=self._staged_group_config,
                current_payload=self._current_group_config_payload(),
            )
            return (
                resolved_candidate_id,
                (
                    self.step_distance_var.get().strip(),
                    self.fps_var.get().strip(),
                    self.random_seed_var.get().strip(),
                    bool(self.turn_smoothing_enabled_var.get()),
                    self.corner_radius_var.get().strip(),
                    self.corner_min_angle_deg_var.get().strip(),
                    self.u_turn_threshold_deg_var.get().strip(),
                    self.u_turn_transition_distance_var.get().strip(),
                    self.corner_max_yaw_step_deg_var.get().strip(),
                    self.u_turn_pivot_yaw_step_deg_var.get().strip(),
                    json.dumps(sync_result.configs, sort_keys=True, ensure_ascii=False),
                ),
            )

        def _cache_preview(self, mission: dict[str, Any]) -> None:
            cache_key = self._preview_cache_key()
            if cache_key is None:
                return
            self._preview_cache[cache_key] = mission

        def _set_preview(self, mission: dict[str, Any]) -> None:
            self.preview_state.set_preview(mission)
            self._cache_preview(mission)

        def _restore_cached_preview(self, *, candidate_id: str | None = None) -> bool:
            cache_key = self._preview_cache_key(candidate_id=candidate_id)
            if cache_key is None:
                return False
            mission = self._preview_cache.get(cache_key)
            if mission is None:
                return False
            self.preview_state.set_preview(mission)
            return True

        def _cancel_preview_refresh(self) -> None:
            if self._preview_refresh_after_id is None:
                return
            try:
                self.root.after_cancel(self._preview_refresh_after_id)
            except Exception:
                pass
            self._preview_refresh_after_id = None

        def _run_preview_refresh(self, *, show_errors: bool) -> None:
            self._preview_refresh_after_id = None
            if self.refresh_mission_preview(show_errors=show_errors):
                self.refresh_canvas()

        def _schedule_preview_refresh(self, *, delay_ms: int, show_errors: bool) -> None:
            if self.current_plan is None:
                return
            self._cancel_preview_refresh()
            self._preview_refresh_after_id = self.root.after(
                max(int(delay_ms), 0),
                lambda: self._run_preview_refresh(show_errors=show_errors),
            )

        def _set_generation_controls_enabled(self, enabled: bool) -> None:
            if enabled:
                self.generate_routes_button.state(["!disabled"])
            else:
                self.generate_routes_button.state(["disabled"])

        def _set_route_generation_status(self, message: str) -> None:
            self.route_generation_status_var.set(message)

        def _update_route_generation_progress(self, progress: dict[str, Any]) -> None:
            self._last_route_progress = progress
            if progress.get("progress_kind") == "auto":
                maximum = max(int(progress.get("max_pairs_to_evaluate", 1)), 1)
                value = min(int(progress.get("pairs_considered", 0)), maximum)
                self.route_generation_progress.configure(mode="determinate", maximum=maximum, value=value)
                phase = str(progress.get("phase", "auto"))
                done = bool(progress.get("done"))
                prefix = "自动规划完成" if done else "自动规划中"
                self._set_route_generation_status(
                    f"{prefix} [{phase}] 已评估 {progress.get('pairs_considered', 0)} / {progress.get('max_pairs_to_evaluate', 0)} 对，"
                    f"候选池 {progress.get('candidate_pool_size', 0)} 条，已选 {progress.get('selected_routes', 0)} / {progress.get('max_output_routes', 0)} 条"
                )
                return
            maximum = max(int(progress["max_search_states"]), 1)
            value = min(int(progress["expansions"]), maximum)
            self.route_generation_progress.configure(mode="determinate", maximum=maximum, value=value)
            if progress["done"]:
                if progress["truncated"]:
                    prefix = "搜索已截断"
                else:
                    prefix = "搜索完成"
            else:
                prefix = "正在生成候选轨迹..."
            self._set_route_generation_status(
                f"{prefix} 已扩展 {progress['expansions']} / {progress['max_search_states']}，"
                f"已找到 {progress['candidates_found']} 条候选"
            )

        def _reset_route_generation_progress(self, message: str = "就绪") -> None:
            self._last_route_progress = None
            self.route_generation_progress.configure(mode="determinate", maximum=1.0, value=0.0)
            self._set_route_generation_status(message)

        def _schedule_route_generation_poll(self) -> None:
            if self._route_generation_poll_after_id is None:
                self._route_generation_poll_after_id = self.root.after(
                    ROUTE_GENERATION_POLL_MS,
                    self._poll_route_generation_queue,
                )

        def _cancel_route_generation_poll(self) -> None:
            if self._route_generation_poll_after_id is None:
                return
            try:
                self.root.after_cancel(self._route_generation_poll_after_id)
            except Exception:
                pass
            self._route_generation_poll_after_id = None

        def _begin_route_generation(
            self,
            *,
            graph_payload: dict[str, Any],
            start_node: str,
            via_nodes: list[str],
            end_node: str,
            max_routes: int,
            max_edge_pass_factor: float,
            min_total_length: float | None,
            max_total_length: float | None,
        ) -> None:
            self._debug_log(
                f"_begin_route_generation route={' -> '.join([start_node, *via_nodes, end_node])}"
            )
            self._route_generation_summary = " -> ".join([start_node, *via_nodes, end_node])
            self._finish_route_generation(terminate=True)
            self._set_generation_controls_enabled(False)
            self._reset_route_generation_progress("正在生成候选轨迹...")
            task_payload = {
                "graph": graph_payload,
                "start": start_node,
                "via": list(via_nodes),
                "end": end_node,
                "max_routes": int(max_routes),
                "max_edge_pass_factor": float(max_edge_pass_factor),
                "min_total_length": None if min_total_length is None else float(min_total_length),
                "max_total_length": None if max_total_length is None else float(max_total_length),
                "max_search_states": 50000,
                "progress_interval": 250,
            }
            try:
                record = self._route_generation_job_service.create_worker_job(
                    graph_ref=str(self.graph_path or self.graph.graph_name),
                    task_payload=task_payload,
                    python_executable=sys.executable,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as exc:
                self._set_generation_controls_enabled(True)
                self._handle_route_generation_error(f"启动后台进程失败：{exc}")
                return
            self._route_generation_job_record = record
            self._route_generation_job_id = record.job_id
            self._route_generation_active = True
            self._debug_log(
                f"route generation job created job_id={record.job_id} runtime_dir={record.runtime_dir}"
            )
            self._schedule_route_generation_poll()
            self._debug_log(f"_begin_route_generation scheduled job_id={record.job_id}")

        def _begin_auto_route_generation(
            self,
            *,
            graph_payload: dict[str, Any],
            auto_config: AutoPlanningConfig,
        ) -> None:
            self._route_generation_summary = "自动规划"
            self._finish_route_generation(terminate=True)
            self._set_generation_controls_enabled(False)
            self._reset_route_generation_progress("正在执行自动规划...")
            task_payload = {
                "graph": graph_payload,
                "planning_mode": "auto",
                "auto_config": {
                    "max_output_routes": int(auto_config.max_output_routes),
                    "max_routes_per_pair": int(auto_config.max_routes_per_pair),
                    "max_anchor_pairs_to_evaluate": int(auto_config.max_anchor_pairs_to_evaluate),
                    "min_frame_count": auto_config.min_frame_count,
                    "max_frame_count": auto_config.max_frame_count,
                    "distance_per_frame": float(auto_config.distance_per_frame),
                    "min_total_length": auto_config.min_total_length,
                    "max_total_length": auto_config.max_total_length,
                    "max_edge_pass_factor": float(auto_config.max_edge_pass_factor),
                    "max_search_states": int(auto_config.max_search_states),
                    "min_endpoint_distance": float(auto_config.min_endpoint_distance),
                    "prefer_connected_anchors": bool(auto_config.prefer_connected_anchors),
                    "prefer_route_diversity": bool(auto_config.prefer_route_diversity),
                    "allow_reverse_direction_counterparts": bool(auto_config.allow_reverse_direction_counterparts),
                    "coverage_weight": float(auto_config.coverage_weight),
                    "diversity_weight": float(auto_config.diversity_weight),
                    "anchor_weight": float(auto_config.anchor_weight),
                    "reverse_penalty_weight": float(auto_config.reverse_penalty_weight),
                    "allowed_route_group_colors": list(auto_config.allowed_route_group_colors),
                    "excluded_endpoint_group_colors": list(auto_config.excluded_endpoint_group_colors),
                    "export_config": (
                        None
                        if auto_config.export_config is None
                        else auto_config.export_config.to_mapping()
                    ),
                },
            }
            try:
                record = self._route_generation_job_service.create_worker_job(
                    graph_ref=str(self.graph_path or self.graph.graph_name),
                    task_payload=task_payload,
                    python_executable=sys.executable,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as exc:
                self._set_generation_controls_enabled(True)
                self._handle_route_generation_error(f"启动后台进程失败：{exc}")
                return
            self._route_generation_job_record = record
            self._route_generation_job_id = record.job_id
            self._route_generation_active = True
            self._debug_log(
                f"auto route generation job created job_id={record.job_id} runtime_dir={record.runtime_dir}"
            )
            self._schedule_route_generation_poll()

        def _handle_route_generation_error(self, error_message: str) -> None:
            self._debug_log(f"generation error: {error_message}")
            self._finish_route_generation()
            self._clear_candidates()
            self.refresh_candidate_tree()
            self.refresh_selection_panel()
            self.refresh_canvas()
            self._reset_route_generation_progress(f"生成失败：{error_message}")
            messagebox.showerror("候选轨迹生成", error_message)
            self.log(f"候选轨迹生成失败：{error_message}")

        def _filters_require_auto_keep(self) -> bool:
            return filters_require_auto_keep(
                min_total_length_text=self.min_total_length_var.get(),
                max_total_length_text=self.max_total_length_var.get(),
                min_frame_count_text=self.min_frame_count_var.get(),
                max_frame_count_text=self.max_frame_count_var.get(),
            )

        def _apply_auto_keep_to_candidate_set(self, candidate_set: RouteCandidateSet) -> None:
            for candidate in candidate_set.candidates:
                candidate.selected = True
            candidate_set.sync_selected_ids()
            candidate_set.meta["auto_keep_candidates"] = True

        def _finish_route_generation(self, *, terminate: bool = False) -> None:
            record = self._route_generation_job_record
            if record is not None:
                self._route_generation_job_service.discard_job(
                    record.job_id,
                    terminate=terminate,
                )
            self._route_generation_job_record = None
            self._route_generation_active = False
            self._set_generation_controls_enabled(True)

        def _handle_route_generation_success(self, candidate_set: RouteCandidateSet) -> None:
            self._debug_log(
                f"generation success count={len(candidate_set.candidates)} truncated={candidate_set.meta.get('truncated')}"
            )
            self._finish_route_generation()
            self._preview_cache.clear()
            if candidate_set.meta.get("planning_mode") != "auto":
                candidate_set = self._apply_generation_filters(candidate_set)
            self._annotate_candidate_frame_counts(candidate_set)
            if candidate_set.meta.get("planning_mode") == "auto":
                self._update_auto_coverage_stats(candidate_set)
            elif self._filters_require_auto_keep():
                self._apply_auto_keep_to_candidate_set(candidate_set)
            self.current_candidate_set = candidate_set
            self.current_candidate_id = None
            self.current_plan = None
            self.preview_state.clear()
            self._refresh_preview_status()
            self.refresh_candidate_tree()
            self.refresh_selection_panel()
            self.refresh_canvas()
            if candidate_set.candidates:
                first_candidate_id = candidate_set.candidates[0].candidate_id
                for item in self.candidate_tree.get_children():
                    values = self.candidate_tree.item(item, "values")
                    if len(values) >= 3 and values[2] == first_candidate_id:
                        self._syncing_candidate_tree = True
                        try:
                            self.candidate_tree.selection_set(item)
                            self.candidate_tree.focus(item)
                        finally:
                            self._syncing_candidate_tree = False
                        break
            if candidate_set.meta.get("truncated"):
                self._set_route_generation_status(
                    f"搜索已截断，已生成 {len(candidate_set.candidates)} 条候选轨迹"
                )
            else:
                self._set_route_generation_status(f"已生成 {len(candidate_set.candidates)} 条候选轨迹")
            self.log(
                f"已生成 {len(candidate_set.candidates)} 条候选轨迹：{self._route_generation_summary}"
            )

        def _update_auto_coverage_stats(self, candidate_set: RouteCandidateSet | None) -> None:
            if candidate_set is None or candidate_set.meta.get("planning_mode") != "auto":
                self.auto_coverage_stats_var.set("尚未执行自动规划")
                return
            self.auto_coverage_stats_var.set(
                f"有向边覆盖 {candidate_set.meta.get('directed_edge_coverage_count', 0)}，"
                f"物理边覆盖 {candidate_set.meta.get('physical_edge_coverage_count', 0)}，"
                f"节点覆盖 {candidate_set.meta.get('node_coverage_count', 0)}"
            )


        def _poll_route_generation_queue(self) -> None:
            self._route_generation_poll_after_id = None
            if not self._route_generation_active:
                return

            record = self._route_generation_job_record
            if record is None:
                self._handle_route_generation_error("后台任务状态丢失")
                return

            status, expired_record = self._route_generation_job_service.get_job_status(
                record.job_id,
                resolve_candidate_set=lambda payload: dict(payload),
            )
            if expired_record is not None:
                self._route_generation_job_service.cleanup_runtime(expired_record)
                self._route_generation_job_record = None
                self._handle_route_generation_error("后台任务状态已过期")
                return
            if status is None:
                self._route_generation_job_record = None
                self._handle_route_generation_error("后台任务不存在")
                return

            latest_progress = status.get("progress")
            state = str(status.get("state") or "")
            if state == "succeeded":
                candidate_payload = status.get("candidate_set")
                if not isinstance(candidate_payload, dict):
                    self._handle_route_generation_error("后台任务返回了无效的候选结果")
                    return
                candidate_set = RouteCandidateSet.from_mapping(candidate_payload)
                self._handle_route_generation_success(candidate_set)
                return
            if state in {"failed", "cancelled", "timed_out"}:
                self._handle_route_generation_error(str(status.get("error") or "后台进程执行失败"))
                return

            if isinstance(latest_progress, dict):
                self._debug_log(
                    f"progress expansions={latest_progress.get('expansions')} candidates={latest_progress.get('candidates_found')}"
                )
                self._update_route_generation_progress(latest_progress)

            if self._route_generation_active:
                self._schedule_route_generation_poll()

        def on_close(self) -> None:
            self._apply_current_node_edits(show_errors=False)
            self._flush_graph_meta_autosave(force=True)
            self._cancel_preview_refresh()
            self._cancel_export_input_autosave()
            self._cancel_canvas_view_autosave()
            self._cancel_route_generation_poll()
            if self._route_generation_active:
                self._finish_route_generation(terminate=True)
            elif self._route_generation_job_record is not None:
                self._finish_route_generation(terminate=False)
            self.root.destroy()

        def _clear_candidates(self) -> None:
            self._cancel_preview_refresh()
            self.current_candidate_set = None
            self.current_candidate_id = None
            self.current_plan = None
            self._preview_cache.clear()
            self.preview_state.clear()
            self._update_auto_coverage_stats(None)
            self._refresh_preview_status()

        def _refresh_all(self) -> None:
            self.refresh_lists()
            self.refresh_via_list()
            self.refresh_candidate_tree()
            self.refresh_canvas()
            self.refresh_selection_panel()

        def refresh_lists(self) -> None:
            self.node_listbox.delete(0, "end")
            for node in self.graph.nodes:
                self.node_listbox.insert("end", f"{node.id}  {node.name}")

            self.edge_listbox.delete(0, "end")
            for edge in self.graph.edges:
                flag = "开" if edge.enabled else "关"
                arrow = "<->" if edge.bidirectional else "->"
                self.edge_listbox.insert(
                    "end",
                    f"{edge.id}  {edge.from_node} {arrow} {edge.to_node}  w={edge.weight:.1f} [{flag}]",
                )

            node_ids = [node.id for node in self.graph.nodes]
            for node_id in self.selected_nodes:
                if node_id in node_ids:
                    self.node_listbox.selection_set(node_ids.index(node_id))

            edge_ids = [edge.id for edge in self.graph.edges]
            if self.selected_edge_id in edge_ids:
                self.edge_listbox.selection_set(edge_ids.index(self.selected_edge_id))

        def refresh_via_list(self) -> None:
            self.via_listbox.delete(0, "end")
            for node_id in self.via_nodes:
                self.via_listbox.insert("end", node_id)

        def _sorted_candidates_for_display(self) -> list[Any]:
            if self.current_candidate_set is None:
                return []
            return sorted(
                self.current_candidate_set.candidates,
                key=lambda candidate: (
                    int(candidate.meta.get("frame_count", 0)),
                    float(candidate.total_length),
                    int(candidate.rank),
                    str(candidate.candidate_id),
                ),
            )

        def _candidate_display_rank(self, candidate_id: str) -> int | None:
            for row_index, candidate in enumerate(self._sorted_candidates_for_display(), start=1):
                if str(candidate.candidate_id) == str(candidate_id):
                    return row_index
            return None

        def refresh_candidate_tree(self) -> None:
            for item in self.candidate_tree.get_children():
                self.candidate_tree.delete(item)

            if self.current_candidate_set is None:
                return

            for candidate in self.current_candidate_set.candidates:
                self.candidate_tree.insert(
                    "",
                    "end",
                    iid=candidate.candidate_id,
                    values=(
                        "是" if candidate.selected else "",
                        candidate.rank,
                        candidate.candidate_id,
                        f"{candidate.total_length:.1f}",
                        candidate.edge_pass_count(),
                        candidate.repeat_node_count(),
                    ),
                )

            if self.current_candidate_id and self.candidate_tree.exists(self.current_candidate_id):
                self.candidate_tree.selection_set(self.current_candidate_id)
                self.candidate_tree.focus(self.current_candidate_id)

        def refresh_candidate_tree(self) -> None:
            self._syncing_candidate_tree = True
            try:
                self.candidate_tree.delete(*self.candidate_tree.get_children())

                if self.current_candidate_set is None:
                    return

                sorted_candidates = self._sorted_candidates_for_display()
                inserted_ids: set[str] = set()
                for row_index, candidate in enumerate(sorted_candidates, start=1):
                    raw_candidate_id = str(candidate.candidate_id)
                    tree_iid = raw_candidate_id
                    if tree_iid in inserted_ids:
                        tree_iid = f"{raw_candidate_id}__dup_{row_index}"
                    inserted_ids.add(tree_iid)
                    self.candidate_tree.insert(
                        "",
                        "end",
                        iid=tree_iid,
                        values=(
                            "Y" if candidate.selected else "",
                            row_index,
                            raw_candidate_id,
                            candidate.meta.get("auto_start_node", self.current_candidate_set.anchor_nodes[0] if self.current_candidate_set.anchor_nodes else ""),
                            candidate.meta.get("auto_end_node", self.current_candidate_set.anchor_nodes[-1] if self.current_candidate_set.anchor_nodes else ""),
                            f"{candidate.total_length:.1f}",
                            candidate.meta.get("frame_count", ""),
                            candidate.edge_pass_count(),
                            candidate.repeat_node_count(),
                        ),
                    )

                if self.current_candidate_id:
                    for item in self.candidate_tree.get_children():
                        values = self.candidate_tree.item(item, "values")
                        if len(values) >= 3 and values[2] == self.current_candidate_id:
                            self.candidate_tree.selection_set(item)
                            self.candidate_tree.focus(item)
                            break
            finally:
                self._syncing_candidate_tree = False

        def _canvas_dimensions(self) -> tuple[int, int]:
            width = max(self.canvas.winfo_width(), 100)
            height = max(self.canvas.winfo_height(), 100)
            return width, height

        def _graph_view_center(self) -> tuple[float, float]:
            return compute_canvas_view_center(node.position for node in self.graph.nodes)

        def _transform_canvas_view_position(
            self,
            position: Iterable[float],
            *,
            view_state: CanvasViewState | None = None,
            view_center: tuple[float, float] | None = None,
        ) -> tuple[float, float]:
            if view_state is None:
                view_state = self._current_canvas_view_state()
            if view_center is None:
                view_center = self._graph_view_center()
            return transform_canvas_view_position(
                position,
                center_xy=view_center,
                view_state=view_state,
            )

        def _inverse_canvas_view_position(
            self,
            position: Iterable[float],
            *,
            view_state: CanvasViewState | None = None,
            view_center: tuple[float, float] | None = None,
        ) -> tuple[float, float]:
            if view_state is None:
                view_state = self._current_canvas_view_state()
            if view_center is None:
                view_center = self._graph_view_center()
            return inverse_canvas_view_position(
                position,
                center_xy=view_center,
                view_state=view_state,
            )

        def _projection(
            self,
            *,
            view_state: CanvasViewState | None = None,
            view_center: tuple[float, float] | None = None,
        ):
            width, height = self._canvas_dimensions()
            if view_state is None:
                view_state = self._current_canvas_view_state()
            if view_center is None:
                view_center = self._graph_view_center()
            return build_canvas_projection(
                [
                    self._transform_canvas_view_position(
                        node.position,
                        view_state=view_state,
                        view_center=view_center,
                    )
                    for node in self.graph.nodes
                ],
                width=width,
                height=height,
            )

        def _transform_draw_point(self, x: float, y: float) -> tuple[float, float]:
            width, height = self._canvas_dimensions()
            center_x = width / 2.0
            center_y = height / 2.0
            return (
                (x - center_x) * self.zoom + center_x + self.pan_x,
                (y - center_y) * self.zoom + center_y + self.pan_y,
            )

        def _inverse_draw_point(self, x: float, y: float) -> tuple[float, float]:
            width, height = self._canvas_dimensions()
            center_x = width / 2.0
            center_y = height / 2.0
            return (
                ((x - self.pan_x - center_x) / self.zoom) + center_x,
                ((y - self.pan_y - center_y) / self.zoom) + center_y,
            )

        def _apply_canvas_view_change(self, *, reset_pan_zoom: bool = False) -> None:
            self._reset_secondary_canvas_interaction()
            if reset_pan_zoom:
                self.zoom = 1.0
                self.pan_x = 0.0
                self.pan_y = 0.0
            self._sync_canvas_view_controls()
            self._canvas_view_dirty = True
            self._schedule_canvas_view_autosave()
            self.refresh_canvas()

        def rotate_canvas_left(self) -> None:
            self.canvas_view_rotation_quadrants = (self.canvas_view_rotation_quadrants - 1) % 4
            self._apply_canvas_view_change()

        def rotate_canvas_right(self) -> None:
            self.canvas_view_rotation_quadrants = (self.canvas_view_rotation_quadrants + 1) % 4
            self._apply_canvas_view_change()

        def toggle_canvas_flip_horizontal(self) -> None:
            self.canvas_view_flip_horizontal = bool(self.canvas_view_flip_horizontal_var.get())
            self._apply_canvas_view_change()

        def toggle_canvas_flip_vertical(self) -> None:
            self.canvas_view_flip_vertical = bool(self.canvas_view_flip_vertical_var.get())
            self._apply_canvas_view_change()

        def reset_canvas_view(self) -> None:
            self.canvas_view_rotation_quadrants = 0
            self.canvas_view_flip_horizontal = False
            self.canvas_view_flip_vertical = False
            self._apply_canvas_view_change(reset_pan_zoom=True)

        def _draw_current_candidate(
            self,
            projection,
            *,
            view_state: CanvasViewState,
            view_center: tuple[float, float],
        ) -> None:
            if self.current_plan is None:
                return

            node_map = self.graph.node_map
            path_points = [
                self._transform_draw_point(
                    *project_point(
                        self._transform_canvas_view_position(
                            node_map[node_id].position,
                            view_state=view_state,
                            view_center=view_center,
                        ),
                        projection,
                    )
                )
                for node_id in self.current_plan.planned_nodes
                if node_id in node_map
            ]
            if len(path_points) >= 2:
                flat_points = []
                for x, y in path_points:
                    flat_points.extend([x, y])
                self.canvas.create_line(*flat_points, fill="#ea580c", width=4, smooth=False)

            edge_passes = list(self.current_plan.edge_passes)
            if not edge_passes:
                return

            for label in compute_edge_pass_label_layout(
                node_map,
                edge_passes,
                lambda position: self._transform_draw_point(
                    *project_point(
                        self._transform_canvas_view_position(
                            position,
                            view_state=view_state,
                            view_center=view_center,
                        ),
                        projection,
                    )
                ),
            ):
                self.canvas.create_text(
                    label.x,
                    label.y,
                    text=str(label.pass_index),
                    fill="#1d4ed8",
                    font=("TkDefaultFont", 9, "bold"),
                )

        def refresh_canvas(self) -> None:
            self.canvas.delete("all")
            if not self.graph.nodes:
                self.canvas.create_text(40, 40, text="未加载图文件", anchor="nw", fill="#475569")
                return

            view_state = self._current_canvas_view_state()
            view_center = self._graph_view_center()
            projection = self._projection(view_state=view_state, view_center=view_center)
            node_map = self.graph.node_map
            active_group_color = self._active_group_color

            for edge in self.graph.edges:
                from_node = node_map.get(edge.from_node)
                to_node = node_map.get(edge.to_node)
                if from_node is None or to_node is None:
                    if edge.id not in self._invalid_canvas_edge_ids_logged:
                        self._invalid_canvas_edge_ids_logged.add(edge.id)
                        self._debug_log(
                            f"skip drawing invalid edge {edge.id}: {edge.from_node} -> {edge.to_node}"
                        )
                    continue
                start = project_point(
                    self._transform_canvas_view_position(
                        from_node.position,
                        view_state=view_state,
                        view_center=view_center,
                    ),
                    projection,
                )
                end = project_point(
                    self._transform_canvas_view_position(
                        to_node.position,
                        view_state=view_state,
                        view_center=view_center,
                    ),
                    projection,
                )
                x1, y1 = self._transform_draw_point(*start)
                x2, y2 = self._transform_draw_point(*end)
                edge_kind = get_edge_kind(edge)
                edge_group_color = get_edge_group_color(edge, default_color=DEFAULT_GROUP_COLOR)
                if edge_kind == EDGE_KIND_BRIDGE:
                    color = resolve_bridge_color(self.graph.meta, default_color=DEFAULT_BRIDGE_COLOR)
                else:
                    color = edge_group_color or DEFAULT_GROUP_COLOR
                color, width, dash = resolve_canvas_edge_draw_style(
                    base_color=color,
                    enabled=bool(edge.enabled),
                    selected=edge.id == self.selected_edge_id,
                    active_group_selected=active_group_color is not None,
                    belongs_to_active_group=(
                        edge_kind == EDGE_KIND_GROUP and edge_group_color == active_group_color
                    ),
                )
                self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width, dash=dash)

            self._draw_current_candidate(
                projection,
                view_state=view_state,
                view_center=view_center,
            )

            if self.preview_state.mission is not None:
                mission_points = [
                    self._transform_draw_point(
                        *project_point(
                            self._transform_canvas_view_position(
                                item["state"][0],
                                view_state=view_state,
                                view_center=view_center,
                            ),
                            projection,
                        )
                    )
                    for item in self.preview_state.mission["positions"]
                ]
                if len(mission_points) >= 2:
                    flat_points = []
                    for x, y in mission_points:
                        flat_points.extend([x, y])
                    self.canvas.create_line(*flat_points, fill="#2563eb", width=2, smooth=False)

            for node in self.graph.nodes:
                point = project_point(
                    self._transform_canvas_view_position(
                        node.position,
                        view_state=view_state,
                        view_center=view_center,
                    ),
                    projection,
                )
                x, y = self._transform_draw_point(*point)
                radius = 6 if node.id in self.selected_nodes else 4
                color = "#f97316" if node.id in self.selected_nodes else "#111827"
                self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="")
                label = node.id
                if node.id == self.start_node:
                    label += " [S]"
                if node.id == self.end_node:
                    label += " [E]"
                if node.id in self.via_nodes:
                    label += f" [V{self.via_nodes.index(node.id) + 1}]"
                self.canvas.create_text(x + 8, y - 8, text=label, anchor="sw", fill="#0f172a")

        def refresh_selection_panel(self) -> None:
            node = self.graph.get_node(self.selected_nodes[0]) if self.selected_nodes else None
            self._selection_panel_node_id = node.id if node else None
            self.selected_node_var.set(node.id if node else "")
            self.name_entry.delete(0, "end")
            self.tags_entry.delete(0, "end")
            self.node_sample_radius_override_entry.delete(0, "end")
            if node is not None:
                self.name_entry.insert(0, node.name)
                self.tags_entry.insert(0, " ".join(node.tags))
                radius_override = node.meta.get(NODE_SAMPLE_RADIUS_META_KEY)
                if radius_override is not None:
                    self.node_sample_radius_override_entry.insert(0, str(radius_override))

            route_text = "尚未生成候选轨迹"
            if self.current_candidate_set is not None and self.current_candidate_id is not None:
                candidate = self.current_candidate_set.get_candidate(self.current_candidate_id)
                display_rank = self._candidate_display_rank(self.current_candidate_id)
                route_text = (
                    f"{candidate.candidate_id} 排名={display_rank if display_rank is not None else candidate.rank} "
                    f"保留={'是' if candidate.selected else '否'} "
                    f"长度={candidate.total_length:.1f} "
                    f"边经过数={candidate.edge_pass_count()} "
                    f"重复节点数={candidate.repeat_node_count()}"
                )
            self.route_info_var.set(route_text)
            self._refresh_preview_status()
            self._refresh_edge_controls()

        def _refresh_edge_controls(self) -> None:
            edge = None
            if self.selected_edge_id:
                try:
                    edge = self.graph.get_edge(self.selected_edge_id)
                except GraphSchemaError:
                    edge = None
            if edge is None:
                self.selected_edge_kind_var.set("未选中边")
                self.selected_edge_color_var.set("")
                return
            edge_kind = get_edge_kind(edge)
            if edge_kind == EDGE_KIND_BRIDGE:
                self.selected_edge_kind_var.set(f"当前边 `{edge.id}`: 桥接边")
                self.selected_edge_color_var.set(
                    f"桥接色 {resolve_bridge_color(self.graph.meta, default_color=DEFAULT_BRIDGE_COLOR)}"
                )
            else:
                color = get_edge_group_color(edge, default_color=DEFAULT_GROUP_COLOR) or DEFAULT_GROUP_COLOR
                self.selected_edge_kind_var.set(f"当前边 `{edge.id}`: 组内边")
                self.selected_edge_color_var.set(f"组色 {color}")

        def _sync_export_controls(self) -> None:
            if is_fixed_z_enabled(self.altitude_mode_var.get()):
                self.fixed_z_entry.configure(state="normal")
            else:
                self.fixed_z_entry.configure(state="disabled")

        def _maybe_apply_graph_default_fixed_z(self) -> None:
            if self._read_group_configs():
                return
            if has_graph_gui_export_input(self.graph.meta, "fixed_z"):
                return
            if not self.fixed_z_var.get().strip() and self.graph.default_altitude is not None:
                self.fixed_z_var.set(str(self.graph.default_altitude))

        def on_altitude_mode_changed(self, _event=None) -> None:
            self._sync_export_controls()

        def on_group_selection_changed(self, _event=None) -> None:
            if self._suspend_group_selection:
                return
            selected_label = self.active_group_color_var.get()
            color = self._group_combo_color_lookup.get(selected_label)
            if color is None and selected_label:
                color = selected_label
            if color is None:
                return
            self._select_group_color(color)

        def add_palette_color(self) -> None:
            initial_color = (
                self._paint_color
                or self._active_group_color
                or DEFAULT_GROUP_COLOR
            )
            result = colorchooser.askcolor(color=initial_color, title="新增调色盘颜色")
            if not result or not result[1]:
                return
            try:
                color = normalize_hex_color(result[1], field_name="group color")
            except GraphSchemaError as exc:
                messagebox.showerror("调色盘颜色", str(exc))
                return
            used_colors, _ = self._palette_colors()
            if color not in set(used_colors):
                self._session_palette_colors.add(color)
            self._select_paint_color(color)
            self._refresh_palette_controls()
            self.status_var.set(f"已选择调色盘颜色：{color}")

        def toggle_paint_mode(self) -> None:
            if self._paint_mode_enabled:
                self._set_paint_mode_enabled(False)
                self.status_var.set("已退出染色模式")
                return
            if self._paint_color is None:
                messagebox.showinfo("染色模式", "请先从调色盘选择一个颜色。")
                return
            if self._insert_mode_enabled:
                self._set_insert_mode_enabled(False)
            self._set_paint_mode_enabled(True)
            self.status_var.set(f"已进入染色模式，当前画笔 {self._paint_color}")

        def toggle_insert_mode(self) -> None:
            if self._insert_mode_enabled:
                self._set_insert_mode_enabled(False)
                self.status_var.set("已退出插点模式")
                return
            if self._paint_mode_enabled:
                self._set_paint_mode_enabled(False)
            self._set_insert_mode_enabled(True)
            self.status_var.set("已进入插点模式，可右键点击组内边插入新节点")

        def choose_active_group_color(self) -> None:
            self.add_palette_color()

        def choose_bridge_color(self) -> None:
            current = resolve_bridge_color(self.graph.meta, default_color=DEFAULT_BRIDGE_COLOR)
            result = colorchooser.askcolor(color=current, title="选择桥接边颜色")
            if not result or not result[1]:
                return
            try:
                color = normalize_hex_color(result[1], field_name="bridge color")
            except GraphSchemaError as exc:
                messagebox.showerror("桥接边颜色", str(exc))
                return
            write_graph_bridge_style(self.graph.meta, {"color": color})
            self.bridge_color_var.set(color)
            self._export_inputs_dirty = True
            self._schedule_export_input_autosave()
            self.refresh_canvas()
            self._refresh_edge_controls()

        def set_selected_edge_group_color(self) -> None:
            if not self.selected_edge_id:
                messagebox.showinfo("边颜色", "请先选中一条边。")
                return
            if self._paint_color is None:
                messagebox.showinfo("边颜色", "请先从调色盘选择一个颜色。")
                return

            self._paint_edge_with_color(self.selected_edge_id, self._paint_color)

        def set_selected_edge_bridge(self) -> None:
            if not self.selected_edge_id:
                messagebox.showinfo("桥接边", "请先选中一条边。")
                return

            def mutate() -> None:
                self.editor.set_edge_bridge(self.selected_edge_id)

            self._run_mutation(mutate)

        def _resolve_export_options(self) -> dict[str, float | int | None | str | bool]:
            return resolve_export_options(
                step_distance_text=self.step_distance_var.get(),
                fps_text=self.fps_var.get(),
                altitude_mode=self.altitude_mode_var.get(),
                fixed_z_text=self.fixed_z_var.get(),
                altitude_offset_text=self.altitude_offset_var.get(),
                takeoff_landing_relative_z_text=self.takeoff_landing_relative_z_var.get(),
                takeoff_landing_step_distance_text=self.takeoff_landing_step_distance_var.get(),
                node_sample_radius_text=self.node_sample_radius_var.get(),
                random_seed_text=self.random_seed_var.get(),
                turn_smoothing_enabled=bool(self.turn_smoothing_enabled_var.get()),
                corner_radius_text=self.corner_radius_var.get(),
                small_turn_yaw_blend_threshold_deg_text=(
                    self.small_turn_yaw_blend_threshold_deg_var.get()
                ),
                corner_min_angle_deg_text=self.corner_min_angle_deg_var.get(),
                u_turn_threshold_deg_text=self.u_turn_threshold_deg_var.get(),
                u_turn_transition_distance_text=self.u_turn_transition_distance_var.get(),
                corner_max_yaw_step_deg_text=self.corner_max_yaw_step_deg_var.get(),
                u_turn_pivot_yaw_step_deg_text=self.u_turn_pivot_yaw_step_deg_var.get(),
            )

        def _candidate_frame_count(self, candidate_set: RouteCandidateSet, candidate_id: str) -> int:
            plan_source = candidate_set
            if candidate_set.meta.get("planning_mode") == "auto":
                candidate = candidate_set.get_candidate(candidate_id)
                start_node = str(candidate.meta.get("auto_start_node") or "")
                end_node = str(candidate.meta.get("auto_end_node") or "")
                if not start_node or not end_node:
                    raise GraphSchemaError("自动规划候选轨迹缺少起点或终点信息。")
                plan_source = RouteCandidateSet(
                    env_id=candidate_set.env_id,
                    graph_name=candidate_set.graph_name,
                    anchor_nodes=[start_node, end_node],
                    candidates=[candidate],
                    node_lookup=candidate_set.node_lookup,
                    selected_candidate_ids=[candidate.candidate_id] if candidate.selected else [],
                    meta=dict(candidate_set.meta),
                )
            plan = candidate_to_plan(plan_source, candidate_id)
            export_options = self._resolve_export_options()
            mission = export_mission(
                plan,
                output_path=None,
                step_distance=float(export_options["step_distance"]),
                fps=float(export_options["fps"]),
                altitude_mode=str(export_options["altitude_mode"]),
                fixed_z=export_options["fixed_z"],
                altitude_offset=float(export_options["altitude_offset"]),
                takeoff_landing_relative_z=export_options["takeoff_landing_relative_z"],
                takeoff_landing_step_distance=export_options["takeoff_landing_step_distance"],
                node_sample_radius=float(export_options["node_sample_radius"]),
                random_seed=export_options["random_seed"],
                turn_smoothing_enabled=bool(export_options["turn_smoothing_enabled"]),
                corner_radius=float(export_options["corner_radius"]),
                small_turn_yaw_blend_threshold_deg=float(
                    export_options["small_turn_yaw_blend_threshold_deg"]
                ),
                corner_min_angle_deg=float(export_options["corner_min_angle_deg"]),
                u_turn_threshold_deg=float(export_options["u_turn_threshold_deg"]),
                u_turn_transition_distance=float(export_options["u_turn_transition_distance"]),
                corner_max_yaw_step_deg=float(export_options["corner_max_yaw_step_deg"]),
                u_turn_pivot_yaw_step_deg=float(export_options["u_turn_pivot_yaw_step_deg"]),
            )
            return len(mission["positions"])

        def _apply_generation_filters(self, candidate_set: RouteCandidateSet) -> RouteCandidateSet:
            min_frame_count = resolve_min_frame_count_text(self.min_frame_count_var.get())
            max_frame_count = resolve_max_frame_count_text(self.max_frame_count_var.get())
            if min_frame_count is None and max_frame_count is None:
                return candidate_set
            filtered_candidates = []
            for candidate in candidate_set.candidates:
                frame_count = self._candidate_frame_count(candidate_set, candidate.candidate_id)
                candidate.meta["frame_count"] = int(frame_count)
                if min_frame_count is not None and frame_count < min_frame_count:
                    continue
                if max_frame_count is not None and frame_count > max_frame_count:
                    continue
                filtered_candidates.append(candidate)
            candidate_set.candidates = filtered_candidates
            candidate_set.meta["min_frame_count"] = min_frame_count
            candidate_set.meta["max_frame_count"] = max_frame_count
            if not filtered_candidates:
                raise GraphSchemaError("当前帧数限制下没有可用候选轨迹。")
            for index, candidate in enumerate(candidate_set.candidates, start=1):
                candidate.rank = index
                candidate.selected = index == 1
            candidate_set.sync_selected_ids()
            return candidate_set

        def _annotate_candidate_frame_counts(self, candidate_set: RouteCandidateSet) -> None:
            for candidate in candidate_set.candidates:
                if "frame_count" not in candidate.meta:
                    candidate.meta["frame_count"] = int(
                        self._candidate_frame_count(candidate_set, candidate.candidate_id)
                    )

        def _collect_auto_plan_inputs(self) -> dict[str, Any]:
            return {
                "planning_mode": self.planning_mode_var.get(),
                "auto_max_output_routes": self.auto_max_output_routes_var.get(),
                "auto_max_routes_per_pair": self.auto_max_routes_per_pair_var.get(),
                "auto_max_anchor_pairs_to_evaluate": self.auto_max_anchor_pairs_var.get(),
                "auto_distance_per_frame": self.auto_distance_per_frame_var.get(),
                "auto_min_total_length": self.auto_min_total_length_var.get(),
                "auto_max_total_length": self.auto_max_total_length_var.get(),
                "auto_min_frame_count": self.auto_min_frame_count_var.get(),
                "auto_max_frame_count": self.auto_max_frame_count_var.get(),
                "auto_min_endpoint_distance": self.auto_min_endpoint_distance_var.get(),
                "auto_max_search_states": self.auto_max_search_states_var.get(),
                "auto_coverage_weight": self.auto_coverage_weight_var.get(),
                "auto_diversity_weight": self.auto_diversity_weight_var.get(),
                "auto_anchor_weight": self.auto_anchor_weight_var.get(),
                "auto_reverse_penalty_weight": self.auto_reverse_penalty_weight_var.get(),
                "auto_prefer_connected_anchors": self.auto_prefer_connected_anchors_var.get(),
                "auto_prefer_route_diversity": self.auto_prefer_route_diversity_var.get(),
                "auto_allow_reverse_direction_counterparts": self.auto_allow_reverse_direction_counterparts_var.get(),
                "auto_enable_global_coverage": self.auto_enable_global_coverage_var.get(),
                "auto_allowed_route_group_colors": list(self._auto_allowed_route_group_colors),
                "auto_excluded_endpoint_group_colors": list(self._auto_excluded_endpoint_group_colors),
            }

        def _sync_route_meta_for_export(self) -> None:
            self._sync_current_group_config_to_graph_meta()
            group_configs, _, configs_changed = self._reconcile_group_configs()
            if configs_changed:
                self._write_group_configs(group_configs)
            bridge_style = read_graph_bridge_style(self.graph.meta)
            if self.current_candidate_set is not None:
                self.current_candidate_set.meta[GRAPH_GROUP_CONFIGS_META_KEY] = group_configs
                self.current_candidate_set.meta[GRAPH_BRIDGE_STYLE_META_KEY] = bridge_style
                self.current_candidate_set.meta[GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY] = write_graph_gui_auto_plan_inputs(
                    self.current_candidate_set.meta,
                    self._collect_auto_plan_inputs(),
                )
            if self.current_plan is not None:
                self.current_plan.meta[GRAPH_GROUP_CONFIGS_META_KEY] = group_configs
                self.current_plan.meta[GRAPH_BRIDGE_STYLE_META_KEY] = bridge_style

        def refresh_mission_preview(self, *, show_errors: bool = True) -> bool:
            if self.current_plan is None:
                self.preview_state.clear()
                self._refresh_preview_status()
                return False

            try:
                self._sync_route_meta_for_export()
                export_options = self._resolve_export_options()
                mission = export_mission(
                    self.current_plan,
                    output_path=None,
                    step_distance=float(export_options["step_distance"]),
                    fps=float(export_options["fps"]),
                    altitude_mode=str(export_options["altitude_mode"]),
                    fixed_z=export_options["fixed_z"],
                    altitude_offset=float(export_options["altitude_offset"]),
                    takeoff_landing_relative_z=export_options["takeoff_landing_relative_z"],
                    takeoff_landing_step_distance=export_options["takeoff_landing_step_distance"],
                    node_sample_radius=float(export_options["node_sample_radius"]),
                    random_seed=export_options["random_seed"],
                    turn_smoothing_enabled=bool(export_options["turn_smoothing_enabled"]),
                    corner_radius=float(export_options["corner_radius"]),
                    small_turn_yaw_blend_threshold_deg=float(
                        export_options["small_turn_yaw_blend_threshold_deg"]
                    ),
                    corner_min_angle_deg=float(export_options["corner_min_angle_deg"]),
                    u_turn_threshold_deg=float(export_options["u_turn_threshold_deg"]),
                    u_turn_transition_distance=float(export_options["u_turn_transition_distance"]),
                    corner_max_yaw_step_deg=float(export_options["corner_max_yaw_step_deg"]),
                    u_turn_pivot_yaw_step_deg=float(export_options["u_turn_pivot_yaw_step_deg"]),
                )
                self._set_preview(mission)
                self._refresh_preview_status()
                return True
            except GraphSchemaError as exc:
                self.preview_state.mark_stale()
                self._refresh_preview_status()
                if show_errors:
                    messagebox.showerror("轨迹预览", str(exc))
                self.log(f"轨迹预览失败：{exc}")
                return False

        def refresh_mission_preview_ui(self) -> None:
            if self.current_plan is None:
                messagebox.showinfo("轨迹预览", "请先生成并选中一条候选轨迹。")
                return
            if self.refresh_mission_preview():
                self.log("已刷新轨迹预览")
                self.refresh_canvas()

        def _nearest_node_id_on_canvas(self, x: float, y: float) -> str | None:
            if not self.graph.nodes:
                return None
            view_state = self._current_canvas_view_state()
            view_center = self._graph_view_center()
            projection = self._projection(view_state=view_state, view_center=view_center)
            base_x, base_y = self._inverse_draw_point(x, y)
            transformed_x, transformed_y = unproject_point(base_x, base_y, projection)
            world_x, world_y = self._inverse_canvas_view_position(
                (transformed_x, transformed_y),
                view_state=view_state,
                view_center=view_center,
            )

            nearest_node_id: str | None = None
            best_distance = float("inf")
            for node in self.graph.nodes:
                dx = node.position[0] - world_x
                dy = node.position[1] - world_y
                distance = (dx * dx + dy * dy) ** 0.5
                if distance < best_distance:
                    best_distance = distance
                    nearest_node_id = node.id
            return nearest_node_id

        def _nearest_node_hit_id_on_canvas(
            self,
            x: float,
            y: float,
            *,
            max_distance_px: float = CANVAS_NODE_HIT_RADIUS_PX,
        ) -> str | None:
            if not self.graph.nodes:
                return None
            view_state = self._current_canvas_view_state()
            view_center = self._graph_view_center()
            projection = self._projection(view_state=view_state, view_center=view_center)
            nearest_node_id: str | None = None
            best_distance = float("inf")
            for node in self.graph.nodes:
                point = project_point(
                    self._transform_canvas_view_position(
                        node.position,
                        view_state=view_state,
                        view_center=view_center,
                    ),
                    projection,
                )
                draw_x, draw_y = self._transform_draw_point(*point)
                distance = math.hypot(float(x) - draw_x, float(y) - draw_y)
                if distance < best_distance:
                    best_distance = distance
                    nearest_node_id = node.id
            if best_distance <= float(max_distance_px):
                return nearest_node_id
            return None

        def _nearest_edge_hit_on_canvas(
            self,
            x: float,
            y: float,
            *,
            max_distance_px: float = CANVAS_EDGE_HIT_RADIUS_PX,
        ) -> CanvasEdgeHit | None:
            if not self.graph.edges:
                return None
            view_state = self._current_canvas_view_state()
            view_center = self._graph_view_center()
            projection = self._projection(view_state=view_state, view_center=view_center)
            node_map = self.graph.node_map
            nearest_hit: CanvasEdgeHit | None = None
            best_distance = float("inf")
            for edge in self.graph.edges:
                from_node = node_map.get(edge.from_node)
                to_node = node_map.get(edge.to_node)
                if from_node is None or to_node is None:
                    continue
                start = project_point(
                    self._transform_canvas_view_position(
                        from_node.position,
                        view_state=view_state,
                        view_center=view_center,
                    ),
                    projection,
                )
                end = project_point(
                    self._transform_canvas_view_position(
                        to_node.position,
                        view_state=view_state,
                        view_center=view_center,
                    ),
                    projection,
                )
                draw_start = self._transform_draw_point(*start)
                draw_end = self._transform_draw_point(*end)
                projection_ratio, projected_point = project_point_onto_segment(
                    (float(x), float(y)),
                    draw_start,
                    draw_end,
                )
                distance = math.hypot(
                    float(x) - projected_point[0],
                    float(y) - projected_point[1],
                )
                if distance < best_distance:
                    best_distance = distance
                    nearest_hit = CanvasEdgeHit(
                        edge_id=edge.id,
                        projection_ratio=projection_ratio,
                        projected_point=projected_point,
                        segment_start=draw_start,
                        segment_end=draw_end,
                    )
            if best_distance <= float(max_distance_px):
                return nearest_hit
            return None

        def _nearest_edge_id_on_canvas(
            self,
            x: float,
            y: float,
            *,
            max_distance_px: float = CANVAS_EDGE_HIT_RADIUS_PX,
        ) -> str | None:
            hit = self._nearest_edge_hit_on_canvas(x, y, max_distance_px=max_distance_px)
            return None if hit is None else hit.edge_id

        def _insert_node_on_canvas_hit(self, hit: CanvasEdgeHit) -> bool:
            if self._route_generation_active:
                messagebox.showinfo("插点模式", "路径生成进行中，暂时不能修改图。")
                return False
            try:
                edge = self.graph.get_edge(hit.edge_id)
            except GraphSchemaError:
                return False
            if get_edge_kind(edge) == EDGE_KIND_BRIDGE:
                self.selected_nodes = []
                self.selected_edge_id = edge.id
                self.refresh_lists()
                self.refresh_selection_panel()
                self.refresh_canvas()
                messagebox.showinfo("插点模式", "桥接边暂不支持插点。")
                self.status_var.set(f"边 `{edge.id}` 是桥接边，暂不支持插点")
                return False

            segment_length_px = math.hypot(
                hit.segment_end[0] - hit.segment_start[0],
                hit.segment_end[1] - hit.segment_start[1],
            )
            endpoint_distance_px = min(
                hit.projection_ratio * segment_length_px,
                (1.0 - hit.projection_ratio) * segment_length_px,
            )
            if endpoint_distance_px <= CANVAS_EDGE_INSERT_ENDPOINT_GUARD_PX:
                messagebox.showinfo("插点模式", "点击位置离端点太近，请在线段中部一些的位置插点。")
                self.status_var.set(f"边 `{edge.id}` 的点击位置离端点过近，已取消插点")
                return False

            created_node_id: str | None = None

            def mutate() -> None:
                nonlocal created_node_id
                inserted_node = self.editor.insert_node_on_edge(hit.edge_id, hit.projection_ratio)
                created_node_id = inserted_node.id

            if not self._run_mutation(mutate):
                return False
            if created_node_id is None:
                return False

            self.selected_nodes = [created_node_id]
            self.selected_edge_id = None
            self.refresh_lists()
            self.refresh_selection_panel()
            self.refresh_canvas()
            self.status_var.set(f"已在边 `{hit.edge_id}` 上插入节点 `{created_node_id}`")
            return True

        def _paint_edge_with_color(self, edge_id: str, color: str) -> bool:
            normalized_color = normalize_hex_color(color, field_name="group color")
            self.selected_nodes = []
            self.selected_edge_id = edge_id

            def mutate() -> None:
                self.editor.set_edge_group_color(edge_id, normalized_color)

            if self._run_mutation(mutate):
                self._select_paint_color(normalized_color)
                self.status_var.set(f"已将边 `{edge_id}` 染成 {normalized_color}")
                return True
            return False

        def _toggle_anchor_on_canvas(self, event, *, mode: str):
            if self._paint_mode_enabled:
                return "break"
            self._apply_current_node_edits(show_errors=False)
            node_id = self._nearest_node_id_on_canvas(event.x, event.y)
            if node_id is None:
                return "break"
            self.selected_nodes = [node_id]
            self.selected_edge_id = None

            refresh_via = False
            if mode == "start":
                if self.start_node == node_id:
                    self.start_node = None
                else:
                    self.start_node = node_id
            elif mode == "end":
                if self.end_node == node_id:
                    self.end_node = None
                else:
                    self.end_node = node_id
                self._reset_secondary_canvas_interaction()
            else:
                refresh_via = True
                if node_id in self.via_nodes:
                    self.via_nodes.remove(node_id)
                else:
                    self.via_nodes.append(node_id)

            self._clear_candidates()
            self.refresh_lists()
            if refresh_via:
                self.refresh_via_list()
            self.refresh_candidate_tree()
            self.refresh_selection_panel()
            self.refresh_canvas()
            return "break"

        def _pick_node_on_canvas(self, event, additive: bool) -> None:
            self._apply_current_node_edits(show_errors=False)
            nearest_node_id = None if self._paint_mode_enabled else self._nearest_node_hit_id_on_canvas(event.x, event.y)
            nearest_edge_id = (
                self._nearest_edge_id_on_canvas(event.x, event.y)
                if self._paint_mode_enabled or nearest_node_id is None
                else None
            )
            action = resolve_canvas_primary_click_action(
                paint_mode_enabled=self._paint_mode_enabled,
                nearest_node_id=nearest_node_id,
                nearest_edge_id=nearest_edge_id,
                additive=additive,
            )
            if action == "paint_edge":
                if nearest_edge_id is not None and self._paint_color is not None:
                    self._paint_edge_with_color(nearest_edge_id, self._paint_color)
                return
            if action == "select_edge":
                self.selected_edge_id = nearest_edge_id
                self.selected_nodes = []
                self.refresh_lists()
                self.refresh_selection_panel()
                self.refresh_canvas()
                return
            if action == "toggle_node":
                if nearest_node_id in self.selected_nodes:
                    self.selected_nodes.remove(nearest_node_id)
                else:
                    self.selected_nodes.append(nearest_node_id)
            elif action == "select_node":
                self.selected_nodes = [nearest_node_id]
            else:
                return
            self.selected_edge_id = None
            self.refresh_lists()
            self.refresh_selection_panel()
            self.refresh_canvas()

        def on_canvas_click(self, event) -> str | None:
            self._pick_node_on_canvas(event, additive=False)
            return None

        def on_canvas_shift_click(self, event) -> str | None:
            self._pick_node_on_canvas(event, additive=True)
            return None

        def on_canvas_double_set_start(self, event):
            return self._toggle_anchor_on_canvas(event, mode="start")

        def on_canvas_double_set_end(self, event):
            if self._insert_mode_enabled:
                return "break"
            return self._toggle_anchor_on_canvas(event, mode="end")

        def on_canvas_double_toggle_via(self, event):
            return self._toggle_anchor_on_canvas(event, mode="via")

        def on_canvas_secondary_press(self, event) -> str:
            self._secondary_button_press_origin = (event.x, event.y)
            self._secondary_button_drag_active = False
            hit = self._nearest_edge_hit_on_canvas(event.x, event.y) if self._insert_mode_enabled else None
            self._secondary_button_press_edge_id = None if hit is None else hit.edge_id
            self._pan_origin = None
            return "break"

        def on_canvas_secondary_move(self, event) -> str:
            if self._secondary_button_press_origin is None:
                return "break"
            if not self._secondary_button_drag_active:
                move_distance_px = math.hypot(
                    event.x - self._secondary_button_press_origin[0],
                    event.y - self._secondary_button_press_origin[1],
                )
                if move_distance_px > CANVAS_SECONDARY_DRAG_THRESHOLD_PX:
                    self._secondary_button_drag_active = True
                    self._pan_origin = self._secondary_button_press_origin
            if self._secondary_button_drag_active:
                self.on_pan_move(event)
            return "break"

        def on_canvas_secondary_release(self, event) -> str:
            press_origin = self._secondary_button_press_origin
            pressed_edge_id = self._secondary_button_press_edge_id
            was_dragging = self._secondary_button_drag_active
            self._reset_secondary_canvas_interaction()
            if press_origin is None:
                return "break"

            move_distance_px = math.hypot(event.x - press_origin[0], event.y - press_origin[1])
            release_hit = self._nearest_edge_hit_on_canvas(event.x, event.y)
            release_edge_id = None if release_hit is None else release_hit.edge_id
            action = resolve_canvas_secondary_release_action(
                insert_mode_enabled=self._insert_mode_enabled,
                nearest_edge_id=release_edge_id or pressed_edge_id,
                movement_distance_px=move_distance_px,
            )
            if action != "insert_edge" or was_dragging:
                return "break"

            self._apply_current_node_edits(show_errors=False)
            resolved_hit = release_hit
            if resolved_hit is None and pressed_edge_id is not None:
                resolved_hit = self._nearest_edge_hit_on_canvas(
                    press_origin[0],
                    press_origin[1],
                    max_distance_px=CANVAS_EDGE_HIT_RADIUS_PX * 1.5,
                )
            if resolved_hit is not None:
                self._insert_node_on_canvas_hit(resolved_hit)
            return "break"

        def on_pan_start(self, event) -> None:
            self._pan_origin = (event.x, event.y)

        def on_pan_move(self, event) -> None:
            if self._pan_origin is None:
                return
            dx = event.x - self._pan_origin[0]
            dy = event.y - self._pan_origin[1]
            self.pan_x += dx
            self.pan_y += dy
            self._pan_origin = (event.x, event.y)
            self.refresh_canvas()

        def on_mouse_wheel(self, event) -> None:
            factor = 1.1 if event.delta > 0 else 0.9
            self.zoom = min(max(self.zoom * factor, 0.4), 4.0)
            self.refresh_canvas()

        def on_node_list_select(self, _event=None) -> None:
            self._apply_current_node_edits(show_errors=False)
            indices = list(self.node_listbox.curselection())
            node_ids = [node.id for node in self.graph.nodes]
            self.selected_nodes = [node_ids[index] for index in indices if index < len(node_ids)]
            self.selected_edge_id = None
            self.refresh_selection_panel()
            self.refresh_canvas()

        def on_edge_list_select(self, _event=None) -> None:
            selection = self.edge_listbox.curselection()
            if not selection:
                return
            edge_ids = [edge.id for edge in self.graph.edges]
            index = selection[0]
            if index < len(edge_ids):
                self.selected_edge_id = edge_ids[index]
                self._refresh_edge_controls()
                self.refresh_canvas()

        def on_candidate_tree_select(self, _event=None) -> None:
            if self._syncing_candidate_tree:
                return
            selection = self.candidate_tree.selection()
            if not selection:
                return
            selected_item = selection[0]
            values = self.candidate_tree.item(selected_item, "values")
            candidate_id = values[2] if len(values) >= 3 else selected_item
            self._set_current_candidate(str(candidate_id))

        def on_candidate_tree_select_all(self, _event=None) -> str:
            items = self.candidate_tree.get_children()
            if not items:
                return "break"
            self._syncing_candidate_tree = True
            try:
                self.candidate_tree.selection_set(items)
                self.candidate_tree.focus(items[0])
            finally:
                self._syncing_candidate_tree = False
            return "break"

        def on_candidate_tree_double_click(self, _event=None) -> None:
            self.toggle_keep_current_candidate()

        def _reload_graph(
            self,
            graph: RouteGraph | None = None,
            *,
            load_export_inputs: bool = False,
            load_canvas_view: bool = False,
            reset_pan_zoom: bool = False,
        ) -> None:
            if graph is None and self.graph_path and self.graph_path.exists():
                graph = _load_validated_graph(self.graph_path)
            if graph is not None:
                self.graph = _validate_loaded_graph(graph, source=self.graph_path)
            self.editor = GraphEditor(self.graph)
            self._session_palette_colors.clear()
            self._invalid_canvas_edge_ids_logged.clear()
            if load_export_inputs:
                self._load_export_inputs_from_graph()
            else:
                self._refresh_group_controls()
            if load_canvas_view:
                self._load_canvas_view_from_graph(reset_pan_zoom=reset_pan_zoom)
            self._maybe_apply_graph_default_fixed_z()
            self._sync_export_controls()
            if not self._route_generation_active:
                self._reset_route_generation_progress("就绪")
            self._clear_candidates()
            self._refresh_all()

        def _persist(self) -> None:
            self._cancel_export_input_autosave()
            self._cancel_canvas_view_autosave()
            self._sync_export_inputs_to_graph_meta()
            self._sync_canvas_view_to_graph_meta()
            self._export_inputs_dirty = False
            self._canvas_view_dirty = False
            self.editor.save(self.graph_path)
            self.log(f"已保存图文件：{self.graph_path}")

        def _run_mutation(self, mutator, *, show_errors: bool = True) -> bool:
            try:
                mutator()
                self._persist()
                self._reload_graph()
                return True
            except GraphSchemaError as exc:
                if show_errors:
                    messagebox.showerror("图结构错误", str(exc))
                self.log(f"操作失败：{exc}")
                try:
                    self._reload_graph()
                except GraphSchemaError as reload_exc:
                    if show_errors:
                        messagebox.showerror("图结构错误", str(reload_exc))
                    self.log(f"图文件重载失败：{reload_exc}")
                return False

        def open_graph(self) -> None:
            self._apply_current_node_edits(show_errors=False)
            self._flush_graph_meta_autosave(force=True)
            selected = filedialog.askopenfilename(
                title="打开图文件 JSON",
                filetypes=[("JSON", "*.json"), ("All files", "*.*")],
                initialdir=str(resolve_data_path("graphs")),
            )
            if not selected:
                return
            candidate_path = Path(selected).resolve()
            try:
                graph = _load_validated_graph(candidate_path)
            except GraphSchemaError as exc:
                messagebox.showerror("图结构错误", str(exc))
                self.log(f"打开图文件失败：{exc}")
                return
            self.graph_path = candidate_path
            self._reload_graph(
                graph,
                load_export_inputs=True,
                load_canvas_view=True,
                reset_pan_zoom=True,
            )
            self.log(f"已打开图文件：{self.graph_path}")

        def save_graph_to_disk(self) -> None:
            self._persist()
            self._reload_graph()

        def validate_graph_ui(self) -> None:
            report = self.editor.validate()
            if report.is_valid:
                messagebox.showinfo("图结构校验", report.format_text())
            else:
                messagebox.showwarning("图结构校验", report.format_text())
            self.log(report.format_text())

        def _apply_current_node_edits(self, *, show_errors: bool) -> bool:
            node_id = self._selection_panel_node_id
            if not node_id:
                return False
            try:
                radius_override = resolve_node_sample_radius_override_text(
                    self.node_sample_radius_override_entry.get()
                )
            except GraphSchemaError as exc:
                if show_errors:
                    messagebox.showerror("节点设置", str(exc))
                self.log(f"节点更新失败：{exc}")
                return False

            try:
                node = self.graph.get_node(node_id)
            except GraphSchemaError:
                return False
            name = self.name_entry.get().strip() or node_id
            tags = self.tags_entry.get().strip().split()
            current_radius_override = node.meta.get(NODE_SAMPLE_RADIUS_META_KEY)
            if current_radius_override is not None:
                try:
                    current_radius_override = float(current_radius_override)
                except (TypeError, ValueError):
                    current_radius_override = None
            if (
                node.name == name
                and node.tags == tags
                and current_radius_override == radius_override
            ):
                return False

            def mutate() -> None:
                self.editor.rename_node(node_id, name)
                self.editor.update_node_tags(node_id, tags)
                self.editor.update_node_sample_radius(node_id, radius_override)

            return self._run_mutation(mutate, show_errors=show_errors)

        def apply_node_edits(self) -> None:
            self._apply_current_node_edits(show_errors=True)

        def _prune_deleted_node_refs(self, removed_node_ids: set[str]) -> None:
            if not removed_node_ids:
                return
            self.selected_nodes = [node_id for node_id in self.selected_nodes if node_id not in removed_node_ids]
            if self.start_node in removed_node_ids:
                self.start_node = None
            if self.end_node in removed_node_ids:
                self.end_node = None
            self.via_nodes = [node_id for node_id in self.via_nodes if node_id not in removed_node_ids]
            if self._selection_panel_node_id in removed_node_ids:
                self._selection_panel_node_id = None
            self.selected_edge_id = None

        def delete_current_node(self) -> None:
            node_id = self._selection_panel_node_id
            if not node_id:
                messagebox.showinfo("删除节点", "请先选中一个节点。")
                return

            try:
                node = self.graph.get_node(node_id)
                node_label = f"{node.id} ({node.name})"
            except GraphSchemaError:
                node_label = node_id

            confirmed = messagebox.askyesno(
                "删除节点",
                f"确认删除节点 {node_label} 吗？\n该操作会同时删除与该节点相连的边。",
            )
            if not confirmed:
                return

            self._prune_deleted_node_refs({node_id})

            def mutate() -> None:
                self.editor.delete_node(node_id)

            self._run_mutation(mutate)

        def create_edge(self) -> None:
            if len(self.selected_nodes) != 2:
                messagebox.showinfo("创建边", "请先选中恰好两个节点。")
                return
            node_a, node_b = self.selected_nodes
            try:
                intent = resolve_edge_creation_intent(
                    self.graph,
                    from_node=node_a,
                    to_node=node_b,
                    fallback_group_color=self._paint_color or self._current_group_editor_color(),
                )
            except GraphSchemaError as exc:
                messagebox.showerror("创建边", str(exc))
                return
            edge_meta = intent.to_edge_meta()
            selected_group_color = intent.group_color

            def mutate() -> None:
                self.editor.add_edge(node_a, node_b, meta=edge_meta)

            if self._run_mutation(mutate) and selected_group_color is not None:
                self._select_group_color(selected_group_color, preserve_unsaved=False)

        def remove_edge(self) -> None:
            if self.selected_edge_id:
                def mutate() -> None:
                    self.editor.remove_edge(self.selected_edge_id)
                self._run_mutation(mutate)
                return
            if len(self.selected_nodes) == 2:
                def mutate_between() -> None:
                    self.editor.remove_edge_between(self.selected_nodes[0], self.selected_nodes[1])
                self._run_mutation(mutate_between)
                return
            messagebox.showinfo("删除边", "请先选中一条边，或选中两个已连接节点。")

        def set_edge_enabled(self, enabled: bool) -> None:
            if not self.selected_edge_id:
                messagebox.showinfo("边状态", "请先选中一条边。")
                return

            def mutate() -> None:
                self.editor.set_edge_enabled(self.selected_edge_id, enabled)

            self._run_mutation(mutate)

        def set_start(self) -> None:
            if not self.selected_nodes:
                return
            self.start_node = self.selected_nodes[0]
            self._clear_candidates()
            self.refresh_candidate_tree()
            self.refresh_canvas()
            self.refresh_selection_panel()

        def set_end(self) -> None:
            if not self.selected_nodes:
                return
            self.end_node = self.selected_nodes[0]
            self._clear_candidates()
            self.refresh_candidate_tree()
            self.refresh_canvas()
            self.refresh_selection_panel()

        def add_via(self) -> None:
            if not self.selected_nodes:
                return
            node_id = self.selected_nodes[0]
            if node_id not in self.via_nodes:
                self.via_nodes.append(node_id)
                self._clear_candidates()
                self.refresh_via_list()
                self.refresh_candidate_tree()
                self.refresh_canvas()

        def clear_via(self) -> None:
            self.via_nodes = []
            self._clear_candidates()
            self.refresh_via_list()
            self.refresh_candidate_tree()
            self.refresh_canvas()

        def reorder_via(self, delta: int) -> None:
            selection = self.via_listbox.curselection()
            if not selection:
                return
            index = selection[0]
            new_index = index + delta
            if new_index < 0 or new_index >= len(self.via_nodes):
                return
            self.via_nodes[index], self.via_nodes[new_index] = self.via_nodes[new_index], self.via_nodes[index]
            self.refresh_via_list()
            self.via_listbox.selection_set(new_index)
            self._clear_candidates()
            self.refresh_candidate_tree()
            self.refresh_canvas()

        def _build_candidate_plan_source(self, candidate_id: str) -> RouteCandidateSet:
            if self.current_candidate_set is None:
                raise GraphSchemaError("请先生成候选轨迹。")
            candidate = self.current_candidate_set.get_candidate(candidate_id)
            if self.current_candidate_set.meta.get("planning_mode") != "auto":
                return self.current_candidate_set
            start_node = str(candidate.meta.get("auto_start_node") or "")
            end_node = str(candidate.meta.get("auto_end_node") or "")
            if not start_node or not end_node:
                raise GraphSchemaError("自动规划候选轨迹缺少起点或终点信息。")
            return RouteCandidateSet(
                env_id=self.current_candidate_set.env_id,
                graph_name=self.current_candidate_set.graph_name,
                anchor_nodes=[start_node, end_node],
                candidates=[candidate],
                node_lookup=self.current_candidate_set.node_lookup,
                selected_candidate_ids=[candidate.candidate_id] if candidate.selected else [],
                meta=dict(self.current_candidate_set.meta),
            )

        def _set_current_candidate(self, candidate_id: str) -> None:
            if self.current_candidate_set is None:
                return
            if candidate_id == self.current_candidate_id and self.current_plan is not None:
                self.refresh_selection_panel()
                self.refresh_canvas()
                return
            self._cancel_preview_refresh()
            self.current_candidate_id = candidate_id
            candidate_plan_source = self._build_candidate_plan_source(candidate_id)
            self.current_plan = candidate_to_plan(candidate_plan_source, candidate_id)
            if not self._restore_cached_preview(candidate_id=candidate_id):
                self.preview_state.select_candidate()
                self.refresh_mission_preview(show_errors=False)
            if self.candidate_tree.exists(candidate_id):
                self._syncing_candidate_tree = True
                try:
                    self.candidate_tree.selection_set(candidate_id)
                    self.candidate_tree.focus(candidate_id)
                finally:
                    self._syncing_candidate_tree = False
            self.refresh_selection_panel()
            self.refresh_canvas()

        def _resolve_auto_planning_config(self) -> AutoPlanningConfig:
            min_total_length = resolve_min_total_length_text(self.auto_min_total_length_var.get())
            max_total_length = resolve_max_total_length_text(self.auto_max_total_length_var.get())
            min_frame_count = resolve_min_frame_count_text(self.auto_min_frame_count_var.get())
            max_frame_count = resolve_max_frame_count_text(self.auto_max_frame_count_var.get())
            export_options = self._resolve_export_options()
            if min_total_length is not None and max_total_length is not None and min_total_length > max_total_length:
                raise GraphSchemaError("自动规划最小长度必须小于等于最大长度。")
            if min_frame_count is not None and max_frame_count is not None and min_frame_count > max_frame_count:
                raise GraphSchemaError("自动规划最小帧数必须小于等于最大帧数。")
            return AutoPlanningConfig(
                max_output_routes=int(self.auto_max_output_routes_var.get().strip() or "20"),
                max_routes_per_pair=int(self.auto_max_routes_per_pair_var.get().strip() or "3"),
                max_anchor_pairs_to_evaluate=int(self.auto_max_anchor_pairs_var.get().strip() or "100"),
                min_frame_count=min_frame_count,
                max_frame_count=max_frame_count,
                distance_per_frame=float(self.auto_distance_per_frame_var.get().strip() or "1.0"),
                min_total_length=min_total_length,
                max_total_length=max_total_length,
                max_edge_pass_factor=float(self.edge_pass_factor_var.get().strip() or args.max_edge_pass_factor),
                max_search_states=int(self.auto_max_search_states_var.get().strip() or "50000"),
                min_endpoint_distance=float(self.auto_min_endpoint_distance_var.get().strip() or "0"),
                prefer_connected_anchors=bool(self.auto_prefer_connected_anchors_var.get()),
                prefer_route_diversity=bool(self.auto_prefer_route_diversity_var.get()),
                allow_reverse_direction_counterparts=bool(self.auto_allow_reverse_direction_counterparts_var.get()),
                coverage_weight=float(self.auto_coverage_weight_var.get().strip() or "1.0"),
                diversity_weight=float(self.auto_diversity_weight_var.get().strip() or "0.45"),
                anchor_weight=float(self.auto_anchor_weight_var.get().strip() or "0.35"),
                reverse_penalty_weight=float(self.auto_reverse_penalty_weight_var.get().strip() or "0.2"),
                allowed_route_group_colors=tuple(self._auto_allowed_route_group_colors),
                excluded_endpoint_group_colors=tuple(self._auto_excluded_endpoint_group_colors),
                export_config=AutoPlanningExportConfig.from_mapping(export_options),
            )

        def generate_routes(self) -> None:
            self._debug_log("generate_routes click")
            if self._route_generation_active:
                messagebox.showinfo(
                    "候选轨迹生成",
                    "候选轨迹仍在后台生成，请等待当前任务完成。",
                )
                return
            planning_mode = self.planning_mode_var.get().strip().lower()
            try:
                self._sync_current_group_config_to_graph_meta()
                graph_payload = self.graph.to_dict()
                if planning_mode == "auto":
                    auto_config = self._resolve_auto_planning_config()
                    self.root.after(
                        1,
                        lambda: self._begin_auto_route_generation(
                            graph_payload=graph_payload,
                            auto_config=auto_config,
                        ),
                    )
                    return
                if not self.start_node or not self.end_node:
                    messagebox.showinfo("生成候选轨迹", "请先设置起点和终点。")
                    return
                max_routes = int(self.max_routes_var.get().strip() or args.max_routes)
                max_edge_pass_factor = float(
                    self.edge_pass_factor_var.get().strip() or args.max_edge_pass_factor
                )
                min_total_length = resolve_min_total_length_text(self.min_total_length_var.get())
                max_total_length = resolve_max_total_length_text(self.max_total_length_var.get())
                min_frame_count = resolve_min_frame_count_text(self.min_frame_count_var.get())
                max_frame_count = resolve_max_frame_count_text(self.max_frame_count_var.get())
                if (
                    min_total_length is not None
                    and max_total_length is not None
                    and min_total_length > max_total_length
                ):
                    raise GraphSchemaError("Min Total Length must be less than or equal to Max Total Length.")
                if (
                    min_frame_count is not None
                    and max_frame_count is not None
                    and min_frame_count > max_frame_count
                ):
                    raise GraphSchemaError("Min Trajectory Frame Count must be less than or equal to Max Trajectory Frame Count.")
            except ValueError:
                messagebox.showerror("候选轨迹生成", "参数必须是有效数值。")
                return
            except GraphSchemaError as exc:
                messagebox.showerror("候选轨迹生成", str(exc))
                return

            start_node = self.start_node
            end_node = self.end_node
            via_nodes = list(self.via_nodes)
            self.root.after(
                1,
                lambda: self._begin_route_generation(
                    graph_payload=graph_payload,
                    start_node=start_node,
                    via_nodes=via_nodes,
                    end_node=end_node,
                    max_routes=max_routes,
                    max_edge_pass_factor=max_edge_pass_factor,
                    min_total_length=min_total_length,
                    max_total_length=max_total_length,
                ),
            )

        def _build_candidate_export_set(self, candidate_ids: list[str]) -> RouteCandidateSet:
            if self.current_candidate_set is None:
                raise GraphSchemaError("请先生成候选轨迹。")
            candidate_id_set = set(candidate_ids)
            candidates = [
                candidate
                for candidate in self.current_candidate_set.candidates
                if candidate.candidate_id in candidate_id_set
            ]
            if not candidates:
                raise GraphSchemaError("没有可导出的候选轨迹。")
            planning_mode = self.current_candidate_set.meta.get("planning_mode")
            if planning_mode != "auto":
                export_set = RouteCandidateSet(
                    env_id=self.current_candidate_set.env_id,
                    graph_name=self.current_candidate_set.graph_name,
                    anchor_nodes=list(self.current_candidate_set.anchor_nodes),
                    candidates=candidates,
                    node_lookup=self.current_candidate_set.node_lookup,
                    selected_candidate_ids=list(candidate_ids),
                    meta=dict(self.current_candidate_set.meta),
                )
                for candidate in export_set.candidates:
                    candidate.selected = candidate.candidate_id in candidate_id_set
                export_set.sync_selected_ids()
                return export_set

            stitched_candidates: list[RouteCandidate] = []
            for index, candidate_id in enumerate(candidate_ids, start=1):
                candidate = self.current_candidate_set.get_candidate(candidate_id)
                start_node = str(candidate.meta.get("auto_start_node") or "")
                end_node = str(candidate.meta.get("auto_end_node") or "")
                if not start_node or not end_node:
                    raise GraphSchemaError(f"自动规划候选 `{candidate_id}` 缺少起点或终点信息。")
                stitched_candidate = RouteCandidate.from_mapping(candidate.to_dict())
                stitched_candidate.selected = True
                stitched_candidate.rank = index
                stitched_candidates.append(stitched_candidate)

            export_set = RouteCandidateSet(
                env_id=self.current_candidate_set.env_id,
                graph_name=self.current_candidate_set.graph_name,
                anchor_nodes=[],
                candidates=stitched_candidates,
                node_lookup=self.current_candidate_set.node_lookup,
                selected_candidate_ids=[candidate.candidate_id for candidate in stitched_candidates],
                meta=dict(self.current_candidate_set.meta),
            )
            return export_set

        def _selected_candidate_ids_in_tree(self) -> list[str]:
            candidate_ids: list[str] = []
            seen_ids: set[str] = set()
            for item in self.candidate_tree.selection():
                values = self.candidate_tree.item(item, "values")
                if len(values) < 3:
                    continue
                candidate_id = str(values[2])
                if candidate_id in seen_ids:
                    continue
                seen_ids.add(candidate_id)
                candidate_ids.append(candidate_id)
            return candidate_ids

        def _resolve_keep_target_candidate_ids(
            self,
            *,
            dialog_title: str,
            allow_current_fallback: bool,
        ) -> list[str] | None:
            if self.current_candidate_set is None:
                messagebox.showinfo(dialog_title, "请先生成候选轨迹。")
                return None
            candidate_ids = self._selected_candidate_ids_in_tree()
            if candidate_ids:
                return candidate_ids
            if allow_current_fallback and self.current_candidate_id is not None:
                return [str(self.current_candidate_id)]
            if allow_current_fallback:
                messagebox.showinfo(dialog_title, "请先生成并选中一条候选轨迹。")
            else:
                messagebox.showinfo(dialog_title, "请先在候选列表中多选至少一条轨迹。")
            return None

        def _restore_candidate_tree_selection(
            self,
            candidate_ids: list[str],
            *,
            focus_candidate_id: str | None = None,
        ) -> None:
            if not candidate_ids:
                return
            candidate_id_set = {str(candidate_id) for candidate_id in candidate_ids}
            selected_items: list[str] = []
            focus_item: str | None = None
            for item in self.candidate_tree.get_children():
                values = self.candidate_tree.item(item, "values")
                candidate_id = str(values[2]) if len(values) >= 3 else str(item)
                if candidate_id not in candidate_id_set:
                    continue
                selected_items.append(item)
                if focus_candidate_id is not None and candidate_id == str(focus_candidate_id):
                    focus_item = item
            if not selected_items:
                return
            if focus_item is None:
                focus_item = selected_items[0]
            self._syncing_candidate_tree = True
            try:
                self.candidate_tree.selection_set(selected_items)
                self.candidate_tree.focus(focus_item)
            finally:
                self._syncing_candidate_tree = False

        def _set_candidates_selected(
            self,
            candidate_ids: list[str],
            selected: bool,
            *,
            focus_candidate_id: str | None = None,
        ) -> int:
            if self.current_candidate_set is None:
                return 0
            updated_count = 0
            for candidate_id in candidate_ids:
                candidate = self.current_candidate_set.get_candidate(candidate_id)
                if candidate.selected != selected:
                    candidate.selected = selected
                    updated_count += 1
            self.current_candidate_set.sync_selected_ids()
            self.refresh_candidate_tree()
            self._restore_candidate_tree_selection(candidate_ids, focus_candidate_id=focus_candidate_id)
            self.refresh_selection_panel()
            return updated_count

        def _toggle_candidates_selected(self, candidate_ids: list[str]) -> tuple[bool, int]:
            if self.current_candidate_set is None:
                return False, 0
            candidates = [self.current_candidate_set.get_candidate(candidate_id) for candidate_id in candidate_ids]
            next_selected = not all(candidate.selected for candidate in candidates)
            focus_candidate_id = (
                self.current_candidate_id
                if self.current_candidate_id is not None and self.current_candidate_id in candidate_ids
                else candidate_ids[0]
            )
            updated_count = self._set_candidates_selected(
                candidate_ids,
                next_selected,
                focus_candidate_id=focus_candidate_id,
            )
            return next_selected, updated_count

        def toggle_keep_current_candidate(self) -> None:
            candidate_ids = self._resolve_keep_target_candidate_ids(
                dialog_title="切换保留状态",
                allow_current_fallback=True,
            )
            if not candidate_ids:
                return
            next_selected, updated_count = self._toggle_candidates_selected(candidate_ids)
            if len(candidate_ids) == 1:
                self.log(f"{'已保留' if next_selected else '已取消保留'} {candidate_ids[0]}")
                return
            if next_selected:
                self.log(f"已保留 {len(candidate_ids)} 条多选候选轨迹（新增 {updated_count} 条）")
            else:
                self.log(f"已取消保留 {len(candidate_ids)} 条多选候选轨迹（变更 {updated_count} 条）")

        def keep_selected_candidates(self) -> None:
            candidate_ids = self._resolve_keep_target_candidate_ids(
                dialog_title="保留当前多选项",
                allow_current_fallback=False,
            )
            if not candidate_ids:
                return
            focus_candidate_id = (
                self.current_candidate_id
                if self.current_candidate_id is not None and self.current_candidate_id in candidate_ids
                else candidate_ids[0]
            )
            updated_count = self._set_candidates_selected(
                candidate_ids,
                True,
                focus_candidate_id=focus_candidate_id,
            )
            self.log(f"已保留 {len(candidate_ids)} 条多选候选轨迹（新增 {updated_count} 条）")

        def unkeep_selected_candidates(self) -> None:
            candidate_ids = self._resolve_keep_target_candidate_ids(
                dialog_title="取消保留当前多选项",
                allow_current_fallback=False,
            )
            if not candidate_ids:
                return
            focus_candidate_id = (
                self.current_candidate_id
                if self.current_candidate_id is not None and self.current_candidate_id in candidate_ids
                else candidate_ids[0]
            )
            updated_count = self._set_candidates_selected(
                candidate_ids,
                False,
                focus_candidate_id=focus_candidate_id,
            )
            self.log(f"已取消保留 {len(candidate_ids)} 条多选候选轨迹（变更 {updated_count} 条）")

        def save_candidate_set_ui(self) -> None:
            if self.current_candidate_set is None:
                messagebox.showinfo("保存候选集", "请先生成候选轨迹。")
                return
            path = filedialog.asksaveasfilename(
                title="保存候选集 JSON",
                defaultextension=".candidates.json",
                initialdir=str(resolve_data_path("plans")),
                initialfile=f"{self.graph.graph_name}_routes.candidates.json",
                filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return
            save_candidate_set(path, self.current_candidate_set)
            self.log(f"已保存候选集：{path}")

        def export_mission_ui(self) -> None:
            if self.current_plan is None or self.current_candidate_id is None:
                messagebox.showinfo("导出 Mission", "请先生成并选中一条候选轨迹。")
                return
            path = filedialog.asksaveasfilename(
                title="导出 Mission JSON",
                defaultextension=".json",
                initialdir=str(resolve_data_path("missions")),
                initialfile=f"{self.graph.graph_name}_{self.current_candidate_id}.json",
                filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return
            try:
                self._sync_route_meta_for_export()
                export_options = self._resolve_export_options()
                mission = export_mission(
                    self.current_plan,
                    output_path=path,
                    step_distance=float(export_options["step_distance"]),
                    fps=float(export_options["fps"]),
                    altitude_mode=str(export_options["altitude_mode"]),
                    fixed_z=export_options["fixed_z"],
                    altitude_offset=float(export_options["altitude_offset"]),
                    takeoff_landing_relative_z=export_options["takeoff_landing_relative_z"],
                    takeoff_landing_step_distance=export_options["takeoff_landing_step_distance"],
                    node_sample_radius=float(export_options["node_sample_radius"]),
                    random_seed=export_options["random_seed"],
                    turn_smoothing_enabled=bool(export_options["turn_smoothing_enabled"]),
                    corner_radius=float(export_options["corner_radius"]),
                    small_turn_yaw_blend_threshold_deg=float(
                        export_options["small_turn_yaw_blend_threshold_deg"]
                    ),
                    corner_min_angle_deg=float(export_options["corner_min_angle_deg"]),
                    u_turn_threshold_deg=float(export_options["u_turn_threshold_deg"]),
                    u_turn_transition_distance=float(export_options["u_turn_transition_distance"]),
                    corner_max_yaw_step_deg=float(export_options["corner_max_yaw_step_deg"]),
                    u_turn_pivot_yaw_step_deg=float(export_options["u_turn_pivot_yaw_step_deg"]),
                )
            except GraphSchemaError as exc:
                messagebox.showerror("导出 Mission", str(exc))
                self.log(f"Mission 导出失败：{exc}")
                return
            self._set_preview(mission)
            self._refresh_preview_status()
            self.log(f"已导出 Mission：{path}")
            self.refresh_canvas()

        def export_selected_missions_ui(self) -> None:
            if self.current_candidate_set is None:
                messagebox.showinfo("导出当前多选项 Mission", "请先生成候选轨迹。")
                return
            candidate_ids = self._selected_candidate_ids_in_tree()
            if not candidate_ids:
                messagebox.showinfo("导出当前多选项 Mission", "请先在候选列表中多选至少一条轨迹。")
                return
            output_dir = filedialog.askdirectory(
                title="导出当前多选项 Mission 到目录",
                initialdir=str(resolve_data_path("missions")),
            )
            if not output_dir:
                return
            try:
                self._sync_route_meta_for_export()
                export_candidate_set = self._build_candidate_export_set(candidate_ids)
                export_options = self._resolve_export_options()
                summary = export_candidate_set_missions(
                    export_candidate_set,
                    output_dir,
                    selected_only=True,
                    step_distance=float(export_options["step_distance"]),
                    fps=float(export_options["fps"]),
                    altitude_mode=str(export_options["altitude_mode"]),
                    fixed_z=export_options["fixed_z"],
                    altitude_offset=float(export_options["altitude_offset"]),
                    takeoff_landing_relative_z=export_options["takeoff_landing_relative_z"],
                    takeoff_landing_step_distance=export_options["takeoff_landing_step_distance"],
                    node_sample_radius=float(export_options["node_sample_radius"]),
                    random_seed=export_options["random_seed"],
                    turn_smoothing_enabled=bool(export_options["turn_smoothing_enabled"]),
                    corner_radius=float(export_options["corner_radius"]),
                    small_turn_yaw_blend_threshold_deg=float(
                        export_options["small_turn_yaw_blend_threshold_deg"]
                    ),
                    corner_min_angle_deg=float(export_options["corner_min_angle_deg"]),
                    u_turn_threshold_deg=float(export_options["u_turn_threshold_deg"]),
                    u_turn_transition_distance=float(export_options["u_turn_transition_distance"]),
                    corner_max_yaw_step_deg=float(export_options["corner_max_yaw_step_deg"]),
                    u_turn_pivot_yaw_step_deg=float(export_options["u_turn_pivot_yaw_step_deg"]),
                )
            except GraphSchemaError as exc:
                messagebox.showerror("导出当前多选项 Mission", str(exc))
                self.log(f"多选 Mission 导出失败：{exc}")
                return
            except Exception as exc:
                self.log(f"多选 Mission 导出异常：{exc}\n{traceback.format_exc()}")
                messagebox.showerror("导出当前多选项 Mission", str(exc))
                return

            summary_lines = [
                f"输出目录：{summary['output_dir']}",
                f"成功：{len(summary['succeeded'])}",
                f"失败：{len(summary['failed'])}",
            ]
            if summary["failed"]:
                for candidate_id in summary["failed"]:
                    summary_lines.append(f"{candidate_id}: {summary['errors'][candidate_id]}")
                messagebox.showwarning("导出当前多选项 Mission", "\n".join(summary_lines))
            else:
                messagebox.showinfo("导出当前多选项 Mission", "\n".join(summary_lines))
            self.log(
                f"多选 Mission 导出完成：成功={len(summary['succeeded'])}，"
                f"失败={len(summary['failed'])}，目录={summary['output_dir']}"
            )

        def export_kept_missions_ui(self) -> None:
            if self.current_candidate_set is None:
                messagebox.showinfo("导出已保留 Mission", "请先生成候选轨迹。")
                return
            self.current_candidate_set.sync_selected_ids()
            if not self.current_candidate_set.selected_candidate_ids:
                messagebox.showinfo("导出已保留 Mission", "请至少保留一条候选轨迹。")
                return
            output_dir = filedialog.askdirectory(
                title="导出已保留 Mission 到目录",
                initialdir=str(resolve_data_path("missions")),
            )
            if not output_dir:
                return
            try:
                self._sync_route_meta_for_export()
                export_candidate_set = self._build_candidate_export_set(self.current_candidate_set.selected_candidate_ids)
                export_options = self._resolve_export_options()
                summary = export_candidate_set_missions(
                    export_candidate_set,
                    output_dir,
                    selected_only=True,
                    step_distance=float(export_options["step_distance"]),
                    fps=float(export_options["fps"]),
                    altitude_mode=str(export_options["altitude_mode"]),
                    fixed_z=export_options["fixed_z"],
                    altitude_offset=float(export_options["altitude_offset"]),
                    takeoff_landing_relative_z=export_options["takeoff_landing_relative_z"],
                    takeoff_landing_step_distance=export_options["takeoff_landing_step_distance"],
                    node_sample_radius=float(export_options["node_sample_radius"]),
                    random_seed=export_options["random_seed"],
                    turn_smoothing_enabled=bool(export_options["turn_smoothing_enabled"]),
                    corner_radius=float(export_options["corner_radius"]),
                    small_turn_yaw_blend_threshold_deg=float(
                        export_options["small_turn_yaw_blend_threshold_deg"]
                    ),
                    corner_min_angle_deg=float(export_options["corner_min_angle_deg"]),
                    u_turn_threshold_deg=float(export_options["u_turn_threshold_deg"]),
                    u_turn_transition_distance=float(export_options["u_turn_transition_distance"]),
                    corner_max_yaw_step_deg=float(export_options["corner_max_yaw_step_deg"]),
                    u_turn_pivot_yaw_step_deg=float(export_options["u_turn_pivot_yaw_step_deg"]),
                )
            except GraphSchemaError as exc:
                messagebox.showerror("导出已保留 Mission", str(exc))
                self.log(f"批量 Mission 导出失败：{exc}")
                return
            except Exception as exc:
                self.log(f"批量 Mission 导出异常：{exc}\n{traceback.format_exc()}")
                messagebox.showerror("导出已保留 Mission", str(exc))
                return

            summary_lines = [
                f"输出目录：{summary['output_dir']}",
                f"成功：{len(summary['succeeded'])}",
                f"失败：{len(summary['failed'])}",
            ]
            if summary["failed"]:
                for candidate_id in summary["failed"]:
                    summary_lines.append(f"{candidate_id}: {summary['errors'][candidate_id]}")
                messagebox.showwarning("导出已保留 Mission", "\n".join(summary_lines))
            else:
                messagebox.showinfo("导出已保留 Mission", "\n".join(summary_lines))
            self.log(
                f"批量 Mission 导出完成：成功={len(summary['succeeded'])}，"
                f"失败={len(summary['failed'])}，目录={summary['output_dir']}"
            )

        def export_preview_png(self) -> None:
            if self.current_plan is None:
                messagebox.showinfo("导出预览图", "请先生成并选中一条候选轨迹。")
                return
            path = filedialog.asksaveasfilename(
                title="导出预览 PNG",
                defaultextension=".png",
                initialdir=str(resolve_data_path("previews")),
                initialfile=f"{self.graph.graph_name}_{self.current_candidate_id or 'preview'}.png",
                filetypes=[("PNG", "*.png"), ("All files", "*.*")],
            )
            if not path:
                return
            render_graph_preview(
                self.graph,
                path,
                plan=self.current_plan,
                mission_positions=None
                if self.preview_state.mission is None
                else self.preview_state.mission["positions"],
                view_state=self._current_canvas_view_state(),
            )
            self.log(f"已导出预览 PNG：{path}")

    root = tk.Tk()
    try:
        GraphGuiApp(root)
    except GraphSchemaError as exc:
        messagebox.showerror("图结构错误", str(exc))
        root.destroy()
        return 1
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return launch_gui(args)


if __name__ == "__main__":
    raise SystemExit(main())
