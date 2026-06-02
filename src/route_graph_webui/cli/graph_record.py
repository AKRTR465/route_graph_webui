from __future__ import annotations

import argparse
import time
from pathlib import Path

from route_graph_webui.graph.io import load_graph, save_graph
from route_graph_webui.graph.model import GraphNode, RouteGraph
from route_graph_webui.runtime_support.runtime import (
    DEFAULT_RESET_LOCATION,
    DEFAULT_RESET_ROTATION,
    KeyboardController,
    RuntimeArgs,
    build_route_graph_env,
    close_env,
    get_current_pose,
    normalize_supported_env,
    resolve_data_path,
    set_default_pose,
    step_runtime,
    timestamp_now,
)


def _next_node_id(graph: RouteGraph) -> str:
    used = {node.id for node in graph.nodes}
    index = 1
    while True:
        candidate = f"N{index:03d}"
        if candidate not in used:
            return candidate
        index += 1


def _load_or_create_graph(output_path: Path, args: argparse.Namespace) -> RouteGraph:
    requested_env_id = getattr(args, "normalized_env_id", args.env_id)
    if output_path.exists():
        graph = load_graph(output_path)
        if graph.env_id != requested_env_id:
            raise ValueError(
                f"Existing graph env_id `{graph.env_id}` does not match requested `{requested_env_id}`"
            )
        return graph

    graph_name = args.graph_name or output_path.stem
    return RouteGraph(
        env_id=requested_env_id,
        graph_name=graph_name,
        default_altitude=args.default_altitude,
        nodes=[],
        edges=[],
        meta={
            "created_at": timestamp_now(),
            "creator": "route_graph_webui.graph_record",
        },
    )


def _save_graph_snapshot(output_path: Path, graph: RouteGraph, reason: str) -> bool:
    try:
        save_graph(output_path, graph)
    except Exception as exc:
        print(f"[save] failed during {reason}: {exc}")
        return False
    print(f"[save] graph written to {output_path} ({reason})")
    return True


def _default_output_filename(args: argparse.Namespace) -> str:
    graph_name = (args.graph_name or "").strip()
    if graph_name:
        stem = graph_name
    else:
        env_name = getattr(args, "normalized_env_name", None) or str(args.env_id)
        stem = env_name
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in stem)
    safe_stem = safe_stem.strip("._") or "route_graph_webui"
    return f"{safe_stem}.json"


def _resolve_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output).resolve()
    return resolve_data_path("graphs", _default_output_filename(args))


def _consume_speed_adjustments(
    controller: KeyboardController,
    *,
    move_step: float,
    yaw_step: float,
    minimum_speed: float = 0.1,
) -> list[str]:
    updates: list[str] = []

    if controller.consume("1"):
        controller.move_speed = round(max(float(minimum_speed), controller.move_speed - float(move_step)), 3)
        updates.append(f"[-] Move Speed: {controller.move_speed:g}")

    if controller.consume("2"):
        controller.move_speed = round(controller.move_speed + float(move_step), 3)
        updates.append(f"[+] Move Speed: {controller.move_speed:g}")

    if controller.consume("3"):
        controller.yaw_speed = round(max(float(minimum_speed), controller.yaw_speed - float(yaw_step)), 3)
        updates.append(f"[-] Yaw Speed: {controller.yaw_speed:g}")

    if controller.consume("4"):
        controller.yaw_speed = round(controller.yaw_speed + float(yaw_step), 3)
        updates.append(f"[+] Yaw Speed: {controller.yaw_speed:g}")

    return updates


