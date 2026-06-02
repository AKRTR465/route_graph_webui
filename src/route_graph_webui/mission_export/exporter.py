from __future__ import annotations

import argparse
import random
import re
import time
from pathlib import Path
from typing import Any, Callable

from route_graph_webui.shared.cli_args import (
    add_graph_argument,
    add_mission_turn_smoothing_arguments,
    add_output_argument,
)
from route_graph_webui.graph.conversion import candidate_to_plan, resolve_plan_edge_passes
from route_graph_webui.graph.grouping import build_uniform_z_node_lookup
from route_graph_webui.graph.io import load_candidate_set, load_graph, load_plan
from route_graph_webui.graph.meta import NODE_Z_PREPROCESS_MODE
from route_graph_webui.graph.model import GraphSchemaError, RouteCandidateSet, RoutePlan
from route_graph_webui.graph.validation import ensure_valid_plan
from route_graph_webui.mission.io import write_mission_json
from route_graph_webui.planning.route_planner import RoutePlanningError, plan_route
from route_graph_webui.shared.time_utils import timestamp_now

from .config import (
    DEFAULT_CORNER_MAX_YAW_STEP_DEG,
    DEFAULT_CORNER_MIN_ANGLE_DEG,
    DEFAULT_CORNER_RADIUS,
    DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
    DEFAULT_TURN_SMOOTHING_ENABLED,
    DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    DEFAULT_U_TURN_THRESHOLD_DEG,
    DEFAULT_U_TURN_TRANSITION_DISTANCE,
    MissionExportOptions,
    _validate_turn_smoothing_parameters,
)
from .group_context import _resolve_graph_default_altitude, _resolve_plan_grouped_export_context
from .sampling import _build_linear_route_raw_points, _build_sampled_node_positions
from .smoothing import _build_smoothed_route_raw_points, _finalize_positions, _wrap_takeoff_landing

def _timestamp_from_clock(clock: Callable[[], float] | None) -> str:
    if clock is None:
        return timestamp_now()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(float(clock())))

