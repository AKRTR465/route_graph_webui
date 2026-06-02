from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable

from route_graph_webui.graph.model import GraphNode, GraphSchemaError, RouteEdgePass, RoutePlan

from .sampling import (
    EPSILON,
    _append_straight_samples,
    _build_raw_point,
    _interpolate_segment,
    _left_normal,
    _lerp_xyz,
    _mid_yaw_deg,
    _normalize_turn_delta_deg,
    _normalize_xy,
    _point_near_segment_end,
    _point_near_segment_start,
    _right_normal,
    _signed_angle_radians,
    _xy_distance,
    _xyz_distance,
    _yaw_from_points,
)

@dataclass(slots=True)
class ArcCornerPrimitive:
    corner_node_id: str
    corner_yaw_hint: float | None
    incoming_edge_pass: RouteEdgePass
    outgoing_edge_pass: RouteEdgePass
    start_xyz: list[float]
    end_xyz: list[float]
    center_xy: tuple[float, float]
    radius: float
    start_angle: float
    sweep_angle: float
    turn_direction: str

    def arc_length(self) -> float:
        return abs(self.sweep_angle) * self.radius

    @property
    def turn_type(self) -> str:
        return "left_arc" if self.turn_direction == "left" else "right_arc"


@dataclass(slots=True)
class PivotUTurnPrimitive:
    corner_node_id: str
    corner_yaw_hint: float | None
    incoming_edge_pass: RouteEdgePass
    outgoing_edge_pass: RouteEdgePass
    entry_xyz: list[float]
    pivot_xyz: list[float]
    exit_xyz: list[float]
    incoming_yaw: float
    outgoing_yaw: float
    yaw_delta_deg: float
    fallback_to_in_place: bool


@dataclass(slots=True)
class SmallTurnYawPrimitive:
    corner_node_id: str
    incoming_edge_pass: RouteEdgePass
    outgoing_edge_pass: RouteEdgePass
    entry_xyz: list[float]
    corner_xyz: list[float]
    exit_xyz: list[float]
    incoming_yaw: float
    corner_yaw: float
    outgoing_yaw: float

