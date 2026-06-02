from __future__ import annotations

import argparse
import bisect
import copy
import json
import math
from pathlib import Path
from typing import Any

from geometry import distance_3d, normalize_angle_deg


DEFAULT_FILE_GLOB = "*.json"
EPSILON = 1e-9

ROUTE_STRAIGHT = "straight"
ROUTE_TURN = "turn"
ROUTE_TAKEOFF_LANDING = "takeoff_landing"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classified distance-based resampling for mission JSON positions "
            "(straight / turn / takeoff-landing)."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Input JSON directory containing mission files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Default: <input-dir>_resampled_distance_classified.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite input files in place.",
    )
    parser.add_argument(
        "--glob",
        type=str,
        default=DEFAULT_FILE_GLOB,
        help=f"File match pattern, default {DEFAULT_FILE_GLOB}",
    )
    parser.add_argument(
        "--straight-step-distance",
        type=float,
        default=None,
        help="Straight-step distance. Default: route_meta.step_distance.",
    )
    parser.add_argument(
        "--turn-step-distance",
        type=float,
        default=None,
        help="Turn-step distance. Default: straight-step distance.",
    )
    parser.add_argument(
        "--takeoff-landing-step-distance",
        type=float,
        default=None,
        help="Takeoff/Landing-step distance. Default: straight-step distance.",
    )
    parser.add_argument(
        "--turn-angle-threshold-deg",
        type=float,
        default=15.0,
        help="Angle threshold for geometric turn fallback when turn_type is missing.",
    )
    return parser.parse_args()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _validate_positive(name: str, value: float) -> float:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return float(value)


def _validate_turn_angle_threshold_deg(value: float) -> float:
    if not math.isfinite(float(value)) or float(value) <= 0.0 or float(value) > 180.0:
        raise ValueError("turn_angle_threshold_deg must be in (0, 180]")
    return float(value)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _distance_3d(a: list[float], b: list[float]) -> float:
    return distance_3d(a, b)


def _vector_3d(a: list[float], b: list[float]) -> tuple[float, float, float]:
    return float(b[0]) - float(a[0]), float(b[1]) - float(a[1]), float(b[2]) - float(a[2])


def _vector_norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)


def _angle_between_deg(v1: tuple[float, float, float], v2: tuple[float, float, float]) -> float | None:
    n1 = _vector_norm(v1)
    n2 = _vector_norm(v2)
    if n1 <= EPSILON or n2 <= EPSILON:
        return None
    cosine = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _normalize_angle_deg(angle: float) -> float:
    return normalize_angle_deg(angle)


def _lerp_angle_deg(a: float, b: float, t: float) -> float:
    delta = ((b - a + 180.0) % 360.0) - 180.0
    return _normalize_angle_deg(a + delta * t)


def _extract_state(point: dict[str, Any]) -> tuple[list[float], list[float]]:
    state = point.get("state")
    if (
        not isinstance(state, list)
        or len(state) != 2
        or not isinstance(state[0], list)
        or not isinstance(state[1], list)
        or len(state[0]) != 3
        or len(state[1]) != 3
    ):
        raise ValueError("positions[*].state must be [[x, y, z], [roll, yaw, pitch]]")
    xyz = [float(value) for value in state[0]]
    ryp = [float(value) for value in state[1]]
    return xyz, ryp


def _extract_xyz(point: dict[str, Any]) -> list[float]:
    xyz, _ = _extract_state(point)
    return xyz


def _extract_info(point: dict[str, Any]) -> dict[str, Any]:
    info = point.get("info")
    if isinstance(info, dict):
        return info
    return {}


def _extract_mode(point: dict[str, Any]) -> str | None:
    mode = _extract_info(point).get("mode")
    if isinstance(mode, str):
        return mode
    return None


def _has_semantic_node_anchor(point: dict[str, Any]) -> bool:
    node_id = _extract_info(point).get("node_id")
    if node_id is None:
        return False
    if isinstance(node_id, str):
        return bool(node_id.strip())
    return True


def _infer_image_name_template(positions: list[dict[str, Any]]) -> tuple[int, str]:
    for point in positions:
        image_path = point.get("image_path")
        if not isinstance(image_path, str) or "." not in image_path:
            continue
        stem, suffix = image_path.rsplit(".", 1)
        if stem.isdigit():
            return max(1, len(stem)), f".{suffix}"
    return 6, ".png"


