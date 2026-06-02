from __future__ import annotations

import argparse

from route_graph_webui.graph.io import load_graph, save_candidate_set
from route_graph_webui.graph.model import GraphSchemaError
from route_graph_webui.planning.route_planner import (
    DEFAULT_MAX_EDGE_PASS_FACTOR,
    DEFAULT_MAX_ROUTES,
    RoutePlanningError,
    generate_route_candidates,
)
from route_graph_webui.shared.cli_args import add_graph_argument, add_output_argument


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


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
