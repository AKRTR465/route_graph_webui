from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from auto_route_planner import AutoPlanningProgress, AutoRoutePlanningError, auto_plan_routes
    from graph_schema import GraphSchemaError, RouteGraph
    from json_store import append_jsonl, read_json, write_json_atomic
    from route_planner import RoutePlanningProgress, RoutePlanningError, generate_route_candidates
else:
    from .auto_route_planner import AutoPlanningProgress, AutoRoutePlanningError, auto_plan_routes
    from .graph_schema import GraphSchemaError, RouteGraph
    from .json_store import append_jsonl, read_json, write_json_atomic
    from .route_planner import RoutePlanningProgress, RoutePlanningError, generate_route_candidates


def _progress_to_dict(progress: RoutePlanningProgress | AutoPlanningProgress) -> dict[str, Any]:
    if isinstance(progress, AutoPlanningProgress):
        return {
            "phase": progress.phase,
            "pairs_considered": int(progress.pairs_considered),
            "max_pairs_to_evaluate": int(progress.max_pairs_to_evaluate),
            "valid_pairs_found": int(progress.valid_pairs_found),
            "candidate_pool_size": int(progress.candidate_pool_size),
            "selected_routes": int(progress.selected_routes),
            "max_output_routes": int(progress.max_output_routes),
            "done": bool(progress.done),
            "searched_candidates": int(progress.searched_candidates),
            "filtered_candidates": int(progress.filtered_candidates),
            "kept_candidates": int(progress.kept_candidates),
            "progress_kind": "auto",
        }
    return {
        "phase": progress.phase,
        "expansions": int(progress.expansions),
        "max_search_states": int(progress.max_search_states),
        "candidates_found": int(progress.candidates_found),
        "truncated": bool(progress.truncated),
        "done": bool(progress.done),
        "progress_kind": "manual",
    }


def run_route_generation_task(
    task_payload: Mapping[str, Any],
    message_queue,
) -> None:
    job_id = int(task_payload["job_id"])

    def publish(message_type: str, **payload: Any) -> None:
        message_queue.put(
            {
                "type": message_type,
                "job_id": job_id,
                **payload,
            }
        )

    try:
        graph = RouteGraph.from_mapping(task_payload["graph"])

        def on_progress(progress: RoutePlanningProgress) -> None:
            publish("progress", progress=_progress_to_dict(progress))

        if task_payload.get("planning_mode") == "auto":
            candidate_set = auto_plan_routes(
                graph,
                config=task_payload.get("auto_config") or {},
                progress_callback=on_progress,
            )
        else:
            candidate_set = generate_route_candidates(
                graph,
                start=str(task_payload["start"]),
                via=[str(node_id) for node_id in task_payload.get("via", [])],
                end=str(task_payload["end"]),
                max_routes=int(task_payload["max_routes"]),
                max_edge_pass_factor=float(task_payload["max_edge_pass_factor"]),
                min_total_length=(
                    None
                    if task_payload.get("min_total_length") is None
                    else float(task_payload["min_total_length"])
                ),
                max_total_length=(
                    None
                    if task_payload.get("max_total_length") is None
                    else float(task_payload["max_total_length"])
                ),
                max_search_states=int(task_payload.get("max_search_states", 50000)),
                progress_callback=on_progress,
                progress_interval=int(task_payload.get("progress_interval", 250)),
            )
    except (GraphSchemaError, RoutePlanningError, AutoRoutePlanningError) as exc:
        publish(
            "error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return
    except Exception as exc:  # pragma: no cover - defensive fallback
        publish(
            "error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return

    publish(
        "success",
        candidate_set=candidate_set.to_dict(),
    )


class _StdoutMessageQueue:
    def put(self, message: Mapping[str, Any]) -> None:
        sys.stdout.write(json.dumps(dict(message), ensure_ascii=False) + "\n")
        sys.stdout.flush()


class _FileMessageQueue:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_path = self.output_dir / "progress.jsonl"
        self.result_path = self.output_dir / "result.json"
        self.error_path = self.output_dir / "error.json"

    def put(self, message: Mapping[str, Any]) -> None:
        message = dict(message)
        message_type = message.get("type")
        if message_type == "progress":
            append_jsonl(self.progress_path, message)
            return
        target = self.result_path if message_type == "success" else self.error_path
        write_json_atomic(target, message, indent=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Background route candidate generation worker.")
    parser.add_argument("--payload", required=True, help="Path to JSON payload file")
    parser.add_argument("--output-dir", help="Optional output directory for file-based messaging")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    payload = read_json(args.payload)

    message_queue = (
        _FileMessageQueue(args.output_dir)
        if args.output_dir
        else _StdoutMessageQueue()
    )
    run_route_generation_task(payload, message_queue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
