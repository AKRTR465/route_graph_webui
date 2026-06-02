from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Iterable


if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from graph_schema import (
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GraphEdge,
        GraphNode,
        GraphSchemaError,
        NODE_SAMPLE_RADIUS_META_KEY,
        get_edge_kind,
        normalize_hex_color,
        RouteGraph,
        edge_xy_weight,
        load_graph,
        save_graph,
        validate_graph,
    )
    from json_store import write_json_atomic
else:
    from .graph_schema import (
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GraphEdge,
        GraphNode,
        GraphSchemaError,
        NODE_SAMPLE_RADIUS_META_KEY,
        get_edge_kind,
        normalize_hex_color,
        RouteGraph,
        edge_xy_weight,
        load_graph,
        save_graph,
        validate_graph,
    )
    from .json_store import write_json_atomic


EDGE_INSERT_ENDPOINT_RATIO_EPSILON = 1e-4
INSERTED_NODE_SOURCE_EDGE_ID_META_KEY = "inserted_from_edge_id"
INSERTED_NODE_SOURCE_EDGE_RATIO_META_KEY = "inserted_edge_ratio"


def _normalize_turn_delta_deg(delta_deg: float) -> float:
    while delta_deg > 180.0:
        delta_deg -= 360.0
    while delta_deg <= -180.0:
        delta_deg += 360.0
    return delta_deg


def _normalize_yaw_deg(yaw_deg: float) -> float:
    while yaw_deg > 180.0:
        yaw_deg -= 360.0
    while yaw_deg <= -180.0:
        yaw_deg += 360.0
    return yaw_deg


def _interpolate_yaw_hint(start_yaw: float | None, end_yaw: float | None, ratio: float) -> float | None:
    if start_yaw is None and end_yaw is None:
        return None
    if start_yaw is None:
        return float(end_yaw)
    if end_yaw is None:
        return float(start_yaw)
    delta = _normalize_turn_delta_deg(float(end_yaw) - float(start_yaw))
    return _normalize_yaw_deg(float(start_yaw) + (delta * float(ratio)))


def save_graph_allow_invalid(path: str | Path, graph: RouteGraph) -> Path:
    resolved = Path(path).resolve()
    return write_json_atomic(resolved, graph.to_dict(), indent=2)


