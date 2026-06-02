from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from graph_schema import (
        DEFAULT_BRIDGE_COLOR,
        DEFAULT_GROUP_COLOR,
        EDGE_KIND_BRIDGE,
        RouteGraph,
        candidate_to_plan,
        get_edge_group_color,
        get_edge_kind,
        load_candidate_set,
        load_graph,
        load_plan,
        physical_edge_key,
        resolve_bridge_color,
    )
else:
    from .graph_schema import (
        DEFAULT_BRIDGE_COLOR,
        DEFAULT_GROUP_COLOR,
        EDGE_KIND_BRIDGE,
        RouteGraph,
        candidate_to_plan,
        get_edge_group_color,
        get_edge_kind,
        load_candidate_set,
        load_graph,
        load_plan,
        physical_edge_key,
        resolve_bridge_color,
    )


@dataclass(frozen=True, slots=True)
class CanvasProjection:
    min_x: float
    min_y: float
    scale: float
    offset_x: float
    offset_y: float
    width: float
    height: float
    padding: float


@dataclass(frozen=True, slots=True)
class EdgePassLabelLayout:
    pass_index: int
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class CanvasViewState:
    rotation_quadrants: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False


def normalize_canvas_view_state(
    view_state: CanvasViewState | Mapping[str, Any] | None = None,
) -> CanvasViewState:
    def _coerce_bool(raw_value: Any) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, int) and raw_value in {0, 1}:
            return bool(raw_value)
        return False

    if isinstance(view_state, CanvasViewState):
        rotation_quadrants = int(view_state.rotation_quadrants)
        flip_horizontal = bool(view_state.flip_horizontal)
        flip_vertical = bool(view_state.flip_vertical)
    elif isinstance(view_state, Mapping):
        raw_rotation = view_state.get("rotation_quadrants", 0)
        try:
            rotation_quadrants = int(raw_rotation)
        except (TypeError, ValueError):
            rotation_quadrants = 0
        if isinstance(raw_rotation, bool):
            rotation_quadrants = 0
        flip_horizontal = _coerce_bool(view_state.get("flip_horizontal", False))
        flip_vertical = _coerce_bool(view_state.get("flip_vertical", False))
    else:
        rotation_quadrants = 0
        flip_horizontal = False
        flip_vertical = False
    return CanvasViewState(
        rotation_quadrants=rotation_quadrants % 4,
        flip_horizontal=flip_horizontal,
        flip_vertical=flip_vertical,
    )


def compute_canvas_view_center(positions: Iterable[Iterable[float]]) -> tuple[float, float]:
    points = [tuple(float(value) for value in position[:2]) for position in positions]
    if not points:
        return 0.0, 0.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _rotate_canvas_view_offset(dx: float, dy: float, rotation_quadrants: int) -> tuple[float, float]:
    normalized_rotation = int(rotation_quadrants) % 4
    if normalized_rotation == 0:
        return dx, dy
    if normalized_rotation == 1:
        return -dy, dx
    if normalized_rotation == 2:
        return -dx, -dy
    return dy, -dx


def transform_canvas_view_position(
    position: Iterable[float],
    *,
    center_xy: tuple[float, float],
    view_state: CanvasViewState | Mapping[str, Any] | None = None,
) -> tuple[float, float]:
    normalized_view = normalize_canvas_view_state(view_state)
    x = float(position[0])
    y = float(position[1])
    dx = x - float(center_xy[0])
    dy = y - float(center_xy[1])
    dx, dy = _rotate_canvas_view_offset(dx, dy, normalized_view.rotation_quadrants)
    if normalized_view.flip_horizontal:
        dx = -dx
    if normalized_view.flip_vertical:
        dy = -dy
    return float(center_xy[0]) + dx, float(center_xy[1]) + dy


def inverse_canvas_view_position(
    position: Iterable[float],
    *,
    center_xy: tuple[float, float],
    view_state: CanvasViewState | Mapping[str, Any] | None = None,
) -> tuple[float, float]:
    normalized_view = normalize_canvas_view_state(view_state)
    x = float(position[0])
    y = float(position[1])
    dx = x - float(center_xy[0])
    dy = y - float(center_xy[1])
    if normalized_view.flip_horizontal:
        dx = -dx
    if normalized_view.flip_vertical:
        dy = -dy
    dx, dy = _rotate_canvas_view_offset(dx, dy, -normalized_view.rotation_quadrants)
    return float(center_xy[0]) + dx, float(center_xy[1]) + dy


