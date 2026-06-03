from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

from route_graph_webui.storage.json_store import write_json_atomic

from .grouping import get_edge_kind, normalize_hex_color
from .io import load_graph, save_graph
from .meta import (
    EDGE_GROUP_COLOR_META_KEY,
    EDGE_KIND_BRIDGE,
    EDGE_KIND_GROUP,
    EDGE_KIND_META_KEY,
    NODE_SAMPLE_RADIUS_META_KEY,
)
from .model import GraphEdge, GraphNode, GraphSchemaError, RouteGraph, edge_planning_weight, edge_xy_weight
from .validation import validate_graph


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
            metrics={
                "length": float(weight),
                "cost": float(weight),
            },
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

        base_weight = edge_planning_weight(edge, self._node_map())
        first_weight = float(base_weight) * resolved_ratio
        second_weight = float(base_weight) - first_weight
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
            weight = edge_xy_weight(node_map[edge.from_node], node_map[edge.to_node])
            edge.weight = weight
            edge.metrics["length"] = weight
            edge.metrics["cost"] = weight
            edge.metrics_explicit = True
            edge.weight_explicit = True

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


__all__ = [
    "EDGE_INSERT_ENDPOINT_RATIO_EPSILON",
    "GraphEditor",
    "INSERTED_NODE_SOURCE_EDGE_ID_META_KEY",
    "INSERTED_NODE_SOURCE_EDGE_RATIO_META_KEY",
    "save_graph_allow_invalid",
]
