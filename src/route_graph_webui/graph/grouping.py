from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .meta import (
    DEFAULT_BRIDGE_COLOR,
    DEFAULT_GROUP_COLOR,
    EDGE_GROUP_COLOR_META_KEY,
    EDGE_KIND_BRIDGE,
    EDGE_KIND_GROUP,
    EDGE_KIND_META_KEY,
    GRAPH_BRIDGE_STYLE_META_KEY,
    GRAPH_GROUP_CONFIGS_META_KEY,
    GROUP_CONFIG_LABEL_KEY,
    GROUP_CONFIG_TEXT_KEYS,
    NODE_SAMPLE_RADIUS_META_KEY,
)
from .model import GraphEdge, GraphNode, GraphSchemaError, RouteGraph, clone_node_lookup

@dataclass(slots=True)
class GraphColorGrouping:
    node_group_candidates: dict[str, set[str]]
    node_group_lookup: dict[str, str]
    conflicting_node_groups: dict[str, set[str]]
    ungrouped_node_ids: set[str]
    group_edge_ids: dict[str, set[str]]
    group_node_ids: dict[str, set[str]]
    bridge_edge_ids: set[str]
    edge_group_lookup: dict[str, str | None]
    edge_kind_lookup: dict[str, str]
    group_average_z_lookup: dict[str, float]


def normalize_hex_color(value: Any, *, field_name: str = "color") -> str:
    if not isinstance(value, str):
        raise GraphSchemaError(f"`{field_name}` must be a hex color string like `#RRGGBB`")
    text = value.strip()
    if not text:
        raise GraphSchemaError(f"`{field_name}` must not be empty")
    if not text.startswith("#"):
        text = f"#{text}"
    if len(text) != 7 or any(ch not in "0123456789abcdefABCDEF" for ch in text[1:]):
        raise GraphSchemaError(f"`{field_name}` must be a hex color string like `#RRGGBB`")
    return text.upper()


def get_edge_kind(edge: "GraphEdge") -> str:
    raw_value = edge.meta.get(EDGE_KIND_META_KEY)
    if raw_value == EDGE_KIND_BRIDGE:
        return EDGE_KIND_BRIDGE
    return EDGE_KIND_GROUP


def get_edge_group_color(
    edge: "GraphEdge",
    *,
    default_color: str = DEFAULT_GROUP_COLOR,
) -> str | None:
    if get_edge_kind(edge) != EDGE_KIND_GROUP:
        return None
    raw_value = edge.meta.get(EDGE_GROUP_COLOR_META_KEY)
    if raw_value is None:
        return normalize_hex_color(default_color, field_name="default_color")
    try:
        return normalize_hex_color(raw_value, field_name=f"GraphEdge `{edge.id}` field `{EDGE_GROUP_COLOR_META_KEY}`")
    except GraphSchemaError:
        return normalize_hex_color(default_color, field_name="default_color")