def build_canvas_projection(
    positions: Iterable[Iterable[float]],
    width: int,
    height: int,
    padding: int = 40,
) -> CanvasProjection:
    points = [tuple(float(value) for value in position[:2]) for position in positions]
    if not points:
        points = [(0.0, 0.0)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    usable_width = max(width - 2 * padding, 1)
    usable_height = max(height - 2 * padding, 1)
    scale = min(usable_width / span_x, usable_height / span_y)
    draw_width = span_x * scale
    draw_height = span_y * scale
    offset_x = (width - draw_width) / 2.0
    offset_y = (height - draw_height) / 2.0

    return CanvasProjection(
        min_x=min_x,
        min_y=min_y,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        width=float(width),
        height=float(height),
        padding=float(padding),
    )


def project_point(position: Iterable[float], projection: CanvasProjection) -> tuple[float, float]:
    x, y = float(position[0]), float(position[1])
    canvas_x = projection.offset_x + (x - projection.min_x) * projection.scale
    canvas_y = projection.height - (projection.offset_y + (y - projection.min_y) * projection.scale)
    return canvas_x, canvas_y


def unproject_point(x: float, y: float, projection: CanvasProjection) -> tuple[float, float]:
    world_x = ((x - projection.offset_x) / projection.scale) + projection.min_x
    world_y = (((projection.height - y) - projection.offset_y) / projection.scale) + projection.min_y
    return world_x, world_y


def _estimate_label_bounds(pass_index: int) -> tuple[float, float]:
    text = str(pass_index)
    return 10.0 + (7.0 * len(text)), 14.0


def _labels_overlap(
    ax: float,
    ay: float,
    aw: float,
    ah: float,
    bx: float,
    by: float,
    bw: float,
    bh: float,
    *,
    padding: float = 4.0,
) -> bool:
    return (
        abs(ax - bx) < ((aw + bw) / 2.0) + padding
        and abs(ay - by) < ((ah + bh) / 2.0) + padding
    )


def compute_edge_pass_label_layout(
    node_lookup: Mapping[str, Any],
    edge_passes: Iterable[Any],
    project_position: Callable[[Iterable[float]], tuple[float, float]],
) -> list[EdgePassLabelLayout]:
    edge_pass_list = list(edge_passes or [])
    if not edge_pass_list:
        return []

    edge_counts = Counter(
        physical_edge_key(edge_pass.from_node, edge_pass.to_node) for edge_pass in edge_pass_list
    )
    edge_seen: dict[tuple[str, str], int] = defaultdict(int)
    occupied: list[tuple[float, float, float, float]] = []
    layouts: list[EdgePassLabelLayout] = []
    tangent_offsets = (0.0, 18.0, -18.0, 32.0, -32.0, 46.0, -46.0, 60.0, -60.0)
    normal_offsets = (0.0, 12.0, -12.0, 24.0, -24.0, 36.0, -36.0)

    for edge_pass in edge_pass_list:
        from_node = node_lookup.get(edge_pass.from_node)
        to_node = node_lookup.get(edge_pass.to_node)
        if from_node is None or to_node is None:
            continue

        from_xy = project_position(from_node.position)
        to_xy = project_position(to_node.position)
        dx = float(to_xy[0]) - float(from_xy[0])
        dy = float(to_xy[1]) - float(from_xy[1])
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            tangent_x, tangent_y = 1.0, 0.0
            normal_x, normal_y = 0.0, -1.0
            midpoint_x, midpoint_y = float(from_xy[0]), float(from_xy[1])
            max_tangent_offset = 0.0
        else:
            tangent_x = dx / length
            tangent_y = dy / length
            normal_x = -tangent_y
            normal_y = tangent_x
            midpoint_x = (float(from_xy[0]) + float(to_xy[0])) / 2.0
            midpoint_y = (float(from_xy[1]) + float(to_xy[1])) / 2.0
            max_tangent_offset = max((length / 2.0) - 10.0, 0.0)

        edge_key = physical_edge_key(edge_pass.from_node, edge_pass.to_node)
        occurrence = edge_seen[edge_key]
        edge_seen[edge_key] += 1
        base_normal_offset = 14.0 * (occurrence - ((edge_counts[edge_key] - 1) / 2.0))

        label_width, label_height = _estimate_label_bounds(int(edge_pass.pass_index))
        best_layout: EdgePassLabelLayout | None = None
        best_score: tuple[int, float] | None = None

        for tangent_offset in tangent_offsets:
            clamped_tangent_offset = max(
                min(float(tangent_offset), max_tangent_offset),
                -max_tangent_offset,
            )
            for extra_normal_offset in normal_offsets:
                total_normal_offset = base_normal_offset + float(extra_normal_offset)
                candidate_x = (
                    midpoint_x
                    + (tangent_x * clamped_tangent_offset)
                    + (normal_x * total_normal_offset)
                )
                candidate_y = (
                    midpoint_y
                    + (tangent_y * clamped_tangent_offset)
                    + (normal_y * total_normal_offset)
                )
                collision_count = sum(
                    1
                    for occupied_x, occupied_y, occupied_w, occupied_h in occupied
                    if _labels_overlap(
                        candidate_x,
                        candidate_y,
                        label_width,
                        label_height,
                        occupied_x,
                        occupied_y,
                        occupied_w,
                        occupied_h,
                    )
                )
                score = (
                    collision_count,
                    abs(clamped_tangent_offset) + (0.35 * abs(extra_normal_offset)),
                )
                if best_layout is None or score < best_score:
                    best_layout = EdgePassLabelLayout(
                        pass_index=int(edge_pass.pass_index),
                        x=candidate_x,
                        y=candidate_y,
                    )
                    best_score = score
                if collision_count == 0:
                    break
            if best_score is not None and best_score[0] == 0:
                break

        if best_layout is None:
            continue
        occupied.append((best_layout.x, best_layout.y, label_width, label_height))
        layouts.append(best_layout)

    return layouts


def render_graph_preview(
    graph: RouteGraph,
    output_path: str | Path,
    *,
    plan: Any | None = None,
    mission_positions: list[dict[str, Any]] | None = None,
    width: int = 1400,
    height: int = 900,
    show_labels: bool = True,
    view_state: CanvasViewState | Mapping[str, Any] | None = None,
) -> Path:
    import matplotlib.pyplot as plt

    normalized_view_state = normalize_canvas_view_state(view_state)
    view_center = compute_canvas_view_center(node.position for node in graph.nodes)
    transformed_positions = [
        transform_canvas_view_position(
            node.position,
            center_xy=view_center,
            view_state=normalized_view_state,
        )
        for node in graph.nodes
    ]
    projection = build_canvas_projection(transformed_positions, width=width, height=height)
    node_map = graph.node_map

    def project_view_position(position: Iterable[float]) -> tuple[float, float]:
        transformed_position = transform_canvas_view_position(
            position,
            center_xy=view_center,
            view_state=normalized_view_state,
        )
        return project_point(transformed_position, projection)

    fig = plt.figure(figsize=(width / 100.0, height / 100.0), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.set_axis_off()

    for edge in graph.edges:
        from_node = node_map.get(edge.from_node)
        to_node = node_map.get(edge.to_node)
        if from_node is None or to_node is None:
            continue
        from_xy = project_view_position(from_node.position)
        to_xy = project_view_position(to_node.position)
        if get_edge_kind(edge) == EDGE_KIND_BRIDGE:
            color = resolve_bridge_color(graph.meta, default_color=DEFAULT_BRIDGE_COLOR)
        else:
            color = get_edge_group_color(edge, default_color=DEFAULT_GROUP_COLOR) or DEFAULT_GROUP_COLOR
        linestyle = "-" if edge.enabled else "--"
        linewidth = 2.0 if edge.enabled else 1.0
        ax.plot([from_xy[0], to_xy[0]], [from_xy[1], to_xy[1]], color=color, linestyle=linestyle, linewidth=linewidth)

    if plan and getattr(plan, "planned_nodes", None):
        planned_xy = [
            project_view_position(node_map[node_id].position)
            for node_id in plan.planned_nodes
            if node_id in node_map
        ]
        if len(planned_xy) >= 2:
            ax.plot(
                [point[0] for point in planned_xy],
                [point[1] for point in planned_xy],
                color="#d9480f",
                linewidth=3.5,
                solid_capstyle="round",
            )
        edge_passes = list(getattr(plan, "edge_passes", []) or [])
        if edge_passes:
            for label in compute_edge_pass_label_layout(
                node_map,
                edge_passes,
                project_view_position,
            ):
                ax.text(label.x, label.y, str(label.pass_index), fontsize=8, color="#1d4ed8")

    if mission_positions:
        polyline = [project_view_position(position["state"][0]) for position in mission_positions]
        ax.plot(
            [point[0] for point in polyline],
            [point[1] for point in polyline],
            color="#1d4ed8",
            linewidth=1.5,
            alpha=0.45,
        )

    for node in graph.nodes:
        x, y = project_view_position(node.position)
        ax.scatter([x], [y], c="#111827", s=28, zorder=5)
        if show_labels:
            ax.text(x + 6, y + 6, node.id, fontsize=8, color="#111827")

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=100)
    plt.close(fig)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a 2D preview for route_graph_webui graph JSON.")
    parser.add_argument("--graph", required=True, help="Path to route graph JSON")
    parser.add_argument("--plan", help="Optional route plan JSON to highlight")
    parser.add_argument("--candidate-set", help="Optional candidate-set JSON to highlight")
    parser.add_argument("--candidate-id", help="Candidate id when previewing from a candidate set")
    parser.add_argument("--output", required=True, help="Output PNG path")
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--no-labels", action="store_true", help="Hide node labels")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    graph = load_graph(args.graph)
    if args.plan and args.candidate_set:
        raise SystemExit("Use either `--plan` or `--candidate-set`, not both.")
    if args.candidate_set:
        candidate_set = load_candidate_set(args.candidate_set)
        plan = candidate_to_plan(candidate_set, args.candidate_id)
    else:
        plan = load_plan(args.plan) if args.plan else None
    output = render_graph_preview(
        graph,
        args.output,
        plan=plan,
        width=args.width,
        height=args.height,
        show_labels=not args.no_labels,
    )
    print(f"Saved preview to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