def build_mission_from_plan(
    plan: RoutePlan,
    *,
    step_distance: float = 60.0,
    fps: float = 4.0,
    altitude_mode: str = "fixed",
    fixed_z: float | None = None,
    altitude_offset: float = 0.0,
    takeoff_landing_relative_z: float | None = None,
    takeoff_landing_step_distance: float | None = None,
    node_sample_radius: float = 0.0,
    random_seed: int | None = None,
    turn_smoothing_enabled: bool = DEFAULT_TURN_SMOOTHING_ENABLED,
    corner_radius: float = DEFAULT_CORNER_RADIUS,
    small_turn_yaw_blend_threshold_deg: float = DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
    corner_min_angle_deg: float = DEFAULT_CORNER_MIN_ANGLE_DEG,
    u_turn_threshold_deg: float = DEFAULT_U_TURN_THRESHOLD_DEG,
    u_turn_transition_distance: float = DEFAULT_U_TURN_TRANSITION_DISTANCE,
    corner_max_yaw_step_deg: float = DEFAULT_CORNER_MAX_YAW_STEP_DEG,
    u_turn_pivot_yaw_step_deg: float = DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    if step_distance <= 0:
        raise GraphSchemaError("`step_distance` must be positive")
    if fps <= 0:
        raise GraphSchemaError("`fps` must be positive")
    if node_sample_radius < 0:
        raise GraphSchemaError("`node_sample_radius` must be non-negative")
    if takeoff_landing_relative_z is not None and float(takeoff_landing_relative_z) < 0:
        raise GraphSchemaError("`takeoff_landing_relative_z` must be non-negative")
    if takeoff_landing_step_distance is not None and float(takeoff_landing_step_distance) <= 0:
        raise GraphSchemaError("`takeoff_landing_step_distance` must be positive when provided")
    if turn_smoothing_enabled:
        _validate_turn_smoothing_parameters(
            corner_radius=corner_radius,
            corner_min_angle_deg=corner_min_angle_deg,
            u_turn_threshold_deg=u_turn_threshold_deg,
            u_turn_transition_distance=u_turn_transition_distance,
            corner_max_yaw_step_deg=corner_max_yaw_step_deg,
            u_turn_pivot_yaw_step_deg=u_turn_pivot_yaw_step_deg,
        )
    ensure_valid_plan(plan)

    graph_default_altitude = _resolve_graph_default_altitude(plan)
    node_lookup, uniform_node_z = build_uniform_z_node_lookup(plan.node_lookup)
    first_node = node_lookup[plan.planned_nodes[0]]
    last_node = node_lookup[plan.planned_nodes[-1]]
    edge_passes = resolve_plan_edge_passes(plan)
    group_fallback_fixed_z = fixed_z
    resolved_global_fixed_z = fixed_z
    if resolved_global_fixed_z is None and altitude_mode == "fixed":
        resolved_global_fixed_z = (
            graph_default_altitude if graph_default_altitude is not None else first_node.position[2]
        )
    (
        node_settings_lookup,
        node_group_lookup,
        original_node_z_lookup,
        group_settings_lookup,
    ) = _resolve_plan_grouped_export_context(
        plan,
        fallback_altitude_mode=altitude_mode,
        fallback_fixed_z=group_fallback_fixed_z,
        fallback_altitude_offset=altitude_offset,
        fallback_node_sample_radius=float(node_sample_radius),
        fallback_takeoff_landing_relative_z=takeoff_landing_relative_z,
        fallback_takeoff_landing_step_distance=takeoff_landing_step_distance,
    )
    start_settings = node_settings_lookup.get(first_node.id)
    end_settings = node_settings_lookup.get(last_node.id)
    resolved_takeoff_relative_z = (
        takeoff_landing_relative_z
        if start_settings is None
        else start_settings.takeoff_landing_relative_z
    )
    resolved_landing_relative_z = (
        takeoff_landing_relative_z
        if end_settings is None
        else end_settings.takeoff_landing_relative_z
    )
    resolved_takeoff_step_distance = float(
        step_distance
        if (
            (takeoff_landing_step_distance if start_settings is None else start_settings.takeoff_landing_step_distance)
            is None
        )
        else (
            takeoff_landing_step_distance
            if start_settings is None
            else start_settings.takeoff_landing_step_distance
        )
    )
    resolved_landing_step_distance = float(
        step_distance
        if (
            (takeoff_landing_step_distance if end_settings is None else end_settings.takeoff_landing_step_distance)
            is None
        )
        else (
            takeoff_landing_step_distance
            if end_settings is None
            else end_settings.takeoff_landing_step_distance
        )
    )
    rng = random.Random(random_seed)
    sampled_node_positions, node_sample_radius_overrides, any_disk_sampling = _build_sampled_node_positions(
        plan,
        node_lookup,
        altitude_mode=altitude_mode,
        fixed_z=resolved_global_fixed_z,
        altitude_offset=altitude_offset,
        node_sample_radius=float(node_sample_radius),
        rng=rng,
        node_settings_lookup=node_settings_lookup or None,
        original_node_z_lookup=original_node_z_lookup or None,
    )
    node_sampling_mode = "xy_disk_per_occurrence" if any_disk_sampling else "point_center"

    if turn_smoothing_enabled:
        route_raw_points, smoothing_stats = _build_smoothed_route_raw_points(
            plan=plan,
            edge_passes=edge_passes,
            sampled_node_positions=sampled_node_positions,
            node_lookup=node_lookup,
            step_distance=step_distance,
            corner_radius=corner_radius,
            small_turn_yaw_blend_threshold_deg=float(small_turn_yaw_blend_threshold_deg),
            corner_min_angle_deg=corner_min_angle_deg,
            u_turn_threshold_deg=u_turn_threshold_deg,
            u_turn_transition_distance=u_turn_transition_distance,
            corner_max_yaw_step_deg=corner_max_yaw_step_deg,
            u_turn_pivot_yaw_step_deg=u_turn_pivot_yaw_step_deg,
        )
    else:
        route_raw_points = _build_linear_route_raw_points(
            planned_nodes=plan.planned_nodes,
            edge_passes=edge_passes,
            sampled_node_positions=sampled_node_positions,
            node_lookup=node_lookup,
            step_distance=step_distance,
        )
        smoothing_stats = {
            "corner_turn_count": 0,
            "u_turn_count": 0,
            "smoothing_fallback_count": 0,
        }

    raw_points, takeoff_start_z, landing_end_z = _wrap_takeoff_landing(
        route_raw_points=route_raw_points,
        first_node=first_node,
        last_node=last_node,
        takeoff_relative_z=resolved_takeoff_relative_z,
        takeoff_step_distance=resolved_takeoff_step_distance,
        landing_relative_z=resolved_landing_relative_z,
        landing_step_distance=resolved_landing_step_distance,
    )
    positions = _finalize_positions(
        raw_points,
        fps=fps,
        default_yaw=first_node.yaw_hint or 0.0,
        clock=clock,
    )
    if resolved_takeoff_relative_z is None and resolved_landing_relative_z is None:
        takeoff_landing_relative_z_meta: float | dict[str, float | None] | None = None
        takeoff_landing_step_distance_meta: float | dict[str, float] | None = None
    elif resolved_takeoff_relative_z == resolved_landing_relative_z:
        takeoff_landing_relative_z_meta = (
            None if resolved_takeoff_relative_z is None else float(resolved_takeoff_relative_z)
        )
        takeoff_landing_step_distance_meta = float(
            resolved_takeoff_step_distance
            if resolved_takeoff_relative_z is not None
            else resolved_landing_step_distance
        )
    else:
        takeoff_landing_relative_z_meta = {
            "takeoff": None
            if resolved_takeoff_relative_z is None
            else float(resolved_takeoff_relative_z),
            "landing": None
            if resolved_landing_relative_z is None
            else float(resolved_landing_relative_z),
        }
        takeoff_landing_step_distance_meta = {
            "takeoff": float(resolved_takeoff_step_distance),
            "landing": float(resolved_landing_step_distance),
        }

    return {
        "positions": positions,
        "keyframes": [],
        "env_id": plan.env_id,
        "route_meta": {
            "graph_name": plan.graph_name,
            "anchor_nodes": list(plan.anchor_nodes),
            "planned_nodes": list(plan.planned_nodes),
            "segment_count": len(plan.segments),
            "total_length": round(float(plan.total_length), 6),
            "edge_pass_count": len(edge_passes),
            "step_distance": float(step_distance),
            "fps": float(fps),
            "altitude_mode": altitude_mode,
            "fixed_z": None if resolved_global_fixed_z is None else float(resolved_global_fixed_z),
            "altitude_offset": float(altitude_offset),
            "node_z_preprocess_mode": NODE_Z_PREPROCESS_MODE,
            "uniform_node_z": round(float(uniform_node_z), 6),
            "takeoff_landing_relative_z": takeoff_landing_relative_z_meta,
            "takeoff_landing_step_distance": takeoff_landing_step_distance_meta,
            "takeoff_landing_enabled": bool(
                resolved_takeoff_relative_z is not None or resolved_landing_relative_z is not None
            ),
            "takeoff_start_z": None if takeoff_start_z is None else round(float(takeoff_start_z), 6),
            "landing_end_z": None if landing_end_z is None else round(float(landing_end_z), 6),
            "node_sample_radius": float(node_sample_radius),
            "node_sample_radius_overrides": {
                node_id: round(float(radius), 6)
                for node_id, radius in sorted(node_sample_radius_overrides.items())
            },
            "random_seed": None if random_seed is None else int(random_seed),
            "node_sampling_mode": node_sampling_mode,
            "turn_smoothing_enabled": bool(turn_smoothing_enabled),
            "corner_radius": float(corner_radius),
            "small_turn_yaw_blend_threshold_deg": float(small_turn_yaw_blend_threshold_deg),
            "corner_min_angle_deg": float(corner_min_angle_deg),
            "u_turn_threshold_deg": float(u_turn_threshold_deg),
            "u_turn_transition_distance": float(u_turn_transition_distance),
            "corner_max_yaw_step_deg": float(corner_max_yaw_step_deg),
            "u_turn_pivot_yaw_step_deg": float(u_turn_pivot_yaw_step_deg),
            "corner_turn_count": int(smoothing_stats["corner_turn_count"]),
            "u_turn_count": int(smoothing_stats["u_turn_count"]),
            "smoothing_fallback_count": int(smoothing_stats["smoothing_fallback_count"]),
            "candidate_id": plan.meta.get("candidate_id"),
            "candidate_rank": plan.meta.get("candidate_rank"),
            "selected": bool(plan.meta.get("selected", False)),
            "candidate_set_meta": {
                key: value
                for key, value in dict(plan.meta).items()
                if key not in {"candidate_id", "candidate_rank", "selected", "candidate_meta"}
            },
            "candidate_meta": dict(plan.meta.get("candidate_meta") or {}),
            "node_group_lookup_v1": dict(sorted(node_group_lookup.items())),
            "group_configs_v1": {
                color: {
                    "altitude_mode": settings.altitude_mode,
                    "fixed_z": None if settings.fixed_z is None else float(settings.fixed_z),
                    "altitude_offset": float(settings.altitude_offset),
                    "node_sample_radius": float(settings.node_sample_radius),
                    "takeoff_landing_relative_z": None
                    if settings.takeoff_landing_relative_z is None
                    else float(settings.takeoff_landing_relative_z),
                    "takeoff_landing_step_distance": None
                    if settings.takeoff_landing_step_distance is None
                    else float(settings.takeoff_landing_step_distance),
                }
                for color, settings in sorted(group_settings_lookup.items())
            },
            "generated_at": _timestamp_from_clock(clock),
        },
    }


def export_mission(
    plan: RoutePlan,
    output_path: str | Path | None = None,
    *,
    step_distance: float = 60.0,
    fps: float = 4.0,
    altitude_mode: str = "fixed",
    fixed_z: float | None = None,
    altitude_offset: float = 0.0,
    takeoff_landing_relative_z: float | None = None,
    takeoff_landing_step_distance: float | None = None,
    node_sample_radius: float = 0.0,
    random_seed: int | None = None,
    turn_smoothing_enabled: bool = DEFAULT_TURN_SMOOTHING_ENABLED,
    corner_radius: float = DEFAULT_CORNER_RADIUS,
    small_turn_yaw_blend_threshold_deg: float = DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
    corner_min_angle_deg: float = DEFAULT_CORNER_MIN_ANGLE_DEG,
    u_turn_threshold_deg: float = DEFAULT_U_TURN_THRESHOLD_DEG,
    u_turn_transition_distance: float = DEFAULT_U_TURN_TRANSITION_DISTANCE,
    corner_max_yaw_step_deg: float = DEFAULT_CORNER_MAX_YAW_STEP_DEG,
    u_turn_pivot_yaw_step_deg: float = DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    mission = build_mission_from_plan(
        plan,
        step_distance=step_distance,
        fps=fps,
        altitude_mode=altitude_mode,
        fixed_z=fixed_z,
        altitude_offset=altitude_offset,
        takeoff_landing_relative_z=takeoff_landing_relative_z,
        takeoff_landing_step_distance=takeoff_landing_step_distance,
        node_sample_radius=node_sample_radius,
        random_seed=random_seed,
        turn_smoothing_enabled=turn_smoothing_enabled,
        corner_radius=corner_radius,
        small_turn_yaw_blend_threshold_deg=small_turn_yaw_blend_threshold_deg,
        corner_min_angle_deg=corner_min_angle_deg,
        u_turn_threshold_deg=u_turn_threshold_deg,
        u_turn_transition_distance=u_turn_transition_distance,
        corner_max_yaw_step_deg=corner_max_yaw_step_deg,
        u_turn_pivot_yaw_step_deg=u_turn_pivot_yaw_step_deg,
        clock=clock,
    )
    if output_path is not None:
        write_mission_json(Path(output_path).resolve(), mission)
    return mission


def _resolve_batch_candidate_ids(
    candidate_set: RouteCandidateSet,
    *,
    candidate_ids: list[str] | None = None,
    selected_only: bool = False,
) -> list[str]:
    if candidate_ids:
        resolved_ids = [str(candidate_id) for candidate_id in candidate_ids]
    else:
        candidate_set.sync_selected_ids()
        resolved_ids = list(candidate_set.selected_candidate_ids)

    if not resolved_ids:
        raise GraphSchemaError(
            "RouteCandidateSet has no selected candidates; keep candidates in the GUI or pass `--candidate-ids`"
        )

    known_ids = {candidate.candidate_id for candidate in candidate_set.candidates}
    unknown_ids = [candidate_id for candidate_id in resolved_ids if candidate_id not in known_ids]
    if unknown_ids:
        raise GraphSchemaError(
            f"Unknown route candidate id(s): {', '.join(sorted(unknown_ids))}"
        )

    if selected_only and candidate_ids:
        raise GraphSchemaError("`selected_only` and explicit `candidate_ids` cannot be used together")

    return resolved_ids


def _resolve_incremental_mission_output_path(
    output_dir: Path,
    graph_name: str,
    candidate_id: str,
    used_indices: set[int] | None = None,
) -> Path:
    if used_indices is None:
        used_indices = set()

    pattern = re.compile(rf"^{re.escape(graph_name)}_C(\d{{3}})(?:_\d+)?\.json$")
    used_in_dir: set[int] = set()
    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if match:
            used_in_dir.add(int(match.group(1)))

    preferred_index_match = re.fullmatch(r"C(\d{3})", str(candidate_id))
    if preferred_index_match is not None:
        next_index = int(preferred_index_match.group(1))
    else:
        next_index = 1

    while next_index in used_in_dir or next_index in used_indices:
        next_index += 1

    used_indices.add(next_index)
    return output_dir / f"{graph_name}_C{next_index:03d}.json"


def export_candidate_set_missions(
    candidate_set: RouteCandidateSet,
    output_dir: str | Path,
    *,
    candidate_ids: list[str] | None = None,
    selected_only: bool = False,
    step_distance: float = 60.0,
    fps: float = 4.0,
    altitude_mode: str = "fixed",
    fixed_z: float | None = None,
    altitude_offset: float = 0.0,
    takeoff_landing_relative_z: float | None = None,
    takeoff_landing_step_distance: float | None = None,
    node_sample_radius: float = 0.0,
    random_seed: int | None = None,
    turn_smoothing_enabled: bool = DEFAULT_TURN_SMOOTHING_ENABLED,
    corner_radius: float = DEFAULT_CORNER_RADIUS,
    small_turn_yaw_blend_threshold_deg: float = DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
    corner_min_angle_deg: float = DEFAULT_CORNER_MIN_ANGLE_DEG,
    u_turn_threshold_deg: float = DEFAULT_U_TURN_THRESHOLD_DEG,
    u_turn_transition_distance: float = DEFAULT_U_TURN_TRANSITION_DISTANCE,
    corner_max_yaw_step_deg: float = DEFAULT_CORNER_MAX_YAW_STEP_DEG,
    u_turn_pivot_yaw_step_deg: float = DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    resolved_dir = Path(output_dir).resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    requested_candidate_ids = _resolve_batch_candidate_ids(
        candidate_set,
        candidate_ids=candidate_ids,
        selected_only=selected_only,
    )

    written_files: dict[str, str] = {}
    errors: dict[str, str] = {}
    succeeded: list[str] = []
    failed: list[str] = []
    used_indices: set[int] = set()

    for candidate_id in requested_candidate_ids:
        try:
            plan = candidate_to_plan(candidate_set, candidate_id)
            output_path = _resolve_incremental_mission_output_path(
                resolved_dir,
                candidate_set.graph_name,
                candidate_id,
                used_indices,
            )
            export_mission(
                plan,
                output_path=output_path,
                step_distance=step_distance,
                fps=fps,
                altitude_mode=altitude_mode,
                fixed_z=fixed_z,
                altitude_offset=altitude_offset,
                takeoff_landing_relative_z=takeoff_landing_relative_z,
                takeoff_landing_step_distance=takeoff_landing_step_distance,
                node_sample_radius=node_sample_radius,
                random_seed=random_seed,
                turn_smoothing_enabled=turn_smoothing_enabled,
                corner_radius=corner_radius,
                small_turn_yaw_blend_threshold_deg=small_turn_yaw_blend_threshold_deg,
                corner_min_angle_deg=corner_min_angle_deg,
                u_turn_threshold_deg=u_turn_threshold_deg,
                u_turn_transition_distance=u_turn_transition_distance,
                corner_max_yaw_step_deg=corner_max_yaw_step_deg,
                u_turn_pivot_yaw_step_deg=u_turn_pivot_yaw_step_deg,
                clock=clock,
            )
        except (GraphSchemaError, RoutePlanningError) as exc:
            failed.append(candidate_id)
            errors[candidate_id] = str(exc)
            continue

        succeeded.append(candidate_id)
        written_files[candidate_id] = str(output_path)

    return {
        "output_dir": str(resolved_dir),
        "requested_candidate_ids": list(requested_candidate_ids),
        "succeeded": succeeded,
        "failed": failed,
        "written_files": written_files,
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export route_graph_webui plans or candidate sets into replay-compatible mission JSON."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", help="Path to route plan JSON")
    source.add_argument("--candidate-set", help="Path to route candidate-set JSON")
    add_graph_argument(
        source,
        required=False,
        help="Path to graph JSON, exporting the shortest route directly",
    )
    parser.add_argument("--candidate-id", help="Candidate id when exporting from a candidate set")
    parser.add_argument("--start", help="Start node id when exporting directly from graph")
    parser.add_argument("--via", nargs="*", default=[], help="Via node ids when exporting directly from graph")
    parser.add_argument("--end", help="End node id when exporting directly from graph")
    add_output_argument(parser, help="Output mission JSON path for single-candidate export")
    parser.add_argument("--output-dir", help="Output directory for batch candidate export")
    parser.add_argument("--step-distance", type=float, default=60.0)
    parser.add_argument("--fps", type=float, default=4.0)
    parser.add_argument("--altitude-mode", choices=["fixed", "follow_nodes"], default="fixed")
    parser.add_argument("--fixed-z", type=float, default=None)
    parser.add_argument("--altitude-offset", type=float, default=0.0)
    parser.add_argument(
        "--takeoff-landing-relative-z",
        type=float,
        default=None,
        help="Optional non-negative vertical offset below the route altitude for takeoff/landing",
    )
    parser.add_argument(
        "--takeoff-landing-step-distance",
        type=float,
        default=None,
        help="Optional positive interpolation step for takeoff/landing segments; defaults to --step-distance",
    )
    parser.add_argument("--node-sample-radius", type=float, default=0.0)
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument(
        "--selected-only",
        action="store_true",
        help="Batch export only the candidate ids listed in selected_candidate_ids (default batch behavior)",
    )
    parser.add_argument(
        "--candidate-ids",
        nargs="*",
        default=None,
        help="Explicit candidate ids for batch export; overrides selected_candidate_ids",
    )
    add_mission_turn_smoothing_arguments(
        parser,
        default_turn_smoothing_enabled=DEFAULT_TURN_SMOOTHING_ENABLED,
        default_corner_radius=DEFAULT_CORNER_RADIUS,
        default_small_turn_yaw_blend_threshold_deg=DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
        default_corner_min_angle_deg=DEFAULT_CORNER_MIN_ANGLE_DEG,
        default_u_turn_threshold_deg=DEFAULT_U_TURN_THRESHOLD_DEG,
        default_u_turn_transition_distance=DEFAULT_U_TURN_TRANSITION_DISTANCE,
        default_corner_max_yaw_step_deg=DEFAULT_CORNER_MAX_YAW_STEP_DEG,
        default_u_turn_pivot_yaw_step_deg=DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if bool(args.output) == bool(args.output_dir):
            raise GraphSchemaError("Specify exactly one of `--output` or `--output-dir`")
        if args.output_dir and args.plan:
            raise GraphSchemaError("`--output-dir` is only supported with `--candidate-set`")
        if args.output_dir and args.graph:
            raise GraphSchemaError("`--output-dir` is only supported with `--candidate-set`")
        if args.output and (args.selected_only or args.candidate_ids):
            raise GraphSchemaError("`--selected-only` / `--candidate-ids` are only valid with `--output-dir`")
        if args.output_dir and args.candidate_id:
            raise GraphSchemaError("`--candidate-id` is only valid for single-candidate export")
        if args.selected_only and args.candidate_ids:
            raise GraphSchemaError("`--selected-only` cannot be combined with `--candidate-ids`")
        export_options = MissionExportOptions.from_mapping(
            {
                "step_distance": args.step_distance,
                "fps": args.fps,
                "altitude_mode": args.altitude_mode,
                "fixed_z": args.fixed_z,
                "altitude_offset": args.altitude_offset,
                "takeoff_landing_relative_z": args.takeoff_landing_relative_z,
                "takeoff_landing_step_distance": args.takeoff_landing_step_distance,
                "node_sample_radius": args.node_sample_radius,
                "random_seed": args.random_seed,
                "turn_smoothing_enabled": args.turn_smoothing_enabled,
                "corner_radius": args.corner_radius,
                "small_turn_yaw_blend_threshold_deg": args.small_turn_yaw_blend_threshold_deg,
                "corner_min_angle_deg": args.corner_min_angle_deg,
                "u_turn_threshold_deg": args.u_turn_threshold_deg,
                "u_turn_transition_distance": args.u_turn_transition_distance,
                "corner_max_yaw_step_deg": args.corner_max_yaw_step_deg,
                "u_turn_pivot_yaw_step_deg": args.u_turn_pivot_yaw_step_deg,
            }
        )

        if args.plan:
            plan = load_plan(args.plan)
        elif args.candidate_set and args.output:
            candidate_set = load_candidate_set(args.candidate_set)
            if not args.candidate_id:
                raise GraphSchemaError(
                    "`--candidate-id` is required when exporting from `--candidate-set`"
                )
            plan = candidate_to_plan(candidate_set, args.candidate_id)
        elif args.graph:
            if not args.start or not args.end:
                raise GraphSchemaError("`--start` and `--end` are required when exporting from `--graph`")
            graph = load_graph(args.graph)
            plan = plan_route(graph, start=args.start, via=args.via, end=args.end)
        else:
            candidate_set = load_candidate_set(args.candidate_set)

        if args.output:
            mission = export_mission(
                plan,
                output_path=args.output,
                **export_options.to_mission_kwargs(),
            )
        else:
            summary = export_candidate_set_missions(
                candidate_set,
                args.output_dir,
                candidate_ids=args.candidate_ids,
                selected_only=args.selected_only,
                **export_options.to_mission_kwargs(),
            )
    except (GraphSchemaError, RoutePlanningError) as exc:
        print(exc)
        return 1

    if args.output:
        print(f"Saved mission JSON to {Path(args.output).resolve()}")
        print(f"Frames: {len(mission['positions'])}")
        print(f"Environment: {mission['env_id']}")
        return 0

    print(f"Saved {len(summary['succeeded'])} mission JSON file(s) to {summary['output_dir']}")
    print(f"Requested candidates: {', '.join(summary['requested_candidate_ids'])}")
    if summary["succeeded"]:
        print(f"Succeeded: {', '.join(summary['succeeded'])}")
    if summary["failed"]:
        print(f"Failed: {', '.join(summary['failed'])}")
        for candidate_id in summary["failed"]:
            print(f"  {candidate_id}: {summary['errors'][candidate_id]}")
        return 1
    return 0
__all__ = [
    "build_mission_from_plan",
    "build_parser",
    "export_candidate_set_missions",
    "export_mission",
    "main",
    "_resolve_batch_candidate_ids",
    "_resolve_incremental_mission_output_path",
    "_timestamp_from_clock",
]
