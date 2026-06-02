from __future__ import annotations

import argparse
import heapq
import math
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Any, Callable, Iterable


if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cli_args import add_graph_argument, add_output_argument
    from graph_schema import (
        NODE_Z_PREPROCESS_MODE,
        GraphColorGrouping,
        GraphSchemaError,
        RouteCandidate,
        RouteCandidateSet,
        RouteEdgePass,
        RoutePlan,
        RouteSegment,
        build_uniform_z_node_lookup,
        candidate_to_plan,
        derive_graph_color_grouping,
        ensure_valid_graph,
        ensure_valid_grouped_graph_for_routes,
        graph_uses_color_groups,
        load_graph,
        read_graph_bridge_style,
        read_graph_group_configs,
        save_candidate_set,
    )
    from webui_common import timestamp_now
else:
    from .graph_schema import (
        NODE_Z_PREPROCESS_MODE,
        GraphColorGrouping,
        GraphSchemaError,
        RouteCandidate,
        RouteCandidateSet,
        RouteEdgePass,
        RoutePlan,
        RouteSegment,
        build_uniform_z_node_lookup,
        candidate_to_plan,
        derive_graph_color_grouping,
        ensure_valid_graph,
        ensure_valid_grouped_graph_for_routes,
        graph_uses_color_groups,
        load_graph,
        read_graph_bridge_style,
        read_graph_group_configs,
        save_candidate_set,
    )
    from .webui_common import timestamp_now
    from .cli_args import add_graph_argument, add_output_argument


DEFAULT_MAX_ROUTES = 10
DEFAULT_MAX_EDGE_PASS_FACTOR = 2.5
DEFAULT_MAX_SEARCH_STATES = 50000
EPSILON = 1e-9


class RoutePlanningError(ValueError):
    """Raised when a route cannot be planned from the graph."""


@dataclass(frozen=True, slots=True)
class RoutePlanningProgress:
    phase: str
    expansions: int
    max_search_states: int
    candidates_found: int
    truncated: bool
    done: bool