def _sample_arc_corner_primitive(
    primitive: ArcCornerPrimitive,
    *,
    step_distance: float,
    corner_max_yaw_step_deg: float,
) -> list[dict[str, Any]]:
    if primitive.arc_length() <= EPSILON:
        return []
    arc_step = min(step_distance, primitive.radius * math.radians(corner_max_yaw_step_deg))
    arc_step = max(arc_step, EPSILON)
    steps = max(1, int(math.ceil(primitive.arc_length() / arc_step)))
    incoming_cutoff = steps // 2
    node_sample_index = max(1, (steps + 1) // 2)
    turn_sign = 1.0 if primitive.sweep_angle >= 0.0 else -1.0
    start_z = primitive.start_xyz[2]
    end_z = primitive.end_xyz[2]
    raw_points: list[dict[str, Any]] = []
    for step_index in range(1, steps + 1):
        ratio = step_index / steps
        angle = primitive.start_angle + (primitive.sweep_angle * ratio)
        tangent_x = -math.sin(angle) * turn_sign
        tangent_y = math.cos(angle) * turn_sign
        yaw = math.degrees(math.atan2(tangent_y, tangent_x))
        edge_pass = (
            primitive.incoming_edge_pass
            if step_index <= incoming_cutoff
            else primitive.outgoing_edge_pass
        )
        raw_points.append(
            _build_raw_point(
                xyz=[
                    primitive.center_xy[0] + (math.cos(angle) * primitive.radius),
                    primitive.center_xy[1] + (math.sin(angle) * primitive.radius),
                    start_z + ((end_z - start_z) * ratio),
                ],
                mode="graph_route",
                node_id=primitive.corner_node_id if step_index == node_sample_index else None,
                edge_id=edge_pass.edge_id,
                segment_index=edge_pass.segment_index,
                pass_index=edge_pass.pass_index,
                yaw_hint=primitive.corner_yaw_hint if step_index == node_sample_index else None,
                yaw=yaw,
                extra_info={
                    "turn_type": primitive.turn_type,
                    "turn_node_id": primitive.corner_node_id,
                },
            )
        )
    return raw_points


def _sample_pivot_u_turn_primitive(
    primitive: PivotUTurnPrimitive,
    *,
    step_distance: float,
    u_turn_pivot_yaw_step_deg: float,
) -> list[dict[str, Any]]:
    raw_points: list[dict[str, Any]] = []
    _append_straight_samples(
        raw_points,
        start_xyz=primitive.entry_xyz,
        end_xyz=primitive.pivot_xyz,
        step_distance=step_distance,
        mode="graph_route",
        edge_id=primitive.incoming_edge_pass.edge_id,
        segment_index=primitive.incoming_edge_pass.segment_index,
        pass_index=primitive.incoming_edge_pass.pass_index,
        yaw=primitive.incoming_yaw,
    )

    pivot_steps = max(1, int(math.ceil(abs(primitive.yaw_delta_deg) / u_turn_pivot_yaw_step_deg)))
    node_sample_index = max(1, (pivot_steps + 1) // 2)
    for step_index in range(1, pivot_steps + 1):
        ratio = step_index / pivot_steps
        raw_points.append(
            _build_raw_point(
                xyz=list(primitive.pivot_xyz),
                mode="graph_turn",
                node_id=primitive.corner_node_id if step_index == node_sample_index else None,
                edge_id=None,
                segment_index=None,
                pass_index=None,
                yaw_hint=primitive.corner_yaw_hint if step_index == node_sample_index else None,
                yaw=primitive.incoming_yaw + (primitive.yaw_delta_deg * ratio),
                extra_info={
                    "turn_type": "u_turn_pivot",
                    "turn_node_id": primitive.corner_node_id,
                    "incoming_pass_index": primitive.incoming_edge_pass.pass_index,
                    "outgoing_pass_index": primitive.outgoing_edge_pass.pass_index,
                },
            )
        )

    _append_straight_samples(
        raw_points,
        start_xyz=primitive.pivot_xyz,
        end_xyz=primitive.exit_xyz,
        step_distance=step_distance,
        mode="graph_route",
        edge_id=primitive.outgoing_edge_pass.edge_id,
        segment_index=primitive.outgoing_edge_pass.segment_index,
        pass_index=primitive.outgoing_edge_pass.pass_index,
        yaw=primitive.outgoing_yaw,
    )
    return raw_points


def _append_small_turn_yaw_segment(
    raw_points: list[dict[str, Any]],
    *,
    start_xyz: list[float],
    end_xyz: list[float],
    step_distance: float,
    mode: str,
    edge_id: str | None,
    segment_index: int | None,
    pass_index: int | None,
    start_yaw: float,
    end_yaw: float,
    end_node_id: str | None = None,
    end_node_yaw_hint: float | None = None,
    extra_info: dict[str, Any] | None = None,
) -> None:
    if _xyz_distance(start_xyz, end_xyz) <= EPSILON:
        return
    samples = _interpolate_segment(start_xyz, end_xyz, step_distance)
    yaw_delta = _normalize_turn_delta_deg(float(end_yaw) - float(start_yaw))
    total_samples = len(samples)
    for sample_index, xyz in enumerate(samples, start=1):
        ratio = sample_index / total_samples
        is_last_sample = sample_index == total_samples
        raw_points.append(
            _build_raw_point(
                xyz=xyz,
                mode=mode,
                node_id=end_node_id if is_last_sample else None,
                edge_id=edge_id,
                segment_index=segment_index,
                pass_index=pass_index,
                yaw_hint=end_node_yaw_hint if is_last_sample else None,
                yaw=float(start_yaw) + (yaw_delta * ratio),
                extra_info=extra_info,
            )
        )


def _sample_small_turn_yaw_primitive(
    primitive: SmallTurnYawPrimitive,
    *,
    step_distance: float,
) -> list[dict[str, Any]]:
    raw_points: list[dict[str, Any]] = []
    extra_info = {
        "turn_type": "small_turn_yaw",
        "turn_node_id": primitive.corner_node_id,
    }
    _append_small_turn_yaw_segment(
        raw_points,
        start_xyz=primitive.entry_xyz,
        end_xyz=primitive.corner_xyz,
        step_distance=step_distance,
        mode="graph_route",
        edge_id=primitive.incoming_edge_pass.edge_id,
        segment_index=primitive.incoming_edge_pass.segment_index,
        pass_index=primitive.incoming_edge_pass.pass_index,
        start_yaw=primitive.incoming_yaw,
        end_yaw=primitive.corner_yaw,
        end_node_id=primitive.corner_node_id,
        extra_info=extra_info,
    )
    _append_small_turn_yaw_segment(
        raw_points,
        start_xyz=primitive.corner_xyz,
        end_xyz=primitive.exit_xyz,
        step_distance=step_distance,
        mode="graph_route",
        edge_id=primitive.outgoing_edge_pass.edge_id,
        segment_index=primitive.outgoing_edge_pass.segment_index,
        pass_index=primitive.outgoing_edge_pass.pass_index,
        start_yaw=primitive.corner_yaw,
        end_yaw=primitive.outgoing_yaw,
        extra_info=extra_info,
    )
    return raw_points


def _build_smoothed_route_raw_points(
    *,
    plan: RoutePlan,
    edge_passes: list[RouteEdgePass],
    sampled_node_positions: list[list[float]],
    node_lookup: dict[str, GraphNode],
    step_distance: float,
    corner_radius: float,
    small_turn_yaw_blend_threshold_deg: float,
    corner_min_angle_deg: float,
    u_turn_threshold_deg: float,
    u_turn_transition_distance: float,
    corner_max_yaw_step_deg: float,
    u_turn_pivot_yaw_step_deg: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not edge_passes:
        first_node = node_lookup[plan.planned_nodes[0]]
        return (
            [
                _build_raw_point(
                    xyz=list(sampled_node_positions[0]),
                    mode="graph_route",
                    node_id=first_node.id,
                    edge_id=None,
                    segment_index=None,
                    pass_index=None,
                    yaw_hint=first_node.yaw_hint,
                )
            ],
            {
                "corner_turn_count": 0,
                "u_turn_count": 0,
                "smoothing_fallback_count": 0,
            },
        )

    edge_start_points = [list(point) for point in sampled_node_positions[:-1]]
    edge_end_points = [list(point) for point in sampled_node_positions[1:]]
    corner_primitives: dict[int, ArcCornerPrimitive | PivotUTurnPrimitive | SmallTurnYawPrimitive] = {}
    corner_turn_count = 0
    u_turn_count = 0
    smoothing_fallback_count = 0

    for node_index in range(1, len(sampled_node_positions) - 1):
        prev_xyz = sampled_node_positions[node_index - 1]
        corner_xyz = sampled_node_positions[node_index]
        next_xyz = sampled_node_positions[node_index + 1]
        incoming_edge_pass = edge_passes[node_index - 1]
        outgoing_edge_pass = edge_passes[node_index]
        corner_node_id = plan.planned_nodes[node_index]
        corner_yaw_hint = node_lookup[corner_node_id].yaw_hint

        in_len_xy = _xy_distance(prev_xyz, corner_xyz)
        out_len_xy = _xy_distance(corner_xyz, next_xyz)
        incoming_vector = _normalize_xy(
            corner_xyz[0] - prev_xyz[0],
            corner_xyz[1] - prev_xyz[1],
        )
        outgoing_vector = _normalize_xy(
            next_xyz[0] - corner_xyz[0],
            next_xyz[1] - corner_xyz[1],
        )
        if (
            in_len_xy <= EPSILON
            or out_len_xy <= EPSILON
            or incoming_vector is None
            or outgoing_vector is None
        ):
            continue

        signed_angle = _signed_angle_radians(incoming_vector, outgoing_vector)
        angle_deg = abs(math.degrees(signed_angle))
        if angle_deg < corner_min_angle_deg:
            incoming_yaw = _yaw_from_points(prev_xyz, corner_xyz)
            outgoing_yaw = _yaw_from_points(corner_xyz, next_xyz)
            if (
                small_turn_yaw_blend_threshold_deg > 0
                and angle_deg > EPSILON
                and angle_deg <= small_turn_yaw_blend_threshold_deg
                and incoming_yaw is not None
                and outgoing_yaw is not None
                and in_len_xy >= (2.0 * step_distance)
                and out_len_xy >= (2.0 * step_distance)
            ):
                transition_distance = min(
                    step_distance * 1.25,
                    0.2 * min(in_len_xy, out_len_xy),
                )
                if transition_distance > EPSILON:
                    entry_xyz = _point_near_segment_end(prev_xyz, corner_xyz, transition_distance)
                    exit_xyz = _point_near_segment_start(corner_xyz, next_xyz, transition_distance)
                    edge_end_points[node_index - 1] = list(entry_xyz)
                    edge_start_points[node_index] = list(exit_xyz)
                    corner_primitives[node_index] = SmallTurnYawPrimitive(
                        corner_node_id=corner_node_id,
                        incoming_edge_pass=incoming_edge_pass,
                        outgoing_edge_pass=outgoing_edge_pass,
                        entry_xyz=list(entry_xyz),
                        corner_xyz=list(corner_xyz),
                        exit_xyz=list(exit_xyz),
                        incoming_yaw=float(incoming_yaw),
                        corner_yaw=float(_mid_yaw_deg(incoming_yaw, outgoing_yaw)),
                        outgoing_yaw=float(outgoing_yaw),
                    )
                    continue
            continue

        if angle_deg >= u_turn_threshold_deg:
            min_turn_length = max(80.0, 1.5 * step_distance)
            fallback_to_in_place = in_len_xy < min_turn_length or out_len_xy < min_turn_length
            if fallback_to_in_place:
                entry_xyz = list(corner_xyz)
                exit_xyz = list(corner_xyz)
                smoothing_fallback_count += 1
            else:
                trim_in = min(u_turn_transition_distance, 0.35 * in_len_xy)
                trim_out = min(u_turn_transition_distance, 0.35 * out_len_xy)
                entry_xyz = _point_near_segment_end(prev_xyz, corner_xyz, trim_in)
                exit_xyz = _point_near_segment_start(corner_xyz, next_xyz, trim_out)
            edge_end_points[node_index - 1] = list(entry_xyz)
            edge_start_points[node_index] = list(exit_xyz)
            incoming_yaw = _yaw_from_points(prev_xyz, corner_xyz)
            outgoing_yaw = _yaw_from_points(corner_xyz, next_xyz)
            incoming_yaw = incoming_yaw if incoming_yaw is not None else (corner_yaw_hint or 0.0)
            outgoing_yaw = outgoing_yaw if outgoing_yaw is not None else incoming_yaw
            corner_primitives[node_index] = PivotUTurnPrimitive(
                corner_node_id=corner_node_id,
                corner_yaw_hint=corner_yaw_hint,
                incoming_edge_pass=incoming_edge_pass,
                outgoing_edge_pass=outgoing_edge_pass,
                entry_xyz=list(entry_xyz),
                pivot_xyz=list(corner_xyz),
                exit_xyz=list(exit_xyz),
                incoming_yaw=float(incoming_yaw),
                outgoing_yaw=float(outgoing_yaw),
                yaw_delta_deg=_normalize_turn_delta_deg(
                    float(outgoing_yaw) - float(incoming_yaw),
                    preferred_sign=signed_angle if abs(signed_angle) > EPSILON else 1.0,
                ),
                fallback_to_in_place=fallback_to_in_place,
            )
            u_turn_count += 1
            continue

        requested_trim = corner_radius * math.tan(abs(signed_angle) / 2.0)
        trim_cap = 0.35 * min(in_len_xy, out_len_xy)
        trim = min(requested_trim, trim_cap)
        if (
            in_len_xy < (2.0 * step_distance)
            or out_len_xy < (2.0 * step_distance)
            or trim < (0.5 * step_distance)
        ):
            smoothing_fallback_count += 1
            continue

        tangent_in = _point_near_segment_end(prev_xyz, corner_xyz, trim)
        tangent_out = _point_near_segment_start(corner_xyz, next_xyz, trim)
        radius = trim / math.tan(abs(signed_angle) / 2.0)
        if radius <= EPSILON:
            smoothing_fallback_count += 1
            continue
        normal_in = _left_normal(incoming_vector) if signed_angle > 0.0 else _right_normal(incoming_vector)
        normal_out = _left_normal(outgoing_vector) if signed_angle > 0.0 else _right_normal(outgoing_vector)
        center_xy = (
            (
                tangent_in[0] + (normal_in[0] * radius)
                + tangent_out[0] + (normal_out[0] * radius)
            ) / 2.0,
            (
                tangent_in[1] + (normal_in[1] * radius)
                + tangent_out[1] + (normal_out[1] * radius)
            ) / 2.0,
        )
        start_angle = math.atan2(tangent_in[1] - center_xy[1], tangent_in[0] - center_xy[0])
        end_angle = math.atan2(tangent_out[1] - center_xy[1], tangent_out[0] - center_xy[0])
        if signed_angle > 0.0:
            while end_angle <= start_angle:
                end_angle += math.tau
        else:
            while end_angle >= start_angle:
                end_angle -= math.tau
        edge_end_points[node_index - 1] = list(tangent_in)
        edge_start_points[node_index] = list(tangent_out)
        corner_primitives[node_index] = ArcCornerPrimitive(
            corner_node_id=corner_node_id,
            corner_yaw_hint=corner_yaw_hint,
            incoming_edge_pass=incoming_edge_pass,
            outgoing_edge_pass=outgoing_edge_pass,
            start_xyz=list(tangent_in),
            end_xyz=list(tangent_out),
            center_xy=center_xy,
            radius=float(radius),
            start_angle=start_angle,
            sweep_angle=end_angle - start_angle,
            turn_direction="left" if signed_angle > 0.0 else "right",
        )
        corner_turn_count += 1

    first_node = node_lookup[edge_passes[0].from_node]
    raw_points = [
        _build_raw_point(
            xyz=list(sampled_node_positions[0]),
            mode="graph_route",
            node_id=first_node.id,
            edge_id=None,
            segment_index=0,
            pass_index=None,
            yaw_hint=first_node.yaw_hint,
        )
    ]

    for edge_index, edge_pass in enumerate(edge_passes):
        next_corner_primitive = corner_primitives.get(edge_index + 1)
        end_node_id = edge_pass.to_node if next_corner_primitive is None else None
        end_node_yaw_hint = node_lookup[edge_pass.to_node].yaw_hint if end_node_id is not None else None
        straight_yaw = _yaw_from_points(edge_start_points[edge_index], edge_end_points[edge_index])
        _append_straight_samples(
            raw_points,
            start_xyz=edge_start_points[edge_index],
            end_xyz=edge_end_points[edge_index],
            step_distance=step_distance,
            mode="graph_route",
            edge_id=edge_pass.edge_id,
            segment_index=edge_pass.segment_index,
            pass_index=edge_pass.pass_index,
            yaw=straight_yaw,
            end_node_id=end_node_id,
            end_node_yaw_hint=end_node_yaw_hint,
        )
        if next_corner_primitive is None:
            continue
        if isinstance(next_corner_primitive, ArcCornerPrimitive):
            raw_points.extend(
                _sample_arc_corner_primitive(
                    next_corner_primitive,
                    step_distance=step_distance,
                    corner_max_yaw_step_deg=corner_max_yaw_step_deg,
                )
            )
        elif isinstance(next_corner_primitive, PivotUTurnPrimitive):
            raw_points.extend(
                _sample_pivot_u_turn_primitive(
                    next_corner_primitive,
                    step_distance=step_distance,
                    u_turn_pivot_yaw_step_deg=u_turn_pivot_yaw_step_deg,
                )
            )
        else:
            raw_points.extend(
                _sample_small_turn_yaw_primitive(
                    next_corner_primitive,
                    step_distance=step_distance,
                )
            )

    return (
        raw_points,
        {
            "corner_turn_count": corner_turn_count,
            "u_turn_count": u_turn_count,
            "smoothing_fallback_count": smoothing_fallback_count,
        },
    )


def _wrap_takeoff_landing(
    *,
    route_raw_points: list[dict[str, Any]],
    first_node: GraphNode,
    last_node: GraphNode,
    takeoff_relative_z: float | None,
    takeoff_step_distance: float,
    landing_relative_z: float | None,
    landing_step_distance: float,
) -> tuple[list[dict[str, Any]], float | None, float | None]:
    route_start_xyz = route_raw_points[0]["xyz"]
    route_end_xyz = route_raw_points[-1]["xyz"]
    takeoff_start_z: float | None = None
    landing_end_z: float | None = None
    raw_points: list[dict[str, Any]] = []

    if takeoff_relative_z is not None:
        offset = float(takeoff_relative_z)
        if offset < 0:
            raise GraphSchemaError("`takeoff_landing_relative_z` must be non-negative")
        takeoff_start_z = float(route_start_xyz[2]) - offset

        if abs(takeoff_start_z - route_start_xyz[2]) > EPSILON:
            takeoff_xyz = [route_start_xyz[0], route_start_xyz[1], takeoff_start_z]
            takeoff_samples = _interpolate_segment(
                takeoff_xyz,
                route_start_xyz,
                takeoff_step_distance,
            )
            raw_points.append(
                _build_raw_point(
                    xyz=takeoff_xyz,
                    mode="graph_takeoff",
                    node_id=first_node.id,
                    edge_id=None,
                    segment_index=None,
                    pass_index=None,
                    yaw_hint=first_node.yaw_hint,
                )
            )
            for xyz in takeoff_samples[:-1]:
                raw_points.append(
                    _build_raw_point(
                        xyz=xyz,
                        mode="graph_takeoff",
                        node_id=None,
                        edge_id=None,
                        segment_index=None,
                        pass_index=None,
                        yaw_hint=None,
                    )
                )
        raw_points.append(route_raw_points[0])
    else:
        raw_points.append(route_raw_points[0])

    raw_points.extend(route_raw_points[1:])

    if landing_relative_z is not None:
        offset = float(landing_relative_z)
        if offset < 0:
            raise GraphSchemaError("`takeoff_landing_relative_z` must be non-negative")
        landing_end_z = float(route_end_xyz[2]) - offset

    if landing_end_z is not None and abs(route_end_xyz[2] - landing_end_z) > EPSILON:
        landing_xyz = [route_end_xyz[0], route_end_xyz[1], landing_end_z]
        landing_samples = _interpolate_segment(
            route_end_xyz,
            landing_xyz,
            landing_step_distance,
        )
        for sample_index, xyz in enumerate(landing_samples):
            is_last_sample = sample_index == len(landing_samples) - 1
            raw_points.append(
                _build_raw_point(
                    xyz=xyz,
                    mode="graph_landing",
                    node_id=last_node.id if is_last_sample else None,
                    edge_id=None,
                    segment_index=None,
                    pass_index=None,
                    # Keep landing yaw continuous with the incoming route instead of
                    # snapping the final frame to the terminal node yaw hint.
                    yaw_hint=None,
                )
            )

    return raw_points, takeoff_start_z, landing_end_z


def _unwrap_angle_deg(current_deg: float, previous_deg: float) -> float:
    delta_deg = _normalize_turn_delta_deg(float(current_deg) - float(previous_deg))
    return float(previous_deg) + delta_deg


def _finalize_positions(
    raw_points: list[dict[str, Any]],
    *,
    fps: float,
    default_yaw: float,
    clock: Callable[[], float] | None = None,
) -> list[dict[str, Any]]:
    positions = []
    start_time = float(clock() if clock is not None else time.time())
    resolved_yaws: list[float] = []
    last_known_yaw = float(default_yaw)
    for index, raw_point in enumerate(raw_points):
        yaw = raw_point.get("yaw")
        if yaw is None:
            for next_point in raw_points[index + 1 :]:
                yaw = _yaw_from_points(raw_point["xyz"], next_point["xyz"])
                if yaw is not None:
                    break
                next_yaw = next_point.get("yaw")
                if next_yaw is not None:
                    yaw = next_yaw
                    break
        if yaw is None:
            yaw = raw_point["yaw_hint"] if raw_point["yaw_hint"] is not None else last_known_yaw
        yaw = _unwrap_angle_deg(float(yaw), last_known_yaw)
        resolved_yaws.append(float(yaw))
        last_known_yaw = float(yaw)

    for index, (raw_point, yaw) in enumerate(zip(raw_points, resolved_yaws, strict=True)):
        info = {
            "mode": raw_point["mode"],
            "node_id": raw_point["node_id"],
            "edge_id": raw_point["edge_id"],
            "segment_index": raw_point["segment_index"],
            "pass_index": raw_point["pass_index"],
        }
        info.update(raw_point.get("extra_info") or {})

        positions.append(
            {
                "state": [
                    [round(float(value), 6) for value in raw_point["xyz"]],
                    [0.0, round(float(yaw), 6), 0.0],
                ],
                "time": start_time + (index / float(fps)),
                "frame": index,
                "image_path": f"{index:06d}.png",
                "info": info,
            }
        )
    return positions
__all__ = [
    "ArcCornerPrimitive",
    "PivotUTurnPrimitive",
    "SmallTurnYawPrimitive",
    "_append_small_turn_yaw_segment",
    "_build_smoothed_route_raw_points",
    "_finalize_positions",
    "_sample_arc_corner_primitive",
    "_sample_pivot_u_turn_primitive",
    "_sample_small_turn_yaw_primitive",
    "_unwrap_angle_deg",
    "_wrap_takeoff_landing",
]
