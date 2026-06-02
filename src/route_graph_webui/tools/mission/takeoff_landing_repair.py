from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


from route_graph_webui.runtime_support.env_registry import extract_env_name
from route_graph_webui.graph.model import GraphSchemaError
from route_graph_webui.mission.io import load_mission_json, write_mission_json
from route_graph_webui.runtime_support.runtime import timestamp_now
from route_graph_webui.storage.spelling_compat import (
    CANONICAL_PHOTOS_DIR_NAME,
    LEGACY_PHOTOS_DIR_NAME,
    resolve_photos_root,
)
from route_graph_webui.storage.graph_store import PROJECT_ROOT, resolve_data_path
from route_graph_webui.tools.mission.mission_repair import merge_repair_images, repair_mission_payload


DEFAULT_RELATIVE_Z = 200.0
DEFAULT_TAKEOFF_LANDING_STEP_DISTANCE = 20.0


@dataclass(frozen=True, slots=True)
class RepairTask:
    mission_path: Path
    photo_dir: Path
    mission_name: str
    scene_name: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-repair missing takeoff/landing frames for replay mission JSON files."
    )
    parser.add_argument(
        "--missions-root",
        required=True,
        help="Directory containing mission JSON files for a single scene.",
    )
    parser.add_argument(
        "--photos-root",
        default=None,
        help=(
            "Scene photo root directory that contains one subdirectory per mission. "
            f"Default: data/data_photos_videos/{CANONICAL_PHOTOS_DIR_NAME}/<missions-root-name> "
            f"(fallback: data/data_photos_videos/{LEGACY_PHOTOS_DIR_NAME}/<missions-root-name>)."
        ),
    )
    parser.add_argument(
        "--start-name",
        default=None,
        help="Inclusive starting mission stem, for example Venice_C450.",
    )
    parser.add_argument(
        "--end-name",
        default=None,
        help="Inclusive ending mission stem, for example Venice_C500.",
    )
    parser.add_argument(
        "--relative-z",
        type=float,
        default=DEFAULT_RELATIVE_Z,
        help=f"Vertical offset to add below route altitude (default: {DEFAULT_RELATIVE_Z}).",
    )
    parser.add_argument(
        "--takeoff-landing-step-distance",
        type=float,
        default=DEFAULT_TAKEOFF_LANDING_STEP_DISTANCE,
        help=(
            "Interpolation step distance for repaired takeoff/landing segments "
            f"(default: {DEFAULT_TAKEOFF_LANDING_STEP_DISTANCE})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate repairability and write the report, but do not replay or overwrite any files.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first mission failure instead of continuing the batch.",
    )
    parser.add_argument(
        "--cleanup-backups",
        action="store_true",
        help=(
            "Delete the per-task pre-repair JSON and photo backups immediately after a task "
            "finishes successfully."
        ),
    )
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    return load_mission_json(path)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    return write_mission_json(path, payload)


def _parse_scene_from_env_id(env_id: Any) -> str | None:
    try:
        return extract_env_name(env_id)
    except ValueError:
        return None


def _resolve_default_photos_root(missions_root: Path) -> Path:
    scene_name = missions_root.name
    data_root = resolve_data_path("data_photos_videos")
    return resolve_photos_root(data_root, scene_name=scene_name)


def _list_mission_paths(missions_root: Path) -> list[Path]:
    if not missions_root.is_dir():
        raise GraphSchemaError(f"`--missions-root` does not exist: {missions_root}")
    paths = sorted(
        [
            path.resolve()
            for path in missions_root.iterdir()
            if path.is_file() and path.suffix.lower() == ".json"
        ],
        key=lambda path: path.stem,
    )
    if not paths:
        raise GraphSchemaError(f"No JSON files found under `{missions_root}`")
    return paths


def _select_mission_paths(
    mission_paths: list[Path],
    *,
    start_name: str | None,
    end_name: str | None,
) -> list[Path]:
    name_lookup = {path.stem: path for path in mission_paths}
    if start_name and start_name not in name_lookup:
        raise GraphSchemaError(f"`--start-name` was not found: {start_name}")
    if end_name and end_name not in name_lookup:
        raise GraphSchemaError(f"`--end-name` was not found: {end_name}")

    selected = [
        path
        for path in mission_paths
        if (start_name is None or path.stem >= start_name)
        and (end_name is None or path.stem <= end_name)
    ]
    if not selected:
        raise GraphSchemaError("The requested mission range is empty")
    if start_name and end_name and start_name > end_name:
        raise GraphSchemaError("`--start-name` must be less than or equal to `--end-name`")
    return selected


def _build_tasks(
    *,
    missions_root: Path,
    photos_root: Path,
    start_name: str | None,
    end_name: str | None,
) -> list[RepairTask]:
    mission_paths = _select_mission_paths(
        _list_mission_paths(missions_root),
        start_name=start_name,
        end_name=end_name,
    )
    scene_name = missions_root.name
    return [
        RepairTask(
            mission_path=path,
            photo_dir=(photos_root / path.stem).resolve(),
            mission_name=path.stem,
            scene_name=scene_name,
        )
        for path in mission_paths
    ]


def _unique_backup_path(path: Path, *, suffix_label: str) -> Path:
    timestamp = timestamp_now().replace(":", "").replace("-", "")
    if path.is_dir() or path.suffix == "":
        base_name = f"{path.name}__{suffix_label}_{timestamp}"
        candidate = path.parent / base_name
    else:
        base_name = f"{path.stem}__{suffix_label}_{timestamp}"
        candidate = path.with_name(f"{base_name}{path.suffix}")
    index = 1
    while candidate.exists():
        if path.is_dir() or path.suffix == "":
            candidate = path.parent / f"{base_name}_{index:03d}"
        else:
            candidate = path.with_name(f"{base_name}_{index:03d}{path.suffix}")
        index += 1
    return candidate


def _build_replay_command(*, repair_json_path: Path, replay_output_root: Path, env_id: str) -> list[str]:
    return [
        sys.executable,
        str((PROJECT_ROOT / "collect_manual_two_step.py").resolve()),
        "--mode",
        "replay",
        "--env-id",
        env_id,
        "--load-file",
        str(repair_json_path),
        "--replay_output_dir",
        str(replay_output_root),
    ]


def _run_replay_capture(*, repair_json_path: Path, replay_output_root: Path, env_id: str) -> Path:
    command = _build_replay_command(
        repair_json_path=repair_json_path,
        replay_output_root=replay_output_root,
        env_id=env_id,
    )
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    combined = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    if result.returncode != 0:
        raise RuntimeError(combined or f"Replay command failed with exit code {result.returncode}")

    replay_dir = replay_output_root / repair_json_path.stem
    if not replay_dir.is_dir():
        raise RuntimeError(
            combined
            or f"Replay finished without creating an output directory: {replay_dir}"
        )
    return replay_dir.resolve()


def _commit_repair_outputs(
    *,
    mission_path: Path,
    photo_dir: Path,
    repaired_json_path: Path,
    merged_photo_dir: Path,
) -> tuple[Path, Path]:
    if not photo_dir.is_dir():
        raise GraphSchemaError(f"Photo directory does not exist: {photo_dir}")

    backup_json_path = _unique_backup_path(mission_path, suffix_label="backup")
    backup_photo_dir = _unique_backup_path(photo_dir, suffix_label="backup")
    shutil.copy2(mission_path, backup_json_path)

    photos_moved = False
    json_replaced = False
    try:
        os.replace(str(photo_dir), str(backup_photo_dir))
        photos_moved = True
        os.replace(str(repaired_json_path), str(mission_path))
        json_replaced = True
        os.replace(str(merged_photo_dir), str(photo_dir))
    except Exception:
        if json_replaced and backup_json_path.exists():
            shutil.copy2(backup_json_path, mission_path)
        if photos_moved:
            if photo_dir.exists():
                shutil.rmtree(photo_dir, ignore_errors=True)
            if backup_photo_dir.exists():
                os.replace(str(backup_photo_dir), str(photo_dir))
        raise

    return backup_json_path.resolve(), backup_photo_dir.resolve()


def _cleanup_backup_outputs(
    *,
    backup_json_path: Path,
    backup_photo_dir: Path,
) -> str | None:
    try:
        if backup_json_path.exists():
            backup_json_path.unlink()
        if backup_photo_dir.exists():
            shutil.rmtree(backup_photo_dir, ignore_errors=False)
    except Exception as exc:
        return str(exc)
    return None


def _resolve_video_path(task: RepairTask) -> Path:
    data_photos_videos_dir = task.photo_dir.parent.parent.parent
    return (data_photos_videos_dir / "videos" / task.scene_name / f"{task.mission_name}.mp4").resolve()


def _append_report_line(handle, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def _process_task(
    task: RepairTask,
    *,
    relative_z: float,
    takeoff_landing_step_distance: float,
    dry_run: bool,
    cleanup_backups: bool,
) -> dict[str, Any]:
    mission = _load_json(task.mission_path)
    env_id = mission.get("env_id")
    scene_from_env = _parse_scene_from_env_id(env_id)
    if scene_from_env and scene_from_env != task.scene_name:
        raise GraphSchemaError(
            f"Scene mismatch for {task.mission_name}: env_id={scene_from_env}, path={task.scene_name}"
        )
    if not isinstance(env_id, str) or not env_id.strip():
        env_id = f"UnrealTrack-{task.scene_name}-ContinuousColor-v0"

    bundle = repair_mission_payload(
        mission,
        relative_z=relative_z,
        takeoff_landing_step_distance=takeoff_landing_step_distance,
    )
    video_path = _resolve_video_path(task)
    record = {
        "mission_name": task.mission_name,
        "scene_name": task.scene_name,
        "mission_path": str(task.mission_path),
        "photo_dir": str(task.photo_dir),
        "status": "dry_run" if dry_run else "planned",
        "original_frame_count": int(bundle.original_count),
        "takeoff_added_count": int(bundle.takeoff_count),
        "landing_added_count": int(bundle.landing_count),
        "repaired_frame_count": int(len(bundle.repaired_mission["positions"])),
        "stale_video_path": str(video_path) if video_path.exists() else None,
    }

    if dry_run:
        return record

    with tempfile.TemporaryDirectory(
        prefix=f"takeoff_landing_repair_{task.mission_name}_",
        dir=str(task.mission_path.parent),
    ) as temp_dir:
        work_dir = Path(temp_dir)
        repaired_json_path = _write_json(work_dir / task.mission_path.name, bundle.repaired_mission)
        replay_output_root = work_dir / "replay_output"
        replay_output_root.mkdir(parents=True, exist_ok=True)

        if bundle.replay_mission is None:
            replay_json_path = None
            replay_dir = work_dir / "empty_replay"
            replay_dir.mkdir(parents=True, exist_ok=True)
        else:
            replay_json_path = _write_json(
                work_dir / f"{task.mission_name}__repair_takeoff_landing.json",
                bundle.replay_mission,
            )
            replay_dir = _run_replay_capture(
                repair_json_path=replay_json_path,
                replay_output_root=replay_output_root,
                env_id=env_id,
            )

        merged_photo_dir = merge_repair_images(
            original_photo_dir=task.photo_dir,
            replay_photo_dir=replay_dir,
            output_dir=work_dir / f"{task.mission_name}__merged_photos",
            original_positions=list(mission["positions"]),
            repaired_positions=list(bundle.repaired_mission["positions"]),
            replay_positions=[] if bundle.replay_mission is None else list(bundle.replay_mission["positions"]),
            takeoff_count=bundle.takeoff_count,
            landing_count=bundle.landing_count,
        )
        backup_json_path, backup_photo_dir = _commit_repair_outputs(
            mission_path=task.mission_path,
            photo_dir=task.photo_dir,
            repaired_json_path=repaired_json_path,
            merged_photo_dir=merged_photo_dir,
        )
        record["status"] = "repaired"
        record["backup_json_path"] = str(backup_json_path)
        record["backup_photo_dir"] = str(backup_photo_dir)
        record["cleanup_backups_enabled"] = bool(cleanup_backups)
        if replay_json_path is not None:
            record["replay_json_path"] = str(replay_json_path)
            record["replay_output_dir"] = str(replay_dir)
        if cleanup_backups:
            cleanup_error = _cleanup_backup_outputs(
                backup_json_path=backup_json_path,
                backup_photo_dir=backup_photo_dir,
            )
            if cleanup_error is None:
                record["backup_cleanup_status"] = "deleted"
            else:
                record["backup_cleanup_status"] = "failed"
                record["backup_cleanup_error"] = cleanup_error
        return record


def run_batch_repair(args: argparse.Namespace) -> dict[str, Any]:
    missions_root = Path(args.missions_root).resolve()
    if not missions_root.is_dir():
        raise GraphSchemaError(f"`--missions-root` does not exist: {missions_root}")
    photos_root = (
        Path(args.photos_root).resolve()
        if args.photos_root
        else _resolve_default_photos_root(missions_root)
    )
    if not photos_root.is_dir():
        raise GraphSchemaError(f"Photo root does not exist: {photos_root}")

    tasks = _build_tasks(
        missions_root=missions_root,
        photos_root=photos_root,
        start_name=args.start_name,
        end_name=args.end_name,
    )

    report_path = (
        missions_root.parent / f"takeoff_landing_repair_report_{timestamp_now().replace(':', '').replace('-', '')}.jsonl"
    ).resolve()
    succeeded: list[str] = []
    failed: list[str] = []

    with report_path.open("w", encoding="utf-8") as report_handle:
        for index, task in enumerate(tasks, start=1):
            print(f"[{index}/{len(tasks)}] {task.mission_name}", flush=True)
            try:
                record = _process_task(
                    task,
                    relative_z=args.relative_z,
                    takeoff_landing_step_distance=args.takeoff_landing_step_distance,
                    dry_run=bool(args.dry_run),
                    cleanup_backups=bool(getattr(args, "cleanup_backups", False)),
                )
                succeeded.append(task.mission_name)
                _append_report_line(report_handle, record)
                cleanup_suffix = ""
                if record.get("backup_cleanup_status") == "deleted":
                    cleanup_suffix = " backups=deleted"
                elif record.get("backup_cleanup_status") == "failed":
                    cleanup_suffix = " backups=cleanup_failed"
                print(
                    f"  OK: takeoff+{record['takeoff_added_count']} landing+{record['landing_added_count']} "
                    f"status={record['status']}{cleanup_suffix}",
                    flush=True,
                )
            except Exception as exc:
                failed.append(task.mission_name)
                record = {
                    "mission_name": task.mission_name,
                    "scene_name": task.scene_name,
                    "mission_path": str(task.mission_path),
                    "photo_dir": str(task.photo_dir),
                    "status": "failed",
                    "error": str(exc),
                }
                _append_report_line(report_handle, record)
                print(f"  FAILED: {exc}", flush=True)
                if args.fail_fast:
                    break

    return {
        "report_path": str(report_path),
        "requested_count": len(tasks),
        "succeeded": succeeded,
        "failed": failed,
        "photos_root": str(photos_root),
        "missions_root": str(missions_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.relative_z < 0:
            raise GraphSchemaError("`--relative-z` must be non-negative")
        if args.takeoff_landing_step_distance <= 0:
            raise GraphSchemaError("`--takeoff-landing-step-distance` must be positive")
        summary = run_batch_repair(args)
    except (GraphSchemaError, RuntimeError, OSError, ValueError) as exc:
        print(exc)
        return 1

    print(f"Report: {summary['report_path']}")
    print(f"Requested: {summary['requested_count']}")
    print(f"Succeeded: {len(summary['succeeded'])}")
    print(f"Failed: {len(summary['failed'])}")
    if summary["failed"]:
        print(f"Failed missions: {', '.join(summary['failed'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
