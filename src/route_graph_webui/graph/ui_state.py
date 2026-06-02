from __future__ import annotations

from typing import Any, Mapping


from .grouping import normalize_hex_color
from .meta import (
    GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY,
    GRAPH_GUI_EXPORT_INPUTS_META_KEY,
    GRAPH_GUI_WEBUI_INPUTS_META_KEY,
)
from .model import GraphSchemaError


GRAPH_GUI_AUTO_PLAN_LIST_KEYS = (
    "auto_allowed_route_group_colors",
    "auto_excluded_endpoint_group_colors",
)
GRAPH_GUI_GLOBAL_EXPORT_TEXT_KEYS = (
    "step_distance",
    "fps",
    "random_seed",
    "corner_radius",
    "small_turn_yaw_blend_threshold_deg",
    "corner_min_angle_deg",
    "u_turn_threshold_deg",
    "u_turn_transition_distance",
    "corner_max_yaw_step_deg",
    "u_turn_pivot_yaw_step_deg",
)
GRAPH_GUI_EXPORT_BOOL_KEYS = ("turn_smoothing_enabled",)
GRAPH_GUI_GROUP_EXPORT_TEXT_KEYS = (
    "node_sample_radius",
    "altitude_mode",
    "fixed_z",
    "altitude_offset",
    "takeoff_landing_relative_z",
    "takeoff_landing_step_distance",
)
GRAPH_GUI_WEBUI_TEXT_KEYS = (
    "planning_mode",
    "max_routes",
    "max_edge_pass_factor",
    "min_total_length",
    "max_total_length",
    "min_frame_count",
    "max_frame_count",
    "candidate_set_file_name",
    "missions_output_dir",
)
GRAPH_GUI_WEBUI_COLOR_KEYS = ("active_group_color",)

EXPORT_ALTITUDE_MODES = ("fixed", "follow_nodes")
PLANNING_MODES = ("manual", "auto")


def normalize_graph_gui_export_inputs(payload: Any) -> dict[str, str | bool]:
    if not isinstance(payload, Mapping):
        return {}

    normalized: dict[str, str | bool] = {}
    for key in (*GRAPH_GUI_GLOBAL_EXPORT_TEXT_KEYS, *GRAPH_GUI_GROUP_EXPORT_TEXT_KEYS):
        if key not in payload:
            continue
        raw_value = payload.get(key)
        text_value: str | None = None
        if isinstance(raw_value, str):
            text_value = raw_value
        elif isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            text_value = str(raw_value)
        if text_value is None:
            continue
        if key == "altitude_mode" and text_value.strip() not in EXPORT_ALTITUDE_MODES:
            continue
        normalized[key] = text_value

    for key in GRAPH_GUI_EXPORT_BOOL_KEYS:
        if key not in payload:
            continue
        raw_value = payload.get(key)
        if isinstance(raw_value, bool):
            normalized[key] = raw_value
        elif isinstance(raw_value, int) and raw_value in {0, 1}:
            normalized[key] = bool(raw_value)

    return normalized


def read_graph_gui_export_inputs(meta: Mapping[str, Any] | None) -> dict[str, str | bool]:
    if not isinstance(meta, Mapping):
        return {}
    raw_payload = meta.get(GRAPH_GUI_EXPORT_INPUTS_META_KEY)
    return normalize_graph_gui_export_inputs(raw_payload)


