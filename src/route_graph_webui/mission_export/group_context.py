from __future__ import annotations

from dataclasses import dataclass

from route_graph_webui.graph.grouping import normalize_hex_color, read_graph_group_configs
from route_graph_webui.graph.meta import GRAPH_GROUP_CONFIGS_META_KEY, GROUP_CONFIG_LABEL_KEY
from route_graph_webui.graph.model import GraphSchemaError, RoutePlan

@dataclass(frozen=True, slots=True)
class NodeExportSettings:
    altitude_mode: str
    fixed_z: float | None
    altitude_offset: float
    node_sample_radius: float
    takeoff_landing_relative_z: float | None
    takeoff_landing_step_distance: float | None

def _resolve_graph_default_altitude(plan: RoutePlan) -> float | None:
    raw_value = plan.meta.get("graph_default_altitude")
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise GraphSchemaError("RoutePlan `meta.graph_default_altitude` must be numeric") from exc


def _read_float_lookup_from_plan_meta(plan: RoutePlan, key: str) -> dict[str, float]:
    raw_value = plan.meta.get(key)
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise GraphSchemaError(f"RoutePlan `meta.{key}` must be a mapping")
    resolved: dict[str, float] = {}
    for raw_name, raw_number in raw_value.items():
        try:
            resolved[str(raw_name)] = float(raw_number)
        except (TypeError, ValueError) as exc:
            raise GraphSchemaError(f"RoutePlan `meta.{key}` contains non-numeric value for `{raw_name}`") from exc
    return resolved


def _read_node_group_lookup_from_plan_meta(plan: RoutePlan) -> dict[str, str]:
    raw_value = plan.meta.get("node_group_lookup_v1")
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise GraphSchemaError("RoutePlan `meta.node_group_lookup_v1` must be a mapping")
    resolved: dict[str, str] = {}
    for raw_node_id, raw_color in raw_value.items():
        try:
            resolved[str(raw_node_id)] = normalize_hex_color(
                raw_color,
                field_name=f"RoutePlan `meta.node_group_lookup_v1.{raw_node_id}`",
            )
        except GraphSchemaError as exc:
            raise GraphSchemaError(str(exc)) from exc
    return resolved