def _resolve_runtime_args(args: argparse.Namespace) -> RuntimeArgs:
    runtime_args = RuntimeArgs.from_source(args)
    location_offset = tuple(float(value) for value in args.reset_location)
    runtime_args.reset_location = tuple(
        float(base) + float(offset)
        for base, offset in zip(DEFAULT_RESET_LOCATION, location_offset)
    )
    return runtime_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record graph nodes from a live UAV-MeM scene.")
    parser.add_argument("--env-id", required=True, help="Gym env_id or env_name")
    parser.add_argument(
        "--output",
        help="Output graph JSON path. Defaults to data/graphs/<graph-name-or-env>.json",
    )
    parser.add_argument("--graph-name", help="Optional graph name for new files")
    parser.add_argument("--default-altitude", type=float, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--time-dilation", type=int, default=10)
    parser.add_argument("--early-done", type=int, default=-1)
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument(
        "--reset-location",
        type=float,
        nargs=3,
        metavar=("DX", "DY", "DZ"),
        default=(0.0, 0.0, 0.0),
        help=(
            "Offset from default reset location in Unreal units. "
            "Final reset location is DEFAULT_RESET_LOCATION + offset. Default: %(default)s"
        ),
    )
    parser.add_argument(
        "--reset-rotation",
        type=float,
        nargs=3,
        metavar=("ROLL", "YAW", "PITCH"),
        default=DEFAULT_RESET_ROTATION,
        help="Initial/reset drone rotation in degrees. Default: %(default)s",
    )
    parser.add_argument(
        "--disable-physics",
        dest="enable_physics",
        action="store_false",
        help="Disable UAV physics simulation (default keeps physics enabled).",
    )
    parser.add_argument("--move-speed", type=float, default=3.0)
    parser.add_argument("--yaw-speed", type=float, default=5.0)
    parser.add_argument("--speed-step", type=float, default=0.1, help="Move-speed increment for keys `1/2`")
    parser.add_argument("--yaw-step", type=float, default=0.1, help="Yaw-speed increment for keys `3/4`")
    parser.add_argument(
        "--status-interval",
        type=float,
        default=0.0,
        help="Periodic status log interval in seconds. Set > 0 to enable; default is disabled.",
    )
    parser.add_argument(
        "--manual-save-only",
        action="store_true",
        help="Disable default autosave after node add/remove and keep manual `S` saves only.",
    )
    parser.add_argument("--tag", nargs="*", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.normalized_env_name, args.normalized_env_id = normalize_supported_env(args.env_id)

    output_path = _resolve_output_path(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph = _load_or_create_graph(output_path, args)
    runtime_args = _resolve_runtime_args(args)

    runtime = None
    controller = KeyboardController(
        tracked_keys=("p", "[", "s", "q", "o", "1", "2", "3", "4"),
        move_speed=args.move_speed,
        yaw_speed=args.yaw_speed,
    )
    autosave_enabled = not args.manual_save_only

    print("=== route_graph_webui graph recorder ===")
    print("Flight: [T/G] forward/backward [F/H] left/right [I/K] up/down [J/L] yaw")
    print(
        "Speed : [1/2] decel/accel move  [3/4] decel/accel yaw"
    )
    print(
        "Ops   : [P] save node + autosave  [ [] delete last node + autosave  "
        "[S] force save  [O] reset pose  [Q] quit"
    )
    print(f"Output: {output_path}")
    print(f"Initial Speeds: move={controller.move_speed:g} yaw={controller.yaw_speed:g}")

    dirty = False
    last_status = 0.0
    last_node_id = "none"

    try:
        runtime = build_route_graph_env(args.normalized_env_id, runtime_args)
        controller.start()
        while True:
            for message in _consume_speed_adjustments(
                controller,
                move_step=args.speed_step,
                yaw_step=args.yaw_step,
            ):
                print(message)

            step_runtime(runtime, controller.flight_action())

            if controller.consume("o"):
                set_default_pose(
                    runtime,
                    location=runtime_args.reset_location,
                    rotation=runtime_args.reset_rotation,
                    enable_physics=runtime_args.enable_physics,
                )
                print("[reset] restored configured reset pose")

            if controller.consume("p"):
                position, rotation = get_current_pose(runtime)
                node = GraphNode(
                    id=_next_node_id(graph),
                    name="",
                    position=[round(float(value), 6) for value in position],
                    yaw_hint=round(float(rotation[1]), 6) if len(rotation) > 1 else None,
                    tags=[str(tag) for tag in args.tag],
                    meta={"captured_at": timestamp_now()},
                )
                if not node.name:
                    node.name = node.id
                graph.nodes.append(node)
                dirty = True
                last_node_id = node.id
                print(f"[node] captured {node.id} @ {node.position}")
                if autosave_enabled and _save_graph_snapshot(output_path, graph, f"node capture {node.id}"):
                    dirty = False

            if controller.consume("["):
                if graph.nodes:
                    removed = graph.nodes.pop()
                    graph.edges = [
                        edge
                        for edge in graph.edges
                        if edge.from_node != removed.id and edge.to_node != removed.id
                    ]
                    dirty = True
                    last_node_id = removed.id
                    print(f"[node] removed {removed.id}")
                    if autosave_enabled and _save_graph_snapshot(output_path, graph, f"node removal {removed.id}"):
                        dirty = False
                else:
                    print("[node] nothing to remove")

            if controller.consume("s"):
                if _save_graph_snapshot(output_path, graph, "manual save"):
                    dirty = False

            if controller.consume("q"):
                break

            now = time.time()
            if float(args.status_interval) > 0 and now - last_status >= float(args.status_interval):
                location, rotation = get_current_pose(runtime)
                yaw = rotation[1] if len(rotation) > 1 else 0.0
                print(
                    f"[status] xyz=({location[0]:.2f}, {location[1]:.2f}, {location[2]:.2f}) "
                    f"yaw={yaw:.2f} nodes={len(graph.nodes)} last={last_node_id}"
                )
                last_status = now

            time.sleep(0.05)
    finally:
        controller.stop()
        if runtime is not None:
            if dirty:
                _save_graph_snapshot(output_path, graph, "exit")
            close_env(runtime)

    print(f"[exit] final graph contains {len(graph.nodes)} nodes and {len(graph.edges)} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