def read_graph_group_configs(meta: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    raw_configs = meta.get(GRAPH_GROUP_CONFIGS_META_KEY)
    if not isinstance(raw_configs, Mapping):
        return {}
    normalized: dict[str, dict[str, str]] = {}
    for raw_color, raw_payload in raw_configs.items():
        try:
            color = normalize_hex_color(raw_color, field_name="group color")
        except GraphSchemaError:
            continue
        if not isinstance(raw_payload, Mapping):
            continue
        cleaned: dict[str, str] = {}
        for key in (GROUP_CONFIG_LABEL_KEY, *GROUP_CONFIG_TEXT_KEYS):
            if key not in raw_payload:
                continue
            value = raw_payload.get(key)
            if value is None:
                cleaned[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = str(value)
        normalized[color] = cleaned
    return normalized


def write_graph_group_configs(meta: dict[str, Any], configs: Mapping[str, Mapping[str, Any]]) -> None:
    if not configs:
        meta.pop(GRAPH_GROUP_CONFIGS_META_KEY, None)
        return
    normalized: dict[str, dict[str, str]] = {}
    for raw_color, raw_payload in configs.items():
        color = normalize_hex_color(raw_color, field_name="group color")
        if not isinstance(raw_payload, Mapping):
            continue
        cleaned: dict[str, str] = {}
        for key in (GROUP_CONFIG_LABEL_KEY, *GROUP_CONFIG_TEXT_KEYS):
            if key not in raw_payload:
                continue
            value = raw_payload.get(key)
            if value is None:
                cleaned[key] = ""
            else:
                cleaned[key] = str(value)
        normalized[color] = cleaned
    if normalized:
        meta[GRAPH_GROUP_CONFIGS_META_KEY] = normalized
    else:
        meta.pop(GRAPH_GROUP_CONFIGS_META_KEY, None)


def read_graph_bridge_style(meta: Mapping[str, Any]) -> dict[str, str]:
    raw_style = meta.get(GRAPH_BRIDGE_STYLE_META_KEY)
    if not isinstance(raw_style, Mapping):
        return {}
    cleaned: dict[str, str] = {}
    raw_color = raw_style.get("color")
    if raw_color is None:
        return cleaned
    try:
        cleaned["color"] = normalize_hex_color(raw_color, field_name="bridge color")
    except GraphSchemaError:
        return {}
    return cleaned


def write_graph_bridge_style(meta: dict[str, Any], style: Mapping[str, Any]) -> None:
    raw_color = style.get("color")
    if raw_color is None or str(raw_color).strip() == "":
        meta.pop(GRAPH_BRIDGE_STYLE_META_KEY, None)
        return
    meta[GRAPH_BRIDGE_STYLE_META_KEY] = {
        "color": normalize_hex_color(raw_color, field_name="bridge color"),
    }


def resolve_bridge_color(meta: Mapping[str, Any], *, default_color: str = DEFAULT_BRIDGE_COLOR) -> str:
    style = read_graph_bridge_style(meta)
    if "color" in style:
        return style["color"]
    return normalize_hex_color(default_color, field_name="default bridge color")


def derive_graph_color_grouping(graph: "RouteGraph") -> GraphColorGrouping:
    node_group_candidates: dict[str, set[str]] = {node.id: set() for node in graph.nodes}
    group_edge_ids: dict[str, set[str]] = {}
    bridge_edge_ids: set[str] = set()
    edge_group_lookup: dict[str, str | None] = {}
    edge_kind_lookup: dict[str, str] = {}

    for edge in graph.edges:
        edge_kind = get_edge_kind(edge)
        edge_kind_lookup[edge.id] = edge_kind
        if edge_kind == EDGE_KIND_BRIDGE:
            bridge_edge_ids.add(edge.id)
            edge_group_lookup[edge.id] = None
            continue
        color = get_edge_group_color(edge)
        edge_group_lookup[edge.id] = color
        if color is None:
            continue
        group_edge_ids.setdefault(color, set()).add(edge.id)
        if edge.from_node in node_group_candidates:
            node_group_candidates[edge.from_node].add(color)
        if edge.to_node in node_group_candidates:
            node_group_candidates[edge.to_node].add(color)

    node_group_lookup: dict[str, str] = {}
    conflicting_node_groups: dict[str, set[str]] = {}
    ungrouped_node_ids: set[str] = set()
    group_node_ids: dict[str, set[str]] = {}

    for node in graph.nodes:
        colors = set(node_group_candidates.get(node.id, set()))
        if len(colors) == 1:
            color = next(iter(colors))
            node_group_lookup[node.id] = color
            group_node_ids.setdefault(color, set()).add(node.id)
        elif len(colors) > 1:
            conflicting_node_groups[node.id] = colors
        else:
            ungrouped_node_ids.add(node.id)

    group_average_z_lookup: dict[str, float] = {}
    for color, node_ids in group_node_ids.items():
        if not node_ids:
            continue
        group_average_z_lookup[color] = sum(
            float(graph.get_node(node_id).position[2]) for node_id in node_ids
        ) / len(node_ids)

    return GraphColorGrouping(
        node_group_candidates=node_group_candidates,
        node_group_lookup=node_group_lookup,
        conflicting_node_groups=conflicting_node_groups,
        ungrouped_node_ids=ungrouped_node_ids,
        group_edge_ids=group_edge_ids,
        group_node_ids=group_node_ids,
        bridge_edge_ids=bridge_edge_ids,
        edge_group_lookup=edge_group_lookup,
        edge_kind_lookup=edge_kind_lookup,
        group_average_z_lookup=group_average_z_lookup,
    )


def graph_uses_color_groups(graph: "RouteGraph") -> bool:
    if GRAPH_GROUP_CONFIGS_META_KEY in graph.meta or GRAPH_BRIDGE_STYLE_META_KEY in graph.meta:
        return True
    for edge in graph.edges:
        if EDGE_KIND_META_KEY in edge.meta or EDGE_GROUP_COLOR_META_KEY in edge.meta:
            return True
    return False


def compute_uniform_node_z(nodes: Mapping[str, "GraphNode"] | Iterable["GraphNode"]) -> float:
    if isinstance(nodes, Mapping):
        node_items = list(nodes.values())
    else:
        node_items = list(nodes)
    if not node_items:
        raise GraphSchemaError("Cannot compute uniform node z from an empty node collection")
    return sum(float(node.position[2]) for node in node_items) / len(node_items)


def build_uniform_z_node_lookup(
    node_lookup: Mapping[str, "GraphNode"],
) -> tuple[dict[str, "GraphNode"], float]:
    uniform_node_z = compute_uniform_node_z(node_lookup)
    normalized_lookup = clone_node_lookup(node_lookup)
    for node in normalized_lookup.values():
        node.position[2] = float(uniform_node_z)
    return normalized_lookup, float(uniform_node_z)


def get_node_sample_radius_override(node: "GraphNode") -> float | None:
    raw_value = node.meta.get(NODE_SAMPLE_RADIUS_META_KEY)
    if raw_value is None:
        return None
    try:
        radius = float(raw_value)
    except Exception as exc:
        raise GraphSchemaError(
            f"Graph node `{node.id}` has invalid `{NODE_SAMPLE_RADIUS_META_KEY}` override"
        ) from exc
    if radius < 0:
        raise GraphSchemaError(
            f"Graph node `{node.id}` has negative `{NODE_SAMPLE_RADIUS_META_KEY}` override"
        )
    return radius

__all__ = [
    "GraphColorGrouping",
    "build_uniform_z_node_lookup",
    "compute_uniform_node_z",
    "derive_graph_color_grouping",
    "get_edge_group_color",
    "get_edge_kind",
    "get_node_sample_radius_override",
    "graph_uses_color_groups",
    "normalize_hex_color",
    "read_graph_bridge_style",
    "read_graph_group_configs",
    "resolve_bridge_color",
    "write_graph_bridge_style",
    "write_graph_group_configs",
]