def _build_interpolated_point(
    left_point: dict[str, Any],
    right_point: dict[str, Any],
    t: float,
) -> dict[str, Any]:
    left_xyz, left_ryp = _extract_state(left_point)
    right_xyz, right_ryp = _extract_state(right_point)

    interpolated = copy.deepcopy(left_point)
    interpolated["state"] = [
        [round(_lerp(left_xyz[i], right_xyz[i], t), 6) for i in range(3)],
        [round(_lerp_angle_deg(left_ryp[i], right_ryp[i], t), 6) for i in range(3)],
    ]

    left_time = left_point.get("time")
    right_time = right_point.get("time")
    if _is_number(left_time) and _is_number(right_time):
        interpolated["time"] = _lerp(float(left_time), float(right_time), t)
    elif _is_number(left_time):
        interpolated["time"] = float(left_time)
    elif _is_number(right_time):
        interpolated["time"] = float(right_time)

    if EPSILON < t < (1.0 - EPSILON):
        info = interpolated.get("info")
        if isinstance(info, dict) and info.get("node_id") is not None:
            info_copy = dict(info)
            info_copy["node_id"] = None
            interpolated["info"] = info_copy

    return interpolated


def _resolve_step_distances(
    route_meta: dict[str, Any] | None,
    *,
    straight_step_distance: float | None,
    turn_step_distance: float | None,
    takeoff_landing_step_distance: float | None,
) -> dict[str, float]:
    route_meta_dict = route_meta if isinstance(route_meta, dict) else {}

    straight_step = straight_step_distance
    if straight_step is None:
        inherited = route_meta_dict.get("step_distance")
        if not _is_number(inherited) or float(inherited) <= 0.0:
            raise ValueError(
                "`route_meta.step_distance` is missing/invalid; pass --straight-step-distance explicitly"
            )
        straight_step = float(inherited)
    straight_step = _validate_positive("straight_step_distance", straight_step)

    turn_step = turn_step_distance if turn_step_distance is not None else straight_step
    turn_step = _validate_positive("turn_step_distance", float(turn_step))

    takeoff_landing_step = (
        takeoff_landing_step_distance
        if takeoff_landing_step_distance is not None
        else straight_step
    )
    takeoff_landing_step = _validate_positive(
        "takeoff_landing_step_distance",
        float(takeoff_landing_step),
    )

    return {
        ROUTE_STRAIGHT: straight_step,
        ROUTE_TURN: turn_step,
        ROUTE_TAKEOFF_LANDING: takeoff_landing_step,
    }


def _build_route_neighbors(positions: list[dict[str, Any]]) -> tuple[list[int | None], list[int | None]]:
    count = len(positions)
    prev_route: list[int | None] = [None] * count
    next_route: list[int | None] = [None] * count

    last_route: int | None = None
    for index, point in enumerate(positions):
        prev_route[index] = last_route
        if _extract_mode(point) == "graph_route":
            last_route = index

    next_route_index: int | None = None
    for index in range(count - 1, -1, -1):
        next_route[index] = next_route_index
        if _extract_mode(positions[index]) == "graph_route":
            next_route_index = index

    return prev_route, next_route


def _is_geometric_turn_fallback(
    positions: list[dict[str, Any]],
    index: int,
    prev_route: list[int | None],
    next_route: list[int | None],
    angle_threshold_deg: float,
) -> bool:
    prev_index = prev_route[index]
    next_index = next_route[index]
    if prev_index is None or next_index is None:
        return False

    prev_xyz = _extract_xyz(positions[prev_index])
    current_xyz = _extract_xyz(positions[index])
    next_xyz = _extract_xyz(positions[next_index])
    angle_deg = _angle_between_deg(
        _vector_3d(prev_xyz, current_xyz),
        _vector_3d(current_xyz, next_xyz),
    )
    if angle_deg is None:
        return False
    return angle_deg >= angle_threshold_deg


def classify_positions(
    positions: list[dict[str, Any]],
    turn_angle_threshold_deg: float,
) -> list[str]:
    if not positions:
        return []

    threshold = _validate_turn_angle_threshold_deg(turn_angle_threshold_deg)
    prev_route, next_route = _build_route_neighbors(positions)

    labels: list[str] = []
    for index, point in enumerate(positions):
        mode = _extract_mode(point)
        info = _extract_info(point)

        if mode in {"graph_takeoff", "graph_landing"}:
            labels.append(ROUTE_TAKEOFF_LANDING)
            continue

        if mode == "graph_route":
            if info.get("turn_type") is not None:
                labels.append(ROUTE_TURN)
                continue
            if _is_geometric_turn_fallback(
                positions=positions,
                index=index,
                prev_route=prev_route,
                next_route=next_route,
                angle_threshold_deg=threshold,
            ):
                labels.append(ROUTE_TURN)
            else:
                labels.append(ROUTE_STRAIGHT)
            continue

        labels.append(ROUTE_STRAIGHT)

    return labels


