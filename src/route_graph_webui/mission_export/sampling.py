from __future__ import annotations

import math
import random
from typing import Any

from route_graph_webui.shared.geometry import distance_3d, interpolate_segment_3d
from route_graph_webui.graph.grouping import get_node_sample_radius_override
from route_graph_webui.graph.model import GraphNode, GraphSchemaError, RouteEdgePass, RoutePlan

from .group_context import NodeExportSettings

EPSILON = 1e-9

def _yaw_from_points(start_xyz: list[float], end_xyz: list[float]) -> float | None:
    dx = float(end_xyz[0]) - float(start_xyz[0])
    dy = float(end_xyz[1]) - float(start_xyz[1])
    if abs(dx) < EPSILON and abs(dy) < EPSILON:
        return None
    return math.degrees(math.atan2(dy, dx))


def _resolve_altitude_from_base_z(
    base_z: float,
    *,
    altitude_mode: str,
    fixed_z: float | None,
    altitude_offset: float,
) -> float:
    if altitude_mode == "follow_nodes":
        return base_z + altitude_offset
    if fixed_z is None:
        return base_z + altitude_offset
    return float(fixed_z) + altitude_offset


def _interpolate_segment(start_xyz: list[float], end_xyz: list[float], step_distance: float) -> list[list[float]]:
    try:
        return interpolate_segment_3d(start_xyz, end_xyz, step_distance)
    except ValueError as exc:
        raise GraphSchemaError("`step_distance` must be positive") from exc


def _sample_xy_disk_offset(radius: float, rng: random.Random) -> tuple[float, float]:
    if radius <= 0:
        return 0.0, 0.0
    theta = rng.random() * math.tau
    rho = math.sqrt(rng.random()) * radius
    return rho * math.cos(theta), rho * math.sin(theta)