class GraphEditor:
    def __init__(self, graph: RouteGraph) -> None:
        self.graph = graph

    @classmethod
    def from_path(cls, path: str | Path) -> "GraphEditor":
        return cls(load_graph(path))

    def _node_map(self) -> dict[str, Any]:
        return self.graph.node_map

    def _edge_map(self) -> dict[str, GraphEdge]:
        return self.graph.edge_map

    def _next_node_id(self) -> str:
        used = {node.id for node in self.graph.nodes}
        index = 1
        while True:
            candidate = f"N{index:03d}"
            if candidate not in used:
                return candidate
            index += 1

    def _next_edge_id(self) -> str:
        used = {edge.id for edge in self.graph.edges}
        index = 1
        while True:
            candidate = f"E{index:03d}"
            if candidate not in used:
                return candidate
            index += 1

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        edge_id: str | None = None,
        weight: float | None = None,
        *,
        enabled: bool = True,
        bidirectional: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> GraphEdge:
        node_map = self._node_map()
        if from_node not in node_map or to_node not in node_map:
            raise GraphSchemaError(f"Cannot add edge `{from_node}` -> `{to_node}`: node missing")
        if from_node == to_node:
            raise GraphSchemaError("Cannot add a self-loop edge")

        for existing in self.graph.edges:
            same_direction = existing.from_node == from_node and existing.to_node == to_node
            reverse_direction = existing.from_node == to_node and existing.to_node == from_node
            if same_direction or (bidirectional and reverse_direction) or (
                existing.bidirectional and reverse_direction
            ):
                raise GraphSchemaError(
                    f"Edge already exists for node pair `{from_node}` / `{to_node}` via `{existing.id}`"
                )

        if edge_id is None:
            edge_id = self._next_edge_id()
        elif edge_id in self._edge_map():
            raise GraphSchemaError(f"Edge id `{edge_id}` already exists")

        if weight is None:
            weight = edge_xy_weight(node_map[from_node], node_map[to_node])

        edge = GraphEdge(
            id=edge_id,
            from_node=from_node,
            to_node=to_node,
            weight=float(weight),
            enabled=enabled,
            bidirectional=bidirectional,
            meta=dict(meta or {}),
        )
        self.graph.edges.append(edge)
        return edge

    def remove_edge(self, edge_id: str) -> GraphEdge:
        for index, edge in enumerate(self.graph.edges):
            if edge.id == edge_id:
                return self.graph.edges.pop(index)
        raise GraphSchemaError(f"Edge `{edge_id}` does not exist")

    def remove_edge_between(self, node_a: str, node_b: str) -> GraphEdge:
        for index, edge in enumerate(self.graph.edges):
            if {edge.from_node, edge.to_node} == {node_a, node_b}:
                return self.graph.edges.pop(index)
        raise GraphSchemaError(f"No edge exists between `{node_a}` and `{node_b}`")

    def rename_node(self, node_id: str, new_name: str) -> None:
        node = self.graph.get_node(node_id)
        node.name = new_name.strip() or node.id

    def update_node_tags(self, node_id: str, tags: Iterable[str]) -> None:
        node = self.graph.get_node(node_id)
        node.tags = [str(tag).strip() for tag in tags if str(tag).strip()]

    def update_node_sample_radius(self, node_id: str, radius: float | None) -> None:
        node = self.graph.get_node(node_id)
        if radius is None:
            node.meta.pop(NODE_SAMPLE_RADIUS_META_KEY, None)
            return
        if float(radius) < 0:
            raise GraphSchemaError("Node sample radius override must be non-negative")
        node.meta[NODE_SAMPLE_RADIUS_META_KEY] = float(radius)

    def update_node_xy(self, node_id: str, x: float, y: float) -> None:
        node = self.graph.get_node(node_id)
        node.position[0] = float(x)
        node.position[1] = float(y)

    def insert_node_on_edge(self, edge_id: str, ratio: float) -> GraphNode:
        edge = self.graph.get_edge(edge_id)
        edge_kind = get_edge_kind(edge)
        if edge_kind != EDGE_KIND_GROUP:
            raise GraphSchemaError("Bridge edges do not support node insertion yet")

        resolved_ratio = float(ratio)
        if not math.isfinite(resolved_ratio):
            raise GraphSchemaError("Insertion ratio must be finite")
        if (
            resolved_ratio <= EDGE_INSERT_ENDPOINT_RATIO_EPSILON
            or resolved_ratio >= (1.0 - EDGE_INSERT_ENDPOINT_RATIO_EPSILON)
        ):
            raise GraphSchemaError(
                "Insertion ratio must stay strictly inside the edge and away from both endpoints"
            )

        from_node = self.graph.get_node(edge.from_node)
        to_node = self.graph.get_node(edge.to_node)
        node_id = self._next_node_id()
        inserted_node = GraphNode(
            id=node_id,
            name=node_id,
            position=[
                float(from_node.position[index])
                + ((float(to_node.position[index]) - float(from_node.position[index])) * resolved_ratio)
                for index in range(3)
            ],
            yaw_hint=_interpolate_yaw_hint(from_node.yaw_hint, to_node.yaw_hint, resolved_ratio),
            tags=[],
            meta={
                INSERTED_NODE_SOURCE_EDGE_ID_META_KEY: str(edge.id),
                INSERTED_NODE_SOURCE_EDGE_RATIO_META_KEY: float(resolved_ratio),
            },
        )
        self.graph.nodes.append(inserted_node)

        first_weight = float(edge.weight) * resolved_ratio
        second_weight = float(edge.weight) - first_weight
        first_meta = dict(edge.meta)
        second_meta = dict(edge.meta)
        self.add_edge(
            from_node.id,
            inserted_node.id,
            weight=first_weight,
            enabled=bool(edge.enabled),
            bidirectional=bool(edge.bidirectional),
            meta=first_meta,
        )
        self.add_edge(
            inserted_node.id,
            to_node.id,
            weight=second_weight,
            enabled=bool(edge.enabled),
            bidirectional=bool(edge.bidirectional),
            meta=second_meta,
        )
        self.remove_edge(edge_id)
        return inserted_node

    def delete_node(self, node_id: str) -> None:
        self.graph.get_node(node_id)
        self.graph.nodes = [node for node in self.graph.nodes if node.id != node_id]
        self.graph.edges = [
            edge for edge in self.graph.edges if edge.from_node != node_id and edge.to_node != node_id
        ]

    def recompute_weights(self, edge_ids: Iterable[str] | None = None) -> None:
        selected = set(edge_ids or [])
        node_map = self._node_map()
        for edge in self.graph.edges:
            if selected and edge.id not in selected:
                continue
            edge.weight = edge_xy_weight(node_map[edge.from_node], node_map[edge.to_node])

    def set_edge_enabled(self, edge_id: str, enabled: bool) -> None:
        self.graph.get_edge(edge_id).enabled = bool(enabled)

    def set_edge_group_color(self, edge_id: str, color: str) -> None:
        edge = self.graph.get_edge(edge_id)
        edge.meta[EDGE_KIND_META_KEY] = EDGE_KIND_GROUP
        edge.meta[EDGE_GROUP_COLOR_META_KEY] = normalize_hex_color(color, field_name="group color")

    def set_edge_bridge(self, edge_id: str) -> None:
        edge = self.graph.get_edge(edge_id)
        edge.meta[EDGE_KIND_META_KEY] = EDGE_KIND_BRIDGE
        edge.meta.pop(EDGE_GROUP_COLOR_META_KEY, None)

    def validate(self):
        return validate_graph(self.graph)

    def save(self, path: str | Path, *, allow_invalid: bool = False) -> Path:
        if allow_invalid:
            return save_graph_allow_invalid(path, self.graph)
        return save_graph(path, self.graph)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Edit and validate route_graph_webui graph JSON files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_edge = subparsers.add_parser("add-edge", help="Add a manual feasible edge")
    add_edge.add_argument("--graph", required=True)
    add_edge.add_argument("--from-node", required=True)
    add_edge.add_argument("--to-node", required=True)
    add_edge.add_argument("--edge-id")
    add_edge.add_argument("--weight", type=float)
    add_edge.add_argument("--one-way", action="store_true", help="Create a one-way edge")
    add_edge.add_argument("--disabled", action="store_true")
    add_edge.add_argument("--output")
    add_edge.add_argument("--allow-invalid", action="store_true")

    remove_edge = subparsers.add_parser("remove-edge", help="Remove an edge by id")
    remove_edge.add_argument("--graph", required=True)
    remove_edge.add_argument("--edge-id", required=True)
    remove_edge.add_argument("--output")
    remove_edge.add_argument("--allow-invalid", action="store_true")

    rename_node = subparsers.add_parser("rename-node", help="Rename a node")
    rename_node.add_argument("--graph", required=True)
    rename_node.add_argument("--node-id", required=True)
    rename_node.add_argument("--name", required=True)
    rename_node.add_argument("--output")
    rename_node.add_argument("--allow-invalid", action="store_true")

    set_tags = subparsers.add_parser("set-tags", help="Replace node tags")
    set_tags.add_argument("--graph", required=True)
    set_tags.add_argument("--node-id", required=True)
    set_tags.add_argument("--tags", nargs="*", default=[])
    set_tags.add_argument("--output")
    set_tags.add_argument("--allow-invalid", action="store_true")

    delete_node = subparsers.add_parser("delete-node", help="Delete a node and connected edges")
    delete_node.add_argument("--graph", required=True)
    delete_node.add_argument("--node-id", required=True)
    delete_node.add_argument("--output")
    delete_node.add_argument("--allow-invalid", action="store_true")

    recompute = subparsers.add_parser("recompute-weights", help="Recompute XY edge weights")
    recompute.add_argument("--graph", required=True)
    recompute.add_argument("--edge-id", nargs="*")
    recompute.add_argument("--output")
    recompute.add_argument("--allow-invalid", action="store_true")

    enable = subparsers.add_parser("enable-edge", help="Enable an edge")
    enable.add_argument("--graph", required=True)
    enable.add_argument("--edge-id", required=True)
    enable.add_argument("--output")
    enable.add_argument("--allow-invalid", action="store_true")

    disable = subparsers.add_parser("disable-edge", help="Disable an edge")
    disable.add_argument("--graph", required=True)
    disable.add_argument("--edge-id", required=True)
    disable.add_argument("--output")
    disable.add_argument("--allow-invalid", action="store_true")

    validate_cmd = subparsers.add_parser("validate", help="Validate graph structure")
    validate_cmd.add_argument("--graph", required=True)

    summary = subparsers.add_parser("summary", help="Print node/edge summary")
    summary.add_argument("--graph", required=True)
    return parser


