from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from graph_schema import (
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GraphSchemaError,
        RouteGraph,
        derive_graph_color_grouping,
        normalize_hex_color,
    )
else:
    from .graph_schema import (
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GraphSchemaError,
        RouteGraph,
        derive_graph_color_grouping,
        normalize_hex_color,
    )


@dataclass(frozen=True, slots=True)
class EdgeCreationIntent:
    edge_kind: str
    group_color: str | None = None

    def to_edge_meta(self) -> dict[str, Any]:
        if self.edge_kind == EDGE_KIND_BRIDGE:
            return {EDGE_KIND_META_KEY: EDGE_KIND_BRIDGE}
        if not self.group_color:
            raise GraphSchemaError("组内边需要提供颜色组颜色")
        return {
            EDGE_KIND_META_KEY: EDGE_KIND_GROUP,
            EDGE_GROUP_COLOR_META_KEY: self.group_color,
        }


def _resolve_group_color(raw_color: str | None, fallback_color: str | None) -> str | None:
    color = raw_color if raw_color is not None and str(raw_color).strip() else fallback_color
    if color is None or not str(color).strip():
        return None
    return normalize_hex_color(color, field_name="group color")


def resolve_edge_creation_intent(
    graph: RouteGraph,
    *,
    from_node: str,
    to_node: str,
    edge_kind: str | None = None,
    group_color: str | None = None,
    fallback_group_color: str | None = None,
) -> EdgeCreationIntent:
    node_map = graph.node_map
    if from_node not in node_map or to_node not in node_map:
        raise GraphSchemaError(f"Cannot add edge `{from_node}` -> `{to_node}`: node missing")
    if from_node == to_node:
        raise GraphSchemaError("Cannot add a self-loop edge")

    if edge_kind == EDGE_KIND_BRIDGE:
        return EdgeCreationIntent(edge_kind=EDGE_KIND_BRIDGE)
    if edge_kind == EDGE_KIND_GROUP:
        selected_color = _resolve_group_color(group_color, fallback_group_color)
        if selected_color is None:
            raise GraphSchemaError("组内边需要提供颜色组颜色")
        return EdgeCreationIntent(edge_kind=EDGE_KIND_GROUP, group_color=selected_color)

    grouping = derive_graph_color_grouping(graph)
    if from_node in grouping.conflicting_node_groups or to_node in grouping.conflicting_node_groups:
        raise GraphSchemaError("存在归属多个颜色组的节点，请先调整相关边为桥接边。")

    group_a = grouping.node_group_lookup.get(from_node)
    group_b = grouping.node_group_lookup.get(to_node)
    if group_a and group_b:
        if group_a == group_b:
            return EdgeCreationIntent(edge_kind=EDGE_KIND_GROUP, group_color=group_a)
        return EdgeCreationIntent(edge_kind=EDGE_KIND_BRIDGE)
    if group_a or group_b:
        return EdgeCreationIntent(edge_kind=EDGE_KIND_GROUP, group_color=group_a or group_b)

    selected_color = _resolve_group_color(group_color, fallback_group_color)
    if selected_color is None:
        raise GraphSchemaError("两个节点都尚未归组，请先从调色盘选择一个颜色。")
    return EdgeCreationIntent(edge_kind=EDGE_KIND_GROUP, group_color=selected_color)


def resolve_edge_creation_meta(
    graph: RouteGraph,
    *,
    from_node: str,
    to_node: str,
    edge_kind: str | None = None,
    group_color: str | None = None,
    fallback_group_color: str | None = None,
) -> dict[str, Any]:
    return resolve_edge_creation_intent(
        graph,
        from_node=from_node,
        to_node=to_node,
        edge_kind=edge_kind,
        group_color=group_color,
        fallback_group_color=fallback_group_color,
    ).to_edge_meta()


__all__ = [
    "EdgeCreationIntent",
    "resolve_edge_creation_intent",
    "resolve_edge_creation_meta",
]