def _parse_group_optional_float(
    raw_config: dict[str, str],
    *,
    key: str,
    fallback_value: float | None,
    group_label: str,
    non_negative: bool = False,
    positive: bool = False,
) -> float | None:
    if key not in raw_config:
        return fallback_value
    text = raw_config.get(key, "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise GraphSchemaError(f"Color group `{group_label}` field `{key}` must be numeric or left empty") from exc
    if non_negative and value < 0:
        raise GraphSchemaError(f"Color group `{group_label}` field `{key}` must be non-negative")
    if positive and value <= 0:
        raise GraphSchemaError(f"Color group `{group_label}` field `{key}` must be positive")
    return float(value)


def _parse_group_required_float(
    raw_config: dict[str, str],
    *,
    key: str,
    fallback_value: float,
    group_label: str,
    non_negative: bool = False,
) -> float:
    if key not in raw_config:
        value = fallback_value
    else:
        text = raw_config.get(key, "").strip()
        if not text:
            value = 0.0
        else:
            try:
                value = float(text)
            except ValueError as exc:
                raise GraphSchemaError(f"Color group `{group_label}` field `{key}` must be numeric") from exc
    if non_negative and value < 0:
        raise GraphSchemaError(f"Color group `{group_label}` field `{key}` must be non-negative")
    return float(value)


def _resolve_group_altitude_mode(
    raw_config: dict[str, str],
    *,
    fallback_value: str,
    group_label: str,
) -> str:
    if "altitude_mode" not in raw_config:
        mode = fallback_value
    else:
        mode = raw_config.get("altitude_mode", "").strip() or fallback_value
    if mode not in {"fixed", "follow_nodes"}:
        raise GraphSchemaError(
            f"Color group `{group_label}` field `altitude_mode` must be one of: fixed, follow_nodes"
        )
    return mode


def _resolve_group_settings(
    *,
    color: str,
    raw_config: dict[str, str],
    group_average_z: float | None,
    fallback_altitude_mode: str,
    fallback_fixed_z: float | None,
    fallback_altitude_offset: float,
    fallback_node_sample_radius: float,
    fallback_takeoff_landing_relative_z: float | None,
    fallback_takeoff_landing_step_distance: float | None,
) -> NodeExportSettings:
    group_label = raw_config.get(GROUP_CONFIG_LABEL_KEY, "").strip() or color
    altitude_mode = _resolve_group_altitude_mode(
        raw_config,
        fallback_value=fallback_altitude_mode,
        group_label=group_label,
    )
    altitude_offset = _parse_group_required_float(
        raw_config,
        key="altitude_offset",
        fallback_value=float(fallback_altitude_offset),
        group_label=group_label,
    )
    node_sample_radius = _parse_group_required_float(
        raw_config,
        key="node_sample_radius",
        fallback_value=float(fallback_node_sample_radius),
        group_label=group_label,
        non_negative=True,
    )
    fixed_z = _parse_group_optional_float(
        raw_config,
        key="fixed_z",
        fallback_value=fallback_fixed_z,
        group_label=group_label,
    )
    if altitude_mode == "fixed" and fixed_z is None and group_average_z is not None:
        fixed_z = float(group_average_z)
    takeoff_landing_relative_z = _parse_group_optional_float(
        raw_config,
        key="takeoff_landing_relative_z",
        fallback_value=fallback_takeoff_landing_relative_z,
        group_label=group_label,
        non_negative=True,
    )
    takeoff_landing_step_distance = _parse_group_optional_float(
        raw_config,
        key="takeoff_landing_step_distance",
        fallback_value=fallback_takeoff_landing_step_distance,
        group_label=group_label,
        positive=True,
    )
    return NodeExportSettings(
        altitude_mode=altitude_mode,
        fixed_z=fixed_z,
        altitude_offset=altitude_offset,
        node_sample_radius=node_sample_radius,
        takeoff_landing_relative_z=takeoff_landing_relative_z,
        takeoff_landing_step_distance=takeoff_landing_step_distance,
    )


def _resolve_plan_grouped_export_context(
    plan: RoutePlan,
    *,
    fallback_altitude_mode: str,
    fallback_fixed_z: float | None,
    fallback_altitude_offset: float,
    fallback_node_sample_radius: float,
    fallback_takeoff_landing_relative_z: float | None,
    fallback_takeoff_landing_step_distance: float | None,
) -> tuple[dict[str, NodeExportSettings], dict[str, str], dict[str, float], dict[str, NodeExportSettings]]:
    node_group_lookup = _read_node_group_lookup_from_plan_meta(plan)
    if not node_group_lookup:
        return {}, {}, {}, {}
    original_node_z_lookup = _read_float_lookup_from_plan_meta(plan, "original_node_z_lookup_v1")
    group_average_z_lookup = _read_float_lookup_from_plan_meta(plan, "group_average_z_lookup_v1")
    raw_group_configs = read_graph_group_configs({GRAPH_GROUP_CONFIGS_META_KEY: plan.meta.get(GRAPH_GROUP_CONFIGS_META_KEY)})
    distinct_colors = {color for color in node_group_lookup.values()}
    if not distinct_colors:
        return {}, {}, original_node_z_lookup, {}
    group_settings_lookup: dict[str, NodeExportSettings] = {}
    for color in sorted(distinct_colors):
        group_settings_lookup[color] = _resolve_group_settings(
            color=color,
            raw_config=raw_group_configs.get(color, {}),
            group_average_z=group_average_z_lookup.get(color),
            fallback_altitude_mode=fallback_altitude_mode,
            fallback_fixed_z=fallback_fixed_z,
            fallback_altitude_offset=fallback_altitude_offset,
            fallback_node_sample_radius=fallback_node_sample_radius,
            fallback_takeoff_landing_relative_z=fallback_takeoff_landing_relative_z,
            fallback_takeoff_landing_step_distance=fallback_takeoff_landing_step_distance,
        )
    node_settings_lookup: dict[str, NodeExportSettings] = {}
    for node_id in plan.node_lookup:
        color = node_group_lookup.get(node_id)
        if color is None:
            continue
        node_settings_lookup[node_id] = group_settings_lookup[color]
    return node_settings_lookup, node_group_lookup, original_node_z_lookup, group_settings_lookup
__all__ = [
    "NodeExportSettings",
    "_parse_group_optional_float",
    "_parse_group_required_float",
    "_read_float_lookup_from_plan_meta",
    "_read_node_group_lookup_from_plan_meta",
    "_resolve_graph_default_altitude",
    "_resolve_group_altitude_mode",
    "_resolve_group_settings",
    "_resolve_plan_grouped_export_context",
]