def _save_and_report(
    editor: GraphEditor,
    output_path: str | Path,
    allow_invalid: bool,
    success_message: str | None = None,
) -> int:
    report = editor.validate()
    if not allow_invalid and not report.is_valid:
        raise GraphSchemaError(report.format_text())
    editor.save(output_path, allow_invalid=allow_invalid)
    if success_message:
        print(success_message)
    print(f"Saved graph to {Path(output_path).resolve()}")
    print(report.format_text())
    return 0 if report.is_valid else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        graph = load_graph(args.graph)
        report = validate_graph(graph)
        print(report.format_text())
        return 0 if report.is_valid else 1

    if args.command == "summary":
        graph = load_graph(args.graph)
        report = validate_graph(graph)
        enabled_edges = sum(1 for edge in graph.edges if edge.enabled)
        print(f"Graph: {graph.graph_name}")
        print(f"Environment: {graph.env_id}")
        print(f"Nodes: {len(graph.nodes)}")
        print(f"Edges: {len(graph.edges)} total / {enabled_edges} enabled")
        print(report.format_text())
        return 0 if report.is_valid else 1

    editor = GraphEditor.from_path(args.graph)
    output = args.output or args.graph
    allow_invalid = bool(getattr(args, "allow_invalid", False))

    try:
        if args.command == "add-edge":
            edge = editor.add_edge(
                args.from_node,
                args.to_node,
                edge_id=args.edge_id,
                weight=args.weight,
                enabled=not args.disabled,
                bidirectional=not args.one_way,
            )
            return _save_and_report(
                editor,
                output,
                allow_invalid,
                f"Added edge `{edge.id}`: {edge.from_node} -> {edge.to_node}",
            )

        if args.command == "remove-edge":
            edge = editor.remove_edge(args.edge_id)
            return _save_and_report(editor, output, allow_invalid, f"Removed edge `{edge.id}`")

        if args.command == "rename-node":
            editor.rename_node(args.node_id, args.name)
            return _save_and_report(editor, output, allow_invalid, f"Renamed node `{args.node_id}`")

        if args.command == "set-tags":
            editor.update_node_tags(args.node_id, args.tags)
            return _save_and_report(
                editor,
                output,
                allow_invalid,
                f"Updated tags for node `{args.node_id}`",
            )

        if args.command == "delete-node":
            editor.delete_node(args.node_id)
            return _save_and_report(
                editor,
                output,
                allow_invalid,
                f"Deleted node `{args.node_id}` and attached edges",
            )

        if args.command == "recompute-weights":
            editor.recompute_weights(args.edge_id)
            return _save_and_report(editor, output, allow_invalid, "Recomputed edge weights")

        if args.command == "enable-edge":
            editor.set_edge_enabled(args.edge_id, True)
            return _save_and_report(editor, output, allow_invalid, f"Enabled edge `{args.edge_id}`")

        if args.command == "disable-edge":
            editor.set_edge_enabled(args.edge_id, False)
            return _save_and_report(editor, output, allow_invalid, f"Disabled edge `{args.edge_id}`")
    except GraphSchemaError as exc:
        print(exc)
        return 1

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
