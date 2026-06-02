from __future__ import annotations

import argparse
import copy
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


from route_graph_webui.graph.model import GraphSchemaError
from route_graph_webui.mission.io import (
    infer_image_name_template,
    load_mission_json,
    reindex_positions,
    write_mission_json,
)
from route_graph_webui.shared.image_sequence import (
    SUPPORTED_IMAGE_EXTENSIONS,
    collect_image_files as collect_shared_image_files,
)
from route_graph_webui.runtime_support.runtime import timestamp_now


EPSILON = 1e-9
SUPPORTED_IMAGE_SUFFIXES = SUPPORTED_IMAGE_EXTENSIONS


@dataclass(frozen=True, slots=True)
class MissionRepairBundle:
    repaired_mission: dict[str, Any]
    replay_mission: dict[str, Any] | None
    takeoff_count: int
    landing_count: int
    original_count: int

    @property
    def replay_count(self) -> int:
        return self.takeoff_count + self.landing_count


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _validate_positive(name: str, value: Any) -> float:
    if not _is_number(value) or float(value) <= 0.0:
        raise GraphSchemaError(f"`{name}` must be positive")
    return float(value)


def _validate_non_negative(name: str, value: Any) -> float:
    if not _is_number(value) or float(value) < 0.0:
        raise GraphSchemaError(f"`{name}` must be non-negative")
    return float(value)


def _extract_info(point: Mapping[str, Any]) -> dict[str, Any]:
    info = point.get("info")
    if isinstance(info, Mapping):
        return dict(info)
    return {}


def _extract_mode(point: Mapping[str, Any]) -> str | None:
    mode = _extract_info(point).get("mode")
    if isinstance(mode, str):
        return mode
    return None