def _build_chunks(labels: list[str]) -> list[tuple[str, int, int]]:
    if not labels:
        return []

    chunks: list[tuple[str, int, int]] = []
    start_index = 0
    current_label = labels[0]
    for index in range(1, len(labels)):
        if labels[index] != current_label:
            chunks.append((current_label, start_index, index - 1))
            start_index = index
            current_label = labels[index]
    chunks.append((current_label, start_index, len(labels) - 1))
    return chunks


def _build_cumulative_lengths(points: list[dict[str, Any]]) -> list[float]:
    cumulative = [0.0]
    for index in range(1, len(points)):
        left_xyz = _extract_xyz(points[index - 1])
        right_xyz = _extract_xyz(points[index])
        cumulative.append(cumulative[-1] + _distance_3d(left_xyz, right_xyz))
    return cumulative


def _sample_point_on_polyline(
    points: list[dict[str, Any]],
    cumulative: list[float],
    distance_value: float,
) -> dict[str, Any]:
    if distance_value <= 0.0:
        return copy.deepcopy(points[0])
    if distance_value >= cumulative[-1]:
        return copy.deepcopy(points[-1])

    right_index = bisect.bisect_left(cumulative, distance_value)
    if right_index < len(cumulative) and abs(cumulative[right_index] - distance_value) <= EPSILON:
        return copy.deepcopy(points[right_index])
    if right_index <= 0:
        return copy.deepcopy(points[0])
    if right_index >= len(cumulative):
        return copy.deepcopy(points[-1])

    left_index = right_index - 1
    segment_length = cumulative[right_index] - cumulative[left_index]
    if segment_length <= EPSILON:
        return copy.deepcopy(points[left_index])

    t = (distance_value - cumulative[left_index]) / segment_length
    return _build_interpolated_point(points[left_index], points[right_index], t)


def _resample_interval(points: list[dict[str, Any]], step_distance: float) -> list[dict[str, Any]]:
    if len(points) <= 1:
        return [copy.deepcopy(point) for point in points]

    cumulative = _build_cumulative_lengths(points)
    total_length = cumulative[-1]
    if total_length <= EPSILON:
        return [copy.deepcopy(points[0]), copy.deepcopy(points[-1])]

    sample_distances = [0.0]
    cursor = step_distance
    while cursor < total_length - EPSILON:
        sample_distances.append(cursor)
        cursor += step_distance
    sample_distances.append(total_length)

    return [
        _sample_point_on_polyline(points, cumulative, sample_distance)
        for sample_distance in sample_distances
    ]


def _resample_chunk(points: list[dict[str, Any]], step_distance: float) -> list[dict[str, Any]]:
    if len(points) <= 1:
        return [copy.deepcopy(point) for point in points]

    keep_indices = {0, len(points) - 1}
    for index, point in enumerate(points):
        if _has_semantic_node_anchor(point):
            keep_indices.add(index)
    ordered_keep = sorted(keep_indices)

    if len(ordered_keep) <= 1:
        return [copy.deepcopy(point) for point in points]

    samples: list[dict[str, Any]] = []
    for interval_index in range(len(ordered_keep) - 1):
        start = ordered_keep[interval_index]
        end = ordered_keep[interval_index + 1]
        interval_points = points[start : end + 1]
        interval_samples = _resample_interval(interval_points, step_distance=step_distance)
        if not samples:
            samples.extend(interval_samples)
        else:
            samples.extend(interval_samples[1:])
    return samples