@dataclass(slots=True)
class PathResult:
    node_ids: list[str]
    edge_signatures: list[tuple[str, str, str]]
    length: float

    def edge_pass_count(self) -> int:
        return len(self.edge_signatures)

    def signature(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(self.edge_signatures)


@dataclass(slots=True)
class WalkState:
    total_length: float
    current_node: str
    prev_node: str | None
    next_anchor_index: int
    node_ids: list[str]
    edge_signatures: list[tuple[str, str, str]]

    def edge_pass_count(self) -> int:
        return len(self.edge_signatures)


@dataclass(frozen=True, slots=True)
class CandidateSetGraphContext:
    node_map: dict[str, Any]
    normalized_node_lookup: dict[str, Any]
    export_meta: dict[str, Any]
    uses_color_groups: bool
    grouping: GraphColorGrouping | None


def prepare_candidate_set_graph_context(graph) -> CandidateSetGraphContext:
    ensure_valid_graph(graph)
    uses_color_groups = graph_uses_color_groups(graph)
    if uses_color_groups:
        ensure_valid_grouped_graph_for_routes(graph)

    node_map = graph.node_map
    normalized_node_lookup, uniform_node_z = build_uniform_z_node_lookup(node_map)
    export_meta: dict[str, Any] = {
        "node_z_preprocess_mode": NODE_Z_PREPROCESS_MODE,
        "uniform_node_z": round(float(uniform_node_z), 6),
        "graph_default_altitude": None
        if graph.default_altitude is None
        else round(float(graph.default_altitude), 6),
    }

    grouping = derive_graph_color_grouping(graph) if uses_color_groups else None
    if uses_color_groups and grouping is not None:
        export_meta.update(
            {
                "group_configs_v1": read_graph_group_configs(graph.meta),
                "bridge_style_v1": read_graph_bridge_style(graph.meta),
                "node_group_lookup_v1": {
                    node_id: color
                    for node_id, color in sorted(grouping.node_group_lookup.items())
                },
                "group_average_z_lookup_v1": {
                    color: round(float(avg_z), 6)
                    for color, avg_z in sorted(grouping.group_average_z_lookup.items())
                },
                "original_node_z_lookup_v1": {
                    node_id: round(float(node.position[2]), 6)
                    for node_id, node in sorted(node_map.items())
                },
            }
        )

    return CandidateSetGraphContext(
        node_map=node_map,
        normalized_node_lookup=normalized_node_lookup,
        export_meta=export_meta,
        uses_color_groups=uses_color_groups,
        grouping=grouping,
    )


_CandidateSetGraphContext = CandidateSetGraphContext
_prepare_candidate_set_graph_context = prepare_candidate_set_graph_context


def _build_adjacency(graph) -> dict[str, list[tuple[str, float, str]]]:
    adjacency: dict[str, list[tuple[str, float, str]]] = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        if not edge.enabled:
            continue
        adjacency.setdefault(edge.from_node, []).append((edge.to_node, float(edge.weight), edge.id))
        if edge.bidirectional:
            adjacency.setdefault(edge.to_node, []).append((edge.from_node, float(edge.weight), edge.id))
    for node_id in adjacency:
        adjacency[node_id].sort(key=lambda item: (item[1], item[0], item[2]))
    return adjacency


def _advance_anchor_index(current_node: str, anchors: list[str], next_anchor_index: int) -> int:
    updated_index = next_anchor_index
    while updated_index < len(anchors) and current_node == anchors[updated_index]:
        updated_index += 1
    return updated_index


def _dijkstra(graph, start: str, end: str) -> PathResult:
    node_map = graph.node_map
    if start not in node_map:
        raise RoutePlanningError(f"Start node `{start}` does not exist")
    if end not in node_map:
        raise RoutePlanningError(f"End node `{end}` does not exist")
    if start == end:
        return PathResult(node_ids=[start], edge_signatures=[], length=0.0)

    adjacency = _build_adjacency(graph)
    queue: list[tuple[float, int, str]] = [(0.0, 0, start)]
    distances = {start: 0.0}
    previous: dict[str, tuple[str, str]] = {}
    visited: set[str] = set()

    while queue:
        distance, edge_count, node_id = heapq.heappop(queue)
        if node_id in visited:
            continue
        visited.add(node_id)
        if node_id == end:
            break

        for neighbor, weight, edge_id in adjacency.get(node_id, []):
            if neighbor in visited:
                continue
            next_distance = distance + weight
            if next_distance + EPSILON < distances.get(neighbor, float("inf")):
                distances[neighbor] = next_distance
                previous[neighbor] = (node_id, edge_id)
                heapq.heappush(queue, (next_distance, edge_count + 1, neighbor))

    if end not in distances:
        raise RoutePlanningError(f"No enabled path exists from `{start}` to `{end}`")

    node_ids = [end]
    edge_signatures: list[tuple[str, str, str]] = []
    cursor = end
    while cursor != start:
        prev_node, edge_id = previous[cursor]
        edge_signatures.append((edge_id, prev_node, cursor))
        node_ids.append(prev_node)
        cursor = prev_node

    node_ids.reverse()
    edge_signatures.reverse()
    return PathResult(node_ids=node_ids, edge_signatures=edge_signatures, length=distances[end])


def compute_shortest_route(graph, anchors: Iterable[str]) -> PathResult:
    anchors = list(anchors)
    if not anchors:
        raise RoutePlanningError("At least one anchor node is required")
    planned_nodes: list[str] = []
    edge_signatures: list[tuple[str, str, str]] = []
    total_length = 0.0

    for anchor_start, anchor_end in zip(anchors, anchors[1:]):
        result = _dijkstra(graph, anchor_start, anchor_end)
        if planned_nodes:
            planned_nodes.extend(result.node_ids[1:])
        else:
            planned_nodes.extend(result.node_ids)
        edge_signatures.extend(result.edge_signatures)
        total_length += result.length

    if not planned_nodes:
        planned_nodes = [anchors[0]]
    return PathResult(node_ids=planned_nodes, edge_signatures=edge_signatures, length=total_length)


_compute_shortest_route = compute_shortest_route


def _edge_pass_count_limit(shortest_edge_pass_count: int, max_edge_pass_factor: float) -> int:
    if max_edge_pass_factor < 1.0:
        raise RoutePlanningError("`max_edge_pass_factor` must be at least 1.0")
    if shortest_edge_pass_count <= 0:
        return 0
    return max(shortest_edge_pass_count, int(math.ceil(shortest_edge_pass_count * max_edge_pass_factor)))


def _build_edge_passes_and_segments(
    graph,
    anchors: list[str],
    node_ids: list[str],
    edge_signatures: list[tuple[str, str, str]],
) -> tuple[list[RouteEdgePass], list[RouteSegment]]:
    edge_map = graph.edge_map
    segments: list[RouteSegment] = []
    edge_passes: list[RouteEdgePass] = []

    current_node = anchors[0]
    target_anchor_index = 1
    current_segment_start = anchors[0]
    current_segment_nodes = [current_node]
    current_segment_edge_passes: list[RouteEdgePass] = []
    current_segment_length = 0.0

    while target_anchor_index < len(anchors) and current_node == anchors[target_anchor_index]:
        segments.append(
            RouteSegment(
                start_anchor=current_segment_start,
                end_anchor=anchors[target_anchor_index],
                node_ids=[current_node],
                edge_ids=[],
                length=0.0,
                edge_passes=[],
                meta={"segment_index": len(segments)},
            )
        )
        current_segment_start = anchors[target_anchor_index]
        target_anchor_index += 1

    for index, (edge_id, from_node, to_node) in enumerate(edge_signatures):
        if from_node != node_ids[index] or to_node != node_ids[index + 1]:
            raise RoutePlanningError("Path node sequence and edge signatures are inconsistent")

        edge_pass = RouteEdgePass(
            pass_index=len(edge_passes) + 1,
            edge_id=edge_id,
            from_node=from_node,
            to_node=to_node,
            segment_index=len(segments),
            local_index=len(current_segment_edge_passes) + 1,
        )
        edge_passes.append(edge_pass)
        current_segment_edge_passes.append(edge_pass)
        current_segment_nodes.append(to_node)
        current_segment_length += float(edge_map[edge_id].weight)
        current_node = to_node

        while target_anchor_index < len(anchors) and current_node == anchors[target_anchor_index]:
            segments.append(
                RouteSegment(
                    start_anchor=current_segment_start,
                    end_anchor=anchors[target_anchor_index],
                    node_ids=list(current_segment_nodes),
                    edge_ids=[item.edge_id for item in current_segment_edge_passes],
                    length=current_segment_length,
                    edge_passes=list(current_segment_edge_passes),
                    meta={
                        "segment_index": len(segments),
                        "edge_pass_count": len(current_segment_edge_passes),
                    },
                )
            )
            current_segment_start = anchors[target_anchor_index]
            target_anchor_index += 1
            current_segment_nodes = [current_node]
            current_segment_edge_passes = []
            current_segment_length = 0.0

    if target_anchor_index != len(anchors):
        raise RoutePlanningError("Candidate path did not satisfy all anchor nodes in order")

    return edge_passes, segments


def _build_candidate(
    graph,
    anchors: list[str],
    path_result: PathResult,
    *,
    candidate_id: str,
    rank: int,
    selected: bool,
) -> RouteCandidate:
    edge_passes, segments = _build_edge_passes_and_segments(
        graph,
        anchors,
        path_result.node_ids,
        path_result.edge_signatures,
    )
    repeat_node_count = len(path_result.node_ids) - len(set(path_result.node_ids))
    return RouteCandidate(
        candidate_id=candidate_id,
        rank=rank,
        planned_nodes=list(path_result.node_ids),
        edge_passes=edge_passes,
        segments=segments,
        total_length=path_result.length,
        selected=selected,
        meta={
            "edge_pass_count": len(edge_passes),
            "repeat_node_count": repeat_node_count,
            "signature": [
                {"edge_id": edge_id, "from_node": from_node, "to_node": to_node}
                for edge_id, from_node, to_node in path_result.edge_signatures
            ],
        },
    )


def _enumerate_candidate_paths(
    graph,
    anchors: list[str],
    *,
    max_routes: int,
    max_edge_passes: int,
    max_search_states: int,
    seed_signature: tuple[tuple[str, str, str], ...],
    min_total_length: float | None = None,
    max_total_length: float | None = None,
    progress_callback: Callable[[RoutePlanningProgress], None] | None = None,
    progress_interval: int = 250,
) -> tuple[list[PathResult], bool]:
    if progress_interval < 1:
        raise RoutePlanningError("`progress_interval` must be at least 1")

    def report_progress(*, phase: str, done: bool, truncated_flag: bool) -> None:
        if progress_callback is None:
            return
        progress_callback(
            RoutePlanningProgress(
                phase=phase,
                expansions=expansions,
                max_search_states=max_search_states,
                candidates_found=1 + len(results),
                truncated=truncated_flag,
                done=done,
            )
        )

    adjacency = _build_adjacency(graph)
    seed_state = WalkState(
        total_length=0.0,
        current_node=anchors[0],
        prev_node=None,
        next_anchor_index=_advance_anchor_index(anchors[0], anchors, 1),
        node_ids=[anchors[0]],
        edge_signatures=[],
    )

    order = count()
    queue: list[tuple[float, int, int, WalkState]] = [
        (seed_state.total_length, seed_state.edge_pass_count(), next(order), seed_state)
    ]
    best_cost: dict[tuple[str, int, str | None, int], float] = {
        (seed_state.current_node, seed_state.next_anchor_index, seed_state.prev_node, 0): 0.0
    }
    results: list[PathResult] = []
    seen_signatures = {seed_signature}
    expansions = 0
    truncated = False

    report_progress(phase="searching", done=False, truncated_flag=False)

    while queue and len(results) < max_routes:
        _length, _edge_count, _ordinal, state = heapq.heappop(queue)
        if state.next_anchor_index == len(anchors) and state.current_node == anchors[-1]:
            signature = tuple(state.edge_signatures)
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                if min_total_length is None or state.total_length + EPSILON >= min_total_length:
                    results.append(
                        PathResult(
                            node_ids=list(state.node_ids),
                            edge_signatures=list(state.edge_signatures),
                            length=state.total_length,
                        )
                    )
            continue

        if expansions >= max_search_states:
            truncated = True
            break
        expansions += 1
        if expansions % progress_interval == 0:
            report_progress(phase="searching", done=False, truncated_flag=False)

        for neighbor, weight, edge_id in adjacency.get(state.current_node, []):
            if state.prev_node is not None and neighbor == state.prev_node:
                continue

            next_edge_count = state.edge_pass_count() + 1
            if next_edge_count > max_edge_passes:
                continue

            next_total_length = state.total_length + weight
            if max_total_length is not None and next_total_length > max_total_length + EPSILON:
                continue
            next_edge_signature = (edge_id, state.current_node, neighbor)
            next_node_ids = state.node_ids + [neighbor]
            next_edge_signatures = state.edge_signatures + [next_edge_signature]
            next_anchor_index = _advance_anchor_index(neighbor, anchors, state.next_anchor_index)

            if min_total_length is None:
                state_key = (neighbor, next_anchor_index, state.current_node, next_edge_count)
                best_known = best_cost.get(state_key)
                if best_known is not None and next_total_length > best_known + EPSILON:
                    continue
                if best_known is None or next_total_length + EPSILON < best_known:
                    best_cost[state_key] = next_total_length

            next_state = WalkState(
                total_length=next_total_length,
                current_node=neighbor,
                prev_node=state.current_node,
                next_anchor_index=next_anchor_index,
                node_ids=next_node_ids,
                edge_signatures=next_edge_signatures,
            )
            heapq.heappush(
                queue,
                (
                    next_state.total_length,
                    next_state.edge_pass_count(),
                    next(order),
                    next_state,
                ),
            )

    report_progress(
        phase="truncated" if truncated else "completed",
        done=True,
        truncated_flag=truncated,
    )

    return results, truncated


def generate_route_candidates(
    graph,
    start: str,
    end: str,
    via: Iterable[str] | None = None,
    *,
    max_routes: int = DEFAULT_MAX_ROUTES,
    max_edge_pass_factor: float = DEFAULT_MAX_EDGE_PASS_FACTOR,
    min_total_length: float | None = None,
    max_total_length: float | None = None,
    max_search_states: int = DEFAULT_MAX_SEARCH_STATES,
    progress_callback: Callable[[RoutePlanningProgress], None] | None = None,
    progress_interval: int = 250,
) -> RouteCandidateSet:
    if max_routes < 1:
        raise RoutePlanningError("`max_routes` must be at least 1")
    if max_search_states < 1:
        raise RoutePlanningError("`max_search_states` must be at least 1")
    if min_total_length is not None and min_total_length <= 0:
        raise RoutePlanningError("`min_total_length` must be positive")
    if max_total_length is not None and max_total_length <= 0:
        raise RoutePlanningError("`max_total_length` must be positive")
    if (
        min_total_length is not None
        and max_total_length is not None
        and min_total_length > max_total_length
    ):
        raise RoutePlanningError("`min_total_length` must be less than or equal to `max_total_length`")
    if not graph.nodes:
        raise RoutePlanningError("Route graph is empty")
    graph_context = prepare_candidate_set_graph_context(graph)

    anchors = [start, *(via or []), end]
    node_map = graph_context.node_map
    grouping = graph_context.grouping
    for anchor in anchors:
        if anchor not in node_map:
            raise RoutePlanningError(f"Anchor node `{anchor}` does not exist")
        if (
            graph_context.uses_color_groups
            and grouping is not None
            and anchor not in grouping.node_group_lookup
        ):
            raise RoutePlanningError(
                f"Anchor node `{anchor}` does not belong to exactly one color group"
            )

    shortest_path = compute_shortest_route(graph, anchors)
    if max_total_length is not None and shortest_path.length > max_total_length + EPSILON:
        raise RoutePlanningError(
            "`max_total_length` is smaller than the shortest feasible route length"
        )
    if min_total_length is not None and shortest_path.length + EPSILON >= min_total_length:
        min_total_length = None
    shortest_edge_pass_count = shortest_path.edge_pass_count()
    max_edge_passes = _edge_pass_count_limit(shortest_edge_pass_count, max_edge_pass_factor)
    normalized_node_lookup, uniform_node_z = build_uniform_z_node_lookup(node_map)

    enumerated_paths, truncated = _enumerate_candidate_paths(
        graph,
        anchors,
        max_routes=max_routes,
        max_edge_passes=max_edge_passes,
        max_search_states=max_search_states,
        seed_signature=shortest_path.signature(),
        min_total_length=min_total_length,
        max_total_length=max_total_length,
        progress_callback=progress_callback,
        progress_interval=progress_interval,
    )

    path_results = [shortest_path, *enumerated_paths]
    if min_total_length is not None:
        path_results = [path for path in path_results if path.length + EPSILON >= min_total_length]
    path_results.sort(
        key=lambda item: (
            item.length,
            item.edge_pass_count(),
            item.signature(),
        )
    )

    candidates: list[RouteCandidate] = []
    for index, path_result in enumerate(path_results[:max_routes], start=1):
        candidate = _build_candidate(
            graph,
            anchors,
            path_result,
            candidate_id=f"C{index:03d}",
            rank=index,
            selected=index == 1,
        )
        candidates.append(candidate)

    if not candidates:
        raise RoutePlanningError(f"No candidate route exists for anchors {' -> '.join(anchors)}")

    candidate_meta = {
        **graph_context.export_meta,
        "created_at": timestamp_now(),
        "planner": "route_graph_webui.route_planner",
        "max_routes": int(max_routes),
        "max_edge_pass_factor": float(max_edge_pass_factor),
        "min_total_length": None if min_total_length is None else round(float(min_total_length), 6),
        "max_total_length": None if max_total_length is None else round(float(max_total_length), 6),
        "max_edge_passes": int(max_edge_passes),
        "max_search_states": int(max_search_states),
        "shortest_total_length": round(float(shortest_path.length), 6),
        "shortest_edge_pass_count": int(shortest_edge_pass_count),
        "candidate_count": len(candidates),
        "truncated": bool(truncated),
    }

    return RouteCandidateSet(
        env_id=graph.env_id,
        graph_name=graph.graph_name,
        anchor_nodes=anchors,
        candidates=candidates,
        node_lookup=graph_context.normalized_node_lookup,
        selected_candidate_ids=[candidates[0].candidate_id],
        meta=candidate_meta,
    )


def plan_route(
    graph,
    start: str,
    end: str,
    via: Iterable[str] | None = None,
    *,
    max_edge_pass_factor: float = DEFAULT_MAX_EDGE_PASS_FACTOR,
    min_total_length: float | None = None,
    max_total_length: float | None = None,
    max_search_states: int = DEFAULT_MAX_SEARCH_STATES,
) -> RoutePlan:
    candidate_set = generate_route_candidates(
        graph,
        start=start,
        via=via,
        end=end,
        max_routes=1,
        max_edge_pass_factor=max_edge_pass_factor,
        min_total_length=min_total_length,
        max_total_length=max_total_length,
        max_search_states=max_search_states,
    )
    return candidate_to_plan(candidate_set, candidate_set.candidates[0].candidate_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate route candidate sets on route_graph_webui graph JSON.")
    add_graph_argument(parser, required=True, help="Path to route graph JSON")
    parser.add_argument("--start", required=True, help="Start node id")
    parser.add_argument("--via", nargs="*", default=[], help="Optional via node ids")
    parser.add_argument("--end", required=True, help="End node id")
    parser.add_argument("--max-routes", type=int, default=DEFAULT_MAX_ROUTES)
    parser.add_argument("--max-edge-pass-factor", type=float, default=DEFAULT_MAX_EDGE_PASS_FACTOR)
    parser.add_argument("--min-total-length", type=float, default=None)
    parser.add_argument("--max-total-length", type=float, default=None)
    add_output_argument(parser, required=True, help="Output route candidate-set JSON path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        graph = load_graph(args.graph)
        candidate_set = generate_route_candidates(
            graph,
            start=args.start,
            via=args.via,
            end=args.end,
            max_routes=args.max_routes,
            max_edge_pass_factor=args.max_edge_pass_factor,
            min_total_length=args.min_total_length,
            max_total_length=args.max_total_length,
        )
        save_path = save_candidate_set(args.output, candidate_set)
    except (GraphSchemaError, RoutePlanningError) as exc:
        print(exc)
        return 1

    print(f"Saved route candidate set to {save_path}")
    print(f"Candidates: {len(candidate_set.candidates)}")
    for candidate in candidate_set.candidates:
        print(
            f"  {candidate.candidate_id}: length={candidate.total_length:.3f}, "
            f"edge_passes={candidate.edge_pass_count()}, repeats={candidate.repeat_node_count()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