def _extract_state(point: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    state = point.get("state")
    if (
        not isinstance(state, list)
        or len(state) != 2
        or not isinstance(state[0], list)
        or not isinstance(state[1], list)
        or len(state[0]) != 3
        or len(state[1]) != 3
    ):
        raise GraphSchemaError("positions[*].state must be [[x, y, z], [roll, yaw, pitch]]")
    xyz = [float(value) for value in state[0]]
    ryp = [float(value) for value in state[1]]
    return xyz, ryp


def _infer_image_name_template(positions: Iterable[Mapping[str, Any]]) -> tuple[int, str]:
    return infer_image_name_template(positions)


def _interpolate_segment(
    start_xyz: list[float],
    end_xyz: list[float],
    step_distance: float,
) -> list[list[float]]:
    dx = end_xyz[0] - start_xyz[0]
    dy = end_xyz[1] - start_xyz[1]
    dz = end_xyz[2] - start_xyz[2]
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    step_distance = _validate_positive("takeoff_landing_step_distance", step_distance)
    steps = max(1, int(math.ceil(distance / step_distance)))
    points: list[list[float]] = []
    for index in range(1, steps + 1):
        ratio = index / steps
        points.append(
            [
                round(start_xyz[0] + (dx * ratio), 6),
                round(start_xyz[1] + (dy * ratio), 6),
                round(start_xyz[2] + (dz * ratio), 6),
            ]
        )
    return points


def _build_takeoff_points(
    route_start_point: Mapping[str, Any],
    *,
    relative_z: float,
    step_distance: float,
) -> list[dict[str, Any]]:
    route_xyz, route_ryp = _extract_state(route_start_point)
    if relative_z <= EPSILON:
        return []
    takeoff_xyz = [route_xyz[0], route_xyz[1], round(route_xyz[2] - relative_z, 6)]
    if abs(takeoff_xyz[2] - route_xyz[2]) <= EPSILON:
        return []

    samples = _interpolate_segment(takeoff_xyz, route_xyz, step_distance)
    route_info = _extract_info(route_start_point)
    first_node_id = route_info.get("node_id")
    points: list[dict[str, Any]] = []
    all_xyz = [takeoff_xyz] + samples[:-1]
    for index, xyz in enumerate(all_xyz):
        node_id = first_node_id if index == 0 else None
        points.append(
            {
                "state": [
                    list(xyz),
                    [round(route_ryp[0], 6), round(route_ryp[1], 6), round(route_ryp[2], 6)],
                ],
                "info": {
                    "mode": "graph_takeoff",
                    "node_id": node_id,
                    "edge_id": None,
                    "segment_index": None,
                    "pass_index": None,
                },
            }
        )
    return points


def _build_landing_points(
    route_end_point: Mapping[str, Any],
    *,
    relative_z: float,
    step_distance: float,
) -> list[dict[str, Any]]:
    route_xyz, route_ryp = _extract_state(route_end_point)
    if relative_z <= EPSILON:
        return []
    landing_xyz = [route_xyz[0], route_xyz[1], round(route_xyz[2] - relative_z, 6)]
    if abs(landing_xyz[2] - route_xyz[2]) <= EPSILON:
        return []

    samples = _interpolate_segment(route_xyz, landing_xyz, step_distance)
    route_info = _extract_info(route_end_point)
    last_node_id = route_info.get("node_id")
    points: list[dict[str, Any]] = []
    for index, xyz in enumerate(samples):
        is_last = index == len(samples) - 1
        points.append(
            {
                "state": [
                    list(xyz),
                    [round(route_ryp[0], 6), round(route_ryp[1], 6), round(route_ryp[2], 6)],
                ],
                "info": {
                    "mode": "graph_landing",
                    "node_id": last_node_id if is_last else None,
                    "edge_id": None,
                    "segment_index": None,
                    "pass_index": None,
                },
            }
        )
    return points


def _reindex_positions(
    positions: list[dict[str, Any]],
    *,
    start_time: float,
    fps: float,
    image_name_builder,
) -> list[dict[str, Any]]:
    image_digits, image_suffix = infer_image_name_template(
        [{"image_path": image_name_builder(0)}]
    )
    copied_positions = [copy.deepcopy(point) for point in positions]
    return reindex_positions(
        copied_positions,
        start_time=start_time,
        fps=fps,
        image_digits=image_digits,
        image_suffix=image_suffix,
    )


def _repair_keyframes(
    keyframes: Any,
    *,
    takeoff_count: int,
    image_digits: int,
    image_suffix: str,
) -> list[Any]:
    if not isinstance(keyframes, list):
        return []

    repaired: list[Any] = []
    for item in keyframes:
        if not isinstance(item, Mapping):
            repaired.append(copy.deepcopy(item))
            continue
        updated = copy.deepcopy(dict(item))
        raw_frame = updated.get("frame_number", updated.get("frame"))
        if isinstance(raw_frame, bool):
            repaired.append(updated)
            continue
        if isinstance(raw_frame, (int, float)):
            next_frame = int(raw_frame) + int(takeoff_count)
            if "frame_number" in updated:
                updated["frame_number"] = next_frame
            if "frame" in updated:
                updated["frame"] = next_frame
            if "image_filename" in updated and isinstance(updated["image_filename"], str):
                updated["image_filename"] = f"{next_frame:0{image_digits}d}{image_suffix}"
            if "image_path" in updated and isinstance(updated["image_path"], str):
                updated["image_path"] = f"{next_frame:0{image_digits}d}{image_suffix}"
        repaired.append(updated)
    return repaired


def _copy_mission_header(mission: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "env_id": mission.get("env_id"),
        "graph_name": mission.get("graph_name"),
    }


def repair_mission_payload(
    mission: Mapping[str, Any],
    *,
    relative_z: float,
    takeoff_landing_step_distance: float,
) -> MissionRepairBundle:
    relative_z = _validate_non_negative("relative_z", relative_z)
    takeoff_landing_step_distance = _validate_positive(
        "takeoff_landing_step_distance",
        takeoff_landing_step_distance,
    )

    positions = mission.get("positions")
    if not isinstance(positions, list) or not positions:
        raise GraphSchemaError("Mission JSON must contain a non-empty `positions` list")
    if any(not isinstance(point, Mapping) for point in positions):
        raise GraphSchemaError("Mission `positions` must contain mapping items")

    route_meta = mission.get("route_meta")
    if route_meta is None:
        route_meta_dict: dict[str, Any] = {}
    elif isinstance(route_meta, Mapping):
        route_meta_dict = dict(route_meta)
    else:
        raise GraphSchemaError("Mission `route_meta` must be a mapping when present")

    if bool(route_meta_dict.get("takeoff_landing_enabled")):
        raise GraphSchemaError("Mission already has takeoff/landing enabled")

    modes = [_extract_mode(point) for point in positions]
    if any(mode in {"graph_takeoff", "graph_landing"} for mode in modes):
        raise GraphSchemaError("Mission already contains takeoff/landing frames")
    if any(mode not in {None, "graph_route", "graph_turn"} for mode in modes):
        raise GraphSchemaError("Mission contains unsupported non-route frames")

    fps = _validate_positive("route_meta.fps", route_meta_dict.get("fps", 0.0))
    start_time = (
        float(positions[0].get("time"))
        if _is_number(positions[0].get("time"))
        else 0.0
    )
    image_digits, image_suffix = _infer_image_name_template(positions)

    original_positions = [copy.deepcopy(dict(point)) for point in positions]
    takeoff_points = _build_takeoff_points(
        positions[0],
        relative_z=relative_z,
        step_distance=takeoff_landing_step_distance,
    )
    landing_points = _build_landing_points(
        positions[-1],
        relative_z=relative_z,
        step_distance=takeoff_landing_step_distance,
    )
    if not takeoff_points and not landing_points:
        raise GraphSchemaError("No takeoff/landing repair frames were generated")

    repaired_positions = _reindex_positions(
        takeoff_points + original_positions + landing_points,
        start_time=start_time,
        fps=fps,
        image_name_builder=lambda index: f"{index:0{image_digits}d}{image_suffix}",
    )

    replay_positions = _reindex_positions(
        takeoff_points + landing_points,
        start_time=0.0,
        fps=fps,
        image_name_builder=lambda index: f"repair_{index:0{image_digits}d}{image_suffix}",
    )

    route_start_xyz, _ = _extract_state(positions[0])
    route_end_xyz, _ = _extract_state(positions[-1])
    repaired_route_meta = copy.deepcopy(route_meta_dict)
    repaired_route_meta["takeoff_landing_relative_z"] = float(relative_z)
    repaired_route_meta["takeoff_landing_step_distance"] = float(takeoff_landing_step_distance)
    repaired_route_meta["takeoff_landing_enabled"] = True
    repaired_route_meta["takeoff_start_z"] = round(route_start_xyz[2] - relative_z, 6)
    repaired_route_meta["landing_end_z"] = round(route_end_xyz[2] - relative_z, 6)
    repaired_route_meta["repair_meta"] = {
        "method": "takeoff_landing_repair_v1",
        "relative_z": float(relative_z),
        "takeoff_landing_step_distance": float(takeoff_landing_step_distance),
        "original_frame_count": int(len(original_positions)),
        "takeoff_added_count": int(len(takeoff_points)),
        "landing_added_count": int(len(landing_points)),
        "repaired_frame_count": int(len(repaired_positions)),
        "repaired_at": timestamp_now(),
    }

    repaired_mission = copy.deepcopy(dict(mission))
    repaired_mission["positions"] = repaired_positions
    repaired_mission["keyframes"] = _repair_keyframes(
        mission.get("keyframes"),
        takeoff_count=len(takeoff_points),
        image_digits=image_digits,
        image_suffix=image_suffix,
    )
    repaired_mission["route_meta"] = repaired_route_meta

    replay_mission: dict[str, Any] | None
    if replay_positions:
        replay_mission = _copy_mission_header(mission)
        replay_mission["positions"] = replay_positions
        replay_mission["keyframes"] = []
        replay_mission["route_meta"] = {
            "repair_mode": "takeoff_landing_only",
            "takeoff_added_count": int(len(takeoff_points)),
            "landing_added_count": int(len(landing_points)),
            "source_repaired_frame_count": int(len(repaired_positions)),
            "generated_at": timestamp_now(),
        }
    else:
        replay_mission = None

    return MissionRepairBundle(
        repaired_mission=repaired_mission,
        replay_mission=replay_mission,
        takeoff_count=len(takeoff_points),
        landing_count=len(landing_points),
        original_count=len(original_positions),
    )


def collect_image_files(photo_dir: str | Path) -> list[Path]:
    directory = Path(photo_dir)
    if not directory.is_dir():
        raise GraphSchemaError(f"Photo directory does not exist: {directory}")
    return sorted(collect_shared_image_files(directory), key=lambda path: path.name)


def validate_photo_directory_for_positions(
    photo_dir: str | Path,
    positions: Iterable[Mapping[str, Any]],
    *,
    label: str,
) -> dict[str, Path]:
    files = collect_image_files(photo_dir)
    expected_names = []
    for point in positions:
        image_path = point.get("image_path")
        if not isinstance(image_path, str) or not image_path.strip():
            raise GraphSchemaError(f"{label} mission contains an invalid `image_path`")
        expected_names.append(Path(image_path).name)
    if len(files) != len(expected_names):
        raise GraphSchemaError(
            f"{label} image count mismatch: {len(files)} files != {len(expected_names)} positions"
        )

    file_lookup = {path.name: path for path in files}
    missing = [name for name in expected_names if name not in file_lookup]
    if missing:
        raise GraphSchemaError(
            f"{label} image directory is missing expected frames: {', '.join(missing[:5])}"
        )
    return file_lookup


def merge_repair_images(
    *,
    original_photo_dir: str | Path,
    replay_photo_dir: str | Path,
    output_dir: str | Path,
    original_positions: list[Mapping[str, Any]],
    repaired_positions: list[Mapping[str, Any]],
    replay_positions: list[Mapping[str, Any]],
    takeoff_count: int,
    landing_count: int,
) -> Path:
    if len(repaired_positions) != (takeoff_count + len(original_positions) + landing_count):
        raise GraphSchemaError("Repaired position count does not match prefix/original/suffix counts")
    if len(replay_positions) != (takeoff_count + landing_count):
        raise GraphSchemaError("Replay position count does not match takeoff/landing counts")

    original_lookup = validate_photo_directory_for_positions(
        original_photo_dir,
        original_positions,
        label="Original",
    )
    replay_lookup = validate_photo_directory_for_positions(
        replay_photo_dir,
        replay_positions,
        label="Replay",
    )

    output_path = Path(output_dir)
    if output_path.exists():
        shutil.rmtree(output_path, ignore_errors=True)
    output_path.mkdir(parents=True, exist_ok=True)

    prefix_names = [Path(point["image_path"]).name for point in replay_positions[:takeoff_count]]
    suffix_names = [
        Path(point["image_path"]).name
        for point in replay_positions[takeoff_count : takeoff_count + landing_count]
    ]

    for index, repaired_point in enumerate(repaired_positions):
        destination = output_path / Path(str(repaired_point["image_path"])).name
        if index < takeoff_count:
            source = replay_lookup[prefix_names[index]]
        elif index < takeoff_count + len(original_positions):
            source_index = index - takeoff_count
            source_name = Path(str(original_positions[source_index]["image_path"])).name
            source = original_lookup[source_name]
        else:
            suffix_index = index - takeoff_count - len(original_positions)
            source = replay_lookup[suffix_names[suffix_index]]
        shutil.copy2(source, destination)

    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair takeoff/landing frames in a single mission JSON payload.")
    parser.add_argument("--input", required=True, help="Input mission JSON path")
    parser.add_argument("--output", required=True, help="Output repaired mission JSON path")
    parser.add_argument("--replay-output", help="Optional output path for the takeoff/landing replay-only JSON")
    parser.add_argument("--relative-z", type=float, required=True, help="Vertical offset below route altitude")
    parser.add_argument(
        "--takeoff-landing-step-distance",
        type=float,
        required=True,
        help="Interpolation step distance for repaired takeoff/landing segments",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        mission = load_mission_json(args.input)
        bundle = repair_mission_payload(
            mission,
            relative_z=args.relative_z,
            takeoff_landing_step_distance=args.takeoff_landing_step_distance,
        )
        write_mission_json(args.output, bundle.repaired_mission)
        if args.replay_output and bundle.replay_mission is not None:
            write_mission_json(args.replay_output, bundle.replay_mission)
    except (GraphSchemaError, OSError, ValueError) as exc:
        print(exc)
        return 1

    print(f"Saved repaired mission JSON to {Path(args.output).resolve()}")
    if args.replay_output and bundle.replay_mission is not None:
        print(f"Saved replay mission JSON to {Path(args.replay_output).resolve()}")
    print(f"Original frames: {bundle.original_count}")
    print(f"Takeoff frames added: {bundle.takeoff_count}")
    print(f"Landing frames added: {bundle.landing_count}")
    return 0


__all__ = [
    "MissionRepairBundle",
    "SUPPORTED_IMAGE_SUFFIXES",
    "build_parser",
    "collect_image_files",
    "main",
    "merge_repair_images",
    "repair_mission_payload",
    "validate_photo_directory_for_positions",
]


if __name__ == "__main__":
    raise SystemExit(main())