def resample_positions(
    positions: list[dict[str, Any]],
    *,
    step_distances: dict[str, float],
    turn_angle_threshold_deg: float,
) -> list[dict[str, Any]]:
    if len(positions) <= 1:
        result = [copy.deepcopy(point) for point in positions]
    else:
        labels = classify_positions(positions, turn_angle_threshold_deg=turn_angle_threshold_deg)
        chunks = _build_chunks(labels)

        result: list[dict[str, Any]] = []
        for label, start_index, end_index in chunks:
            chunk_points = positions[start_index : end_index + 1]
            step_distance = step_distances.get(label, step_distances[ROUTE_STRAIGHT])
            chunk_samples = _resample_chunk(chunk_points, step_distance=step_distance)
            result.extend(chunk_samples)

    image_digits, image_suffix = _infer_image_name_template(positions)
    for frame_index, point in enumerate(result):
        point["frame"] = frame_index
        point["image_path"] = f"{frame_index:0{image_digits}d}{image_suffix}"
    return result


def process_file(
    input_path: Path,
    output_path: Path,
    *,
    straight_step_distance: float | None,
    turn_step_distance: float | None,
    takeoff_landing_step_distance: float | None,
    turn_angle_threshold_deg: float,
) -> tuple[int, int]:
    with input_path.open("r", encoding="utf-8") as f:
        mission = json.load(f)

    positions = mission.get("positions")
    if not isinstance(positions, list):
        raise ValueError(f"`positions` is missing or not a list: {input_path}")
    if positions and not isinstance(positions[0], dict):
        raise ValueError(f"`positions` item format is invalid: {input_path}")

    resolved_steps = _resolve_step_distances(
        mission.get("route_meta"),
        straight_step_distance=straight_step_distance,
        turn_step_distance=turn_step_distance,
        takeoff_landing_step_distance=takeoff_landing_step_distance,
    )

    original_count = len(positions)
    resampled_positions = resample_positions(
        positions,
        step_distances=resolved_steps,
        turn_angle_threshold_deg=turn_angle_threshold_deg,
    )
    mission["positions"] = resampled_positions

    route_meta = mission.get("route_meta")
    if not isinstance(route_meta, dict):
        route_meta = {}
        mission["route_meta"] = route_meta
    route_meta["resample_method"] = "distance_classified_v2"
    route_meta["resample_straight_step_distance"] = float(resolved_steps[ROUTE_STRAIGHT])
    route_meta["resample_turn_step_distance"] = float(resolved_steps[ROUTE_TURN])
    route_meta["resample_takeoff_landing_step_distance"] = float(resolved_steps[ROUTE_TAKEOFF_LANDING])
    route_meta["resample_turn_angle_threshold_deg"] = float(turn_angle_threshold_deg)
    route_meta["resample_original_count"] = int(original_count)
    route_meta["resample_new_count"] = int(len(resampled_positions))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(mission, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return original_count, len(resampled_positions)


def main() -> int:
    args = _parse_args()
    input_dir: Path = args.input_dir.resolve()
    in_place = bool(args.in_place)
    file_glob = str(args.glob)
    turn_angle_threshold_deg = _validate_turn_angle_threshold_deg(float(args.turn_angle_threshold_deg))

    if args.straight_step_distance is not None:
        _validate_positive("--straight-step-distance", float(args.straight_step_distance))
    if args.turn_step_distance is not None:
        _validate_positive("--turn-step-distance", float(args.turn_step_distance))
    if args.takeoff_landing_step_distance is not None:
        _validate_positive("--takeoff-landing-step-distance", float(args.takeoff_landing_step_distance))

    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    if in_place:
        output_dir = input_dir
    else:
        output_dir = (
            args.output_dir.resolve()
            if args.output_dir is not None
            else input_dir.parent / f"{input_dir.name}_resampled_distance_classified"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob(file_glob))
    if not json_files:
        print(f"No files matched: dir={input_dir}, glob={file_glob}")
        return 0

    total_before = 0
    total_after = 0
    processed_count = 0

    for file_path in json_files:
        if not file_path.is_file():
            continue
        output_path = file_path if in_place else (output_dir / file_path.name)
        before, after = process_file(
            file_path,
            output_path,
            straight_step_distance=args.straight_step_distance,
            turn_step_distance=args.turn_step_distance,
            takeoff_landing_step_distance=args.takeoff_landing_step_distance,
            turn_angle_threshold_deg=turn_angle_threshold_deg,
        )
        total_before += before
        total_after += after
        processed_count += 1
        print(
            f"[OK] {file_path.name}: {before} -> {after} "
            f"(added {after - before} points)"
        )

    print("-" * 70)
    print(f"Files: {processed_count}")
    print(f"Total points: {total_before} -> {total_after} (added {total_after - total_before})")
    print(f"Output dir: {output_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