def _collect_node_sample_radius_overrides(node_lookup: dict[str, GraphNode]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for node_id, node in node_lookup.items():
        radius = get_node_sample_radius_override(node)
        if radius is not None:
            overrides[str(node_id)] = float(radius)
    return overrides


def _build_sampled_node_positions(
    plan: RoutePlan,
    node_lookup: dict[str, GraphNode],
    *,
    altitude_mode: str,
    fixed_z: float | None,
    altitude_offset: float,
    node_sample_radius: float,
    rng: random.Random,
    node_settings_lookup: dict[str, NodeExportSettings] | None = None,
    original_node_z_lookup: dict[str, float] | None = None,
) -> tuple[list[list[float]], dict[str, float], bool]:
    node_sample_radius_overrides = _collect_node_sample_radius_overrides(node_lookup)
    sampled_positions: list[list[float]] = []
    any_disk_sampling = False
    for node_id in plan.planned_nodes:
        node = node_lookup[node_id]
        settings = node_settings_lookup.get(node_id) if node_settings_lookup is not None else None
        resolved_altitude_mode = altitude_mode if settings is None else settings.altitude_mode
        resolved_fixed_z = fixed_z if settings is None else settings.fixed_z
        resolved_altitude_offset = altitude_offset if settings is None else settings.altitude_offset
        base_z = float(
            node.position[2]
            if original_node_z_lookup is None
            else original_node_z_lookup.get(node_id, float(node.position[2]))
        )
        xyz = [
            float(node.position[0]),
            float(node.position[1]),
            _resolve_altitude_from_base_z(
                base_z,
                altitude_mode=resolved_altitude_mode,
                fixed_z=resolved_fixed_z,
                altitude_offset=resolved_altitude_offset,
            ),
        ]
        radius = node_sample_radius_overrides.get(
            node_id,
            float(node_sample_radius if settings is None else settings.node_sample_radius),
        )
        if radius > 0:
            any_disk_sampling = True
        offset_x, offset_y = _sample_xy_disk_offset(radius, rng)
        sampled_positions.append([xyz[0] + offset_x, xyz[1] + offset_y, xyz[2]])
    return sampled_positions, node_sample_radius_overrides, any_disk_sampling


def _xy_distance(point_a: list[float], point_b: list[float]) -> float:
    return math.hypot(float(point_b[0]) - float(point_a[0]), float(point_b[1]) - float(point_a[1]))


def _xyz_distance(point_a: list[float], point_b: list[float]) -> float:
    return distance_3d(point_a, point_b)


def _lerp_xyz(start_xyz: list[float], end_xyz: list[float], ratio: float) -> list[float]:
    return [
        start_xyz[0] + (end_xyz[0] - start_xyz[0]) * ratio,
        start_xyz[1] + (end_xyz[1] - start_xyz[1]) * ratio,
        start_xyz[2] + (end_xyz[2] - start_xyz[2]) * ratio,
    ]


def _normalize_xy(dx: float, dy: float) -> tuple[float, float] | None:
    length = math.hypot(dx, dy)
    if length <= EPSILON:
        return None
    return dx / length, dy / length


def _left_normal(vector: tuple[float, float]) -> tuple[float, float]:
    return -vector[1], vector[0]


def _right_normal(vector: tuple[float, float]) -> tuple[float, float]:
    return vector[1], -vector[0]


def _signed_angle_radians(vector_a: tuple[float, float], vector_b: tuple[float, float]) -> float:
    cross = (vector_a[0] * vector_b[1]) - (vector_a[1] * vector_b[0])
    dot = (vector_a[0] * vector_b[0]) + (vector_a[1] * vector_b[1])
    return math.atan2(cross, dot)


def _normalize_turn_delta_deg(delta_deg: float, preferred_sign: float = 0.0) -> float:
    while delta_deg > 180.0:
        delta_deg -= 360.0
    while delta_deg <= -180.0:
        delta_deg += 360.0
    if abs(abs(delta_deg) - 180.0) <= 1e-6 and preferred_sign != 0.0:
        return 180.0 if preferred_sign > 0.0 else -180.0
    return delta_deg


def _mid_yaw_deg(start_yaw: float, end_yaw: float) -> float:
    delta = _normalize_turn_delta_deg(float(end_yaw) - float(start_yaw))
    return float(start_yaw) + (delta * 0.5)


def _point_near_segment_end(start_xyz: list[float], end_xyz: list[float], trim_xy: float) -> list[float]:
    edge_xy_length = _xy_distance(start_xyz, end_xyz)
    if edge_xy_length <= EPSILON:
        return list(end_xyz)
    ratio = max(0.0, min(1.0, 1.0 - (trim_xy / edge_xy_length)))
    return _lerp_xyz(start_xyz, end_xyz, ratio)


def _point_near_segment_start(start_xyz: list[float], end_xyz: list[float], trim_xy: float) -> list[float]:
    edge_xy_length = _xy_distance(start_xyz, end_xyz)
    if edge_xy_length <= EPSILON:
        return list(start_xyz)
    ratio = max(0.0, min(1.0, trim_xy / edge_xy_length))
    return _lerp_xyz(start_xyz, end_xyz, ratio)


def _build_raw_point(
    *,
    xyz: list[float],
    mode: str,
    node_id: str | None,
    edge_id: str | None,
    segment_index: int | None,
    pass_index: int | None,
    yaw_hint: float | None,
    yaw: float | None = None,
    extra_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "xyz": xyz,
        "mode": mode,
        "node_id": node_id,
        "edge_id": edge_id,
        "segment_index": segment_index,
        "pass_index": pass_index,
        "yaw_hint": yaw_hint,
        "yaw": None if yaw is None else float(yaw),
        "extra_info": dict(extra_info or {}),
    }


def _append_straight_samples(
    raw_points: list[dict[str, Any]],
    *,
    start_xyz: list[float],
    end_xyz: list[float],
    step_distance: float,
    mode: str,
    edge_id: str | None,
    segment_index: int | None,
    pass_index: int | None,
    yaw: float | None,
    end_node_id: str | None = None,
    end_node_yaw_hint: float | None = None,
    extra_info: dict[str, Any] | None = None,
) -> None:
    if _xyz_distance(start_xyz, end_xyz) <= EPSILON:
        return
    samples = _interpolate_segment(start_xyz, end_xyz, step_distance)
    for sample_index, xyz in enumerate(samples):
        is_last_sample = sample_index == len(samples) - 1
        raw_points.append(
            _build_raw_point(
                xyz=xyz,
                mode=mode,
                node_id=end_node_id if is_last_sample else None,
                edge_id=edge_id,
                segment_index=segment_index,
                pass_index=pass_index,
                yaw_hint=end_node_yaw_hint if is_last_sample else None,
                yaw=yaw,
                extra_info=extra_info,
            )
        )


def _build_linear_route_raw_points(
    *,
    planned_nodes: list[str],
    edge_passes: list[RouteEdgePass],
    sampled_node_positions: list[list[float]],
    node_lookup: dict[str, GraphNode],
    step_distance: float,
) -> list[dict[str, Any]]:
    first_node = node_lookup[edge_passes[0].from_node] if edge_passes else node_lookup[planned_nodes[0]]
    raw_points = [
        _build_raw_point(
            xyz=list(sampled_node_positions[0]),
            mode="graph_route",
            node_id=first_node.id,
            edge_id=None,
            segment_index=0 if edge_passes else None,
            pass_index=None,
            yaw_hint=first_node.yaw_hint,
        )
    ]
    for edge_index, edge_pass in enumerate(edge_passes):
        to_node = node_lookup[edge_pass.to_node]
        start_xyz = sampled_node_positions[edge_index]
        end_xyz = sampled_node_positions[edge_index + 1]
        samples = _interpolate_segment(start_xyz, end_xyz, step_distance)
        for sample_index, xyz in enumerate(samples):
            is_last_sample = sample_index == len(samples) - 1
            raw_points.append(
                _build_raw_point(
                    xyz=xyz,
                    mode="graph_route",
                    node_id=edge_pass.to_node if is_last_sample else None,
                    edge_id=edge_pass.edge_id,
                    segment_index=edge_pass.segment_index,
                    pass_index=edge_pass.pass_index,
                    yaw_hint=to_node.yaw_hint if is_last_sample else None,
                )
            )
    return raw_points
__all__ = [
    "EPSILON",
    "_append_straight_samples",
    "_build_linear_route_raw_points",
    "_build_raw_point",
    "_build_sampled_node_positions",
    "_collect_node_sample_radius_overrides",
    "_interpolate_segment",
    "_left_normal",
    "_lerp_xyz",
    "_mid_yaw_deg",
    "_normalize_turn_delta_deg",
    "_normalize_xy",
    "_point_near_segment_end",
    "_point_near_segment_start",
    "_resolve_altitude_from_base_z",
    "_right_normal",
    "_sample_xy_disk_offset",
    "_signed_angle_radians",
    "_xy_distance",
    "_xyz_distance",
    "_yaw_from_points",
]