def write_graph_gui_export_inputs(
    meta: dict[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, str | bool]:
    normalized = normalize_graph_gui_export_inputs(dict(payload))
    meta[GRAPH_GUI_EXPORT_INPUTS_META_KEY] = normalized
    return normalized


def has_graph_gui_export_input(meta: Mapping[str, Any] | None, key: str) -> bool:
    if not isinstance(meta, Mapping):
        return False
    raw_payload = meta.get(GRAPH_GUI_EXPORT_INPUTS_META_KEY)
    return isinstance(raw_payload, Mapping) and key in raw_payload


def normalize_graph_gui_auto_plan_inputs(payload: Any) -> dict[str, str | bool | list[str]]:
    if not isinstance(payload, Mapping):
        return {}

    normalized: dict[str, str | bool | list[str]] = {}
    text_keys = (
        "planning_mode",
        "auto_max_output_routes",
        "auto_max_routes_per_pair",
        "auto_max_anchor_pairs_to_evaluate",
        "auto_distance_per_frame",
        "auto_min_total_length",
        "auto_max_total_length",
        "auto_min_frame_count",
        "auto_max_frame_count",
        "auto_min_endpoint_distance",
        "auto_max_search_states",
        "auto_coverage_weight",
        "auto_diversity_weight",
        "auto_anchor_weight",
        "auto_reverse_penalty_weight",
        "auto_node_coverage_weight",
        "auto_endpoint_reuse_weight",
    )
    bool_keys = (
        "auto_prefer_connected_anchors",
        "auto_prefer_route_diversity",
        "auto_allow_reverse_direction_counterparts",
        "auto_enable_global_coverage",
    )

    for key in text_keys:
        if key not in payload:
            continue
        raw_value = payload.get(key)
        text_value = "" if raw_value is None else str(raw_value)
        if key == "planning_mode" and text_value not in PLANNING_MODES:
            continue
        normalized[key] = text_value

    for key in bool_keys:
        if key not in payload:
            continue
        raw_value = payload.get(key)
        if isinstance(raw_value, bool):
            normalized[key] = raw_value
        elif isinstance(raw_value, int) and raw_value in {0, 1}:
            normalized[key] = bool(raw_value)

    for key in GRAPH_GUI_AUTO_PLAN_LIST_KEYS:
        if key not in payload:
            continue
        raw_value = payload.get(key)
        if raw_value is None or raw_value == "":
            normalized[key] = []
            continue
        if isinstance(raw_value, str):
            raw_items = [raw_value]
        elif isinstance(raw_value, Mapping):
            continue
        else:
            try:
                raw_items = list(raw_value)
            except TypeError:
                continue
        cleaned: list[str] = []
        seen_colors: set[str] = set()
        for item in raw_items:
            if item is None:
                continue
            if isinstance(item, str) and not item.strip():
                continue
            try:
                color = normalize_hex_color(item, field_name=f"graph GUI auto-plan field `{key}`")
            except GraphSchemaError:
                continue
            if color in seen_colors:
                continue
            seen_colors.add(color)
            cleaned.append(color)
        normalized[key] = cleaned

    return normalized


def read_graph_gui_auto_plan_inputs(meta: Mapping[str, Any] | None) -> dict[str, str | bool | list[str]]:
    if not isinstance(meta, Mapping):
        return {}
    raw_payload = meta.get(GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY)
    return normalize_graph_gui_auto_plan_inputs(raw_payload)


def write_graph_gui_auto_plan_inputs(
    meta: dict[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, str | bool | list[str]]:
    normalized = normalize_graph_gui_auto_plan_inputs(dict(payload))
    meta[GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY] = normalized
    return normalized


def normalize_graph_gui_webui_inputs(payload: Any) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        return {}

    normalized: dict[str, str] = {}
    for key in GRAPH_GUI_WEBUI_TEXT_KEYS:
        if key not in payload:
            continue
        raw_value = payload.get(key)
        text_value: str | None = None
        if raw_value is None:
            text_value = ""
        elif isinstance(raw_value, str):
            text_value = raw_value
        elif isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            text_value = str(raw_value)
        if text_value is None:
            continue
        if key == "planning_mode" and text_value not in PLANNING_MODES:
            continue
        normalized[key] = text_value

    for key in GRAPH_GUI_WEBUI_COLOR_KEYS:
        if key not in payload:
            continue
        raw_value = payload.get(key)
        if raw_value is None or str(raw_value).strip() == "":
            normalized[key] = ""
            continue
        try:
            normalized[key] = normalize_hex_color(raw_value, field_name=key)
        except GraphSchemaError:
            continue

    return normalized


def read_graph_gui_webui_inputs(meta: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(meta, Mapping):
        return {}
    raw_payload = meta.get(GRAPH_GUI_WEBUI_INPUTS_META_KEY)
    return normalize_graph_gui_webui_inputs(raw_payload)


def write_graph_gui_webui_inputs(
    meta: dict[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, str]:
    normalized = normalize_graph_gui_webui_inputs(dict(payload))
    meta[GRAPH_GUI_WEBUI_INPUTS_META_KEY] = normalized
    return normalized
