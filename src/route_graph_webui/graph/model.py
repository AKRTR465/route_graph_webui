from __future__ import annotations

import math
from collections.abc import Iterable as IterableABC
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .versioning import (
    CURRENT_GRAPH_FORMAT,
    CURRENT_GRAPH_FORMAT_VERSION,
    CURRENT_EVALUATION_VERSION,
    resolve_evaluation_version,
)

UAV_EXTENSION_KEY = "uav"
WEBUI_EXTENSION_KEY = "route_graph_webui"
DEFAULT_COORDINATE_SYSTEM = {
    "type": "cartesian",
    "axes": ["x", "y", "z"],
    "unit": "cm",
}


class GraphSchemaError(ValueError):
    """Raised when graph or plan data is invalid."""


@dataclass(slots=True)
class GraphValidationIssue:
    severity: str
    code: str
    message: str
    refs: list[str] = field(default_factory=list)

    def format_line(self) -> str:
        refs = f" ({', '.join(self.refs)})" if self.refs else ""
        return f"[{self.severity}] {self.code}: {self.message}{refs}"


@dataclass(slots=True)
class GraphValidationReport:
    issues: list[GraphValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[GraphValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[GraphValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        refs: Iterable[str] | None = None,
    ) -> None:
        self.issues.append(
            GraphValidationIssue(
                severity=severity,
                code=code,
                message=message,
                refs=list(refs or []),
            )
        )

    def format_text(self) -> str:
        if not self.issues:
            return "No validation issues found."
        return "\n".join(issue.format_line() for issue in self.issues)


def _as_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphSchemaError(f"`{field_name}` must be a non-empty string")
    return value


def _as_finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise GraphSchemaError(f"`{field_name}` must be a finite number")
    try:
        numeric_value = float(value)
    except Exception as exc:
        raise GraphSchemaError(f"`{field_name}` must be a finite number") from exc
    if not math.isfinite(numeric_value):
        raise GraphSchemaError(f"`{field_name}` must be a finite number")
    return numeric_value


def _as_float_list(value: Iterable[Any], expected_length: int, field_name: str) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, IterableABC):
        raise GraphSchemaError(f"`{field_name}` must be a list of numbers")
    values = [
        _as_finite_float(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    ]
    if len(values) != expected_length:
        raise GraphSchemaError(
            f"`{field_name}` must contain exactly {expected_length} numeric values"
        )
    return values


def _ensure_str_list(value: Iterable[Any] | None) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in value]


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise GraphSchemaError(
        f"`{field_name}` must be a boolean, 'true'/'false', or 1/0"
    )


def _as_strict_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise GraphSchemaError(f"`{field_name}` must be a boolean")


def _ensure_mapping(value: Any, field_name: str, *, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return dict(default or {})
    if not isinstance(value, Mapping):
        raise GraphSchemaError(f"`{field_name}` must be an object")
    return dict(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _read_extension(raw: Mapping[str, Any], namespace: str) -> dict[str, Any]:
    extensions = _ensure_mapping(raw.get("extensions"), "extensions")
    return _ensure_mapping(extensions.get(namespace), f"extensions.{namespace}")


def _merge_extension(extensions: Mapping[str, Any], namespace: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(extensions)
    current = _ensure_mapping(merged.get(namespace), f"extensions.{namespace}")
    current.update(dict(payload))
    if current:
        merged[namespace] = current
    else:
        merged.pop(namespace, None)
    return merged


def _clean_empty_objects(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value != {}}


def _round_float(value: float) -> float:
    return round(float(value), 6)


def _as_metrics(value: Any, field_name: str = "metrics") -> dict[str, float]:
    raw_metrics = _ensure_mapping(value, field_name)
    metrics: dict[str, float] = {}
    for key, raw_value in raw_metrics.items():
        metrics[str(key)] = _as_finite_float(raw_value, f"{field_name}.{key}")
    return metrics


def clone_graph_node(node: "GraphNode") -> "GraphNode":
    return GraphNode(
        id=str(node.id),
        name=str(node.name),
        position=[float(value) for value in node.position],
        yaw_hint=None if node.yaw_hint is None else float(node.yaw_hint),
        tags=list(node.tags),
        meta=dict(node.meta),
        extensions=dict(node.extensions),
    )


def clone_node_lookup(node_lookup: Mapping[str, "GraphNode"]) -> dict[str, "GraphNode"]:
    return {
        str(node_id): clone_graph_node(node)
        for node_id, node in node_lookup.items()
    }

@dataclass(slots=True)
class GraphNode:
    id: str
    name: str
    position: list[float]
    yaw_hint: float | None = None
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GraphNode":
        try:
            node_id = _as_non_empty_str(raw["id"], "GraphNode `id`")
        except KeyError as exc:
            raise GraphSchemaError("GraphNode is missing required field `id`") from exc
        raw_label = raw.get("label")
        name = raw_label if isinstance(raw_label, str) and raw_label.strip() else node_id
        position = _as_float_list(raw.get("position", []), 3, "position")
        properties = _ensure_mapping(raw.get("properties"), f"GraphNode `{node_id}` field `properties`")
        extensions = _ensure_mapping(raw.get("extensions"), f"GraphNode `{node_id}` field `extensions`")
        uav_extension = _ensure_mapping(extensions.get(UAV_EXTENSION_KEY), f"GraphNode `{node_id}` extension `{UAV_EXTENSION_KEY}`")

        yaw_hint = uav_extension.get("yaw_hint_deg")
        if yaw_hint is not None:
            yaw_hint = float(yaw_hint)
            if not math.isfinite(yaw_hint):
                raise GraphSchemaError(f"GraphNode `{node_id}` field `extensions.uav.yaw_hint_deg` must be finite")
        sample_radius = uav_extension.get("sample_radius")
        meta = dict(properties)
        if sample_radius is not None:
            try:
                radius = float(sample_radius)
            except Exception as exc:
                raise GraphSchemaError(f"GraphNode `{node_id}` field `extensions.uav.sample_radius` must be numeric") from exc
            if not math.isfinite(radius):
                raise GraphSchemaError(f"GraphNode `{node_id}` field `extensions.uav.sample_radius` must be finite")
            meta["node_sample_radius"] = radius
        return cls(
            id=node_id,
            name=name,
            position=position,
            yaw_hint=yaw_hint,
            tags=_ensure_str_list(raw.get("tags")),
            meta=meta,
            extensions=extensions,
        )

    def to_dict(self) -> dict[str, Any]:
        properties = dict(self.meta)
        sample_radius = properties.pop("node_sample_radius", None)
        extensions = dict(self.extensions)
        uav_extension = _ensure_mapping(extensions.get(UAV_EXTENSION_KEY), f"GraphNode `{self.id}` extension `{UAV_EXTENSION_KEY}`")
        if self.yaw_hint is not None:
            uav_extension["yaw_hint_deg"] = _round_float(float(self.yaw_hint))
        if sample_radius is not None:
            uav_extension["sample_radius"] = _round_float(float(sample_radius))
        if uav_extension:
            extensions[UAV_EXTENSION_KEY] = uav_extension
        else:
            extensions.pop(UAV_EXTENSION_KEY, None)

        return _clean_empty_objects({
            "id": self.id,
            "label": self.name,
            "position": [_round_float(v) for v in self.position],
            "tags": list(self.tags),
            "properties": properties,
            "extensions": extensions,
        })


@dataclass(slots=True)
class GraphEdge:
    id: str
    from_node: str
    to_node: str
    weight: float
    enabled: bool = True
    bidirectional: bool = True
    meta: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
    metrics_explicit: bool = True
    weight_explicit: bool = True

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        node_lookup: Mapping[str, GraphNode] | None = None,
    ) -> "GraphEdge":
        try:
            edge_id = _as_non_empty_str(raw["id"], "GraphEdge `id`")
        except KeyError as exc:
            raise GraphSchemaError("GraphEdge is missing required field `id`") from exc

        from_node = raw.get("source")
        to_node = raw.get("target")
        if from_node is None or to_node is None:
            raise GraphSchemaError(f"GraphEdge `{edge_id}` must define `source` and `target`")
        from_node = _as_non_empty_str(from_node, f"GraphEdge `{edge_id}` field `source`")
        to_node = _as_non_empty_str(to_node, f"GraphEdge `{edge_id}` field `target`")

        properties = _ensure_mapping(raw.get("properties"), f"GraphEdge `{edge_id}` field `properties`")
        extensions = _ensure_mapping(raw.get("extensions"), f"GraphEdge `{edge_id}` field `extensions`")
        webui_extension = _ensure_mapping(
            extensions.get(WEBUI_EXTENSION_KEY),
            f"GraphEdge `{edge_id}` extension `{WEBUI_EXTENSION_KEY}`",
        )
        metrics = _as_metrics(raw.get("metrics"), f"GraphEdge `{edge_id}` field `metrics`")
        metrics_explicit = bool(metrics)
        if "cost" in metrics:
            weight = metrics["cost"]
        elif "length" in metrics:
            weight = metrics["length"]
        elif node_lookup is not None and from_node in node_lookup and to_node in node_lookup:
            weight = edge_xy_weight(node_lookup[from_node], node_lookup[to_node])
        else:
            weight = 0.0

        return cls(
            id=edge_id,
            from_node=from_node,
            to_node=to_node,
            weight=weight,
            enabled=_as_strict_bool(raw.get("enabled", True), f"GraphEdge `{edge_id}` field `enabled`"),
            bidirectional=not _as_strict_bool(raw.get("directed", False), f"GraphEdge `{edge_id}` field `directed`"),
            meta=webui_extension,
            metrics=metrics,
            properties=properties,
            extensions=extensions,
            metrics_explicit=metrics_explicit,
            weight_explicit=False,
        )

    def to_dict(self) -> dict[str, Any]:
        extensions = dict(self.extensions)
        if self.meta:
            extensions = _merge_extension(extensions, WEBUI_EXTENSION_KEY, self.meta)
        elif WEBUI_EXTENSION_KEY in extensions:
            extensions.pop(WEBUI_EXTENSION_KEY, None)

        metrics = dict(self.metrics)
        if not metrics and self.metrics_explicit:
            metrics = {"length": float(self.weight), "cost": float(self.weight)}
        metrics = {key: _round_float(value) for key, value in metrics.items()}

        return _clean_empty_objects({
            "id": self.id,
            "source": self.from_node,
            "target": self.to_node,
            "directed": not bool(self.bidirectional),
            "enabled": bool(self.enabled),
            "metrics": metrics,
            "properties": dict(self.properties),
            "extensions": extensions,
        })


@dataclass(slots=True)
class RouteGraph:
    env_id: str
    graph_name: str
    default_altitude: float | None
    graph_id: str | None = None
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    format_version: int = CURRENT_GRAPH_FORMAT_VERSION
    coordinate_system: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_COORDINATE_SYSTEM))
    properties: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RouteGraph":
        try:
            graph_format = raw["format"]
            format_version = raw["format_version"]
            graph_id = _as_non_empty_str(raw["id"], "RouteGraph `id`")
            graph_name = _as_non_empty_str(raw["name"], "RouteGraph `name`")
            raw_coordinate_system = raw["coordinate_system"]
            raw_nodes = raw["nodes"]
            raw_edges = raw["edges"]
        except KeyError as exc:
            raise GraphSchemaError("RouteGraph requires `format`, `format_version`, `id`, `name`, `coordinate_system`, `nodes`, and `edges`") from exc

        if graph_format != CURRENT_GRAPH_FORMAT:
            raise GraphSchemaError(f"RouteGraph `format` must be `{CURRENT_GRAPH_FORMAT}`")
        if (
            not isinstance(format_version, int)
            or isinstance(format_version, bool)
            or format_version != CURRENT_GRAPH_FORMAT_VERSION
        ):
            raise GraphSchemaError(f"RouteGraph `format_version` must be {CURRENT_GRAPH_FORMAT_VERSION}")
        if not isinstance(raw_nodes, list):
            raise GraphSchemaError("RouteGraph `nodes` must be an array")
        if not isinstance(raw_edges, list):
            raise GraphSchemaError("RouteGraph `edges` must be an array")

        coordinate_system = _ensure_mapping(raw_coordinate_system, "coordinate_system")
        properties = _ensure_mapping(raw.get("properties"), "properties")
        extensions = _ensure_mapping(raw.get("extensions"), "extensions")
        uav_extension = _ensure_mapping(extensions.get(UAV_EXTENSION_KEY), f"extensions.{UAV_EXTENSION_KEY}")
        webui_extension = _ensure_mapping(extensions.get(WEBUI_EXTENSION_KEY), f"extensions.{WEBUI_EXTENSION_KEY}")

        default_altitude = uav_extension.get("default_altitude")
        if default_altitude is not None:
            default_altitude = float(default_altitude)
            if not math.isfinite(default_altitude):
                raise GraphSchemaError("RouteGraph `extensions.uav.default_altitude` must be finite")
        env_id = _optional_str(uav_extension.get("env_id")) or ""
        nodes: list[GraphNode] = []
        for index, item in enumerate(raw_nodes):
            if not isinstance(item, Mapping):
                raise GraphSchemaError(f"RouteGraph `nodes[{index}]` must be an object")
            nodes.append(GraphNode.from_mapping(item))
        node_lookup = {node.id: node for node in nodes}
        edges: list[GraphEdge] = []
        for index, item in enumerate(raw_edges):
            if not isinstance(item, Mapping):
                raise GraphSchemaError(f"RouteGraph `edges[{index}]` must be an object")
            edges.append(GraphEdge.from_mapping(item, node_lookup=node_lookup))

        return cls(
            env_id=env_id,
            graph_name=graph_name,
            default_altitude=default_altitude,
            graph_id=graph_id,
            nodes=nodes,
            edges=edges,
            meta=webui_extension,
            format_version=format_version,
            coordinate_system=coordinate_system,
            properties=properties,
            extensions=extensions,
        )

    @property
    def node_map(self) -> dict[str, GraphNode]:
        return {node.id: node for node in self.nodes}

    @property
    def edge_map(self) -> dict[str, GraphEdge]:
        return {edge.id: edge for edge in self.edges}

    def get_node(self, node_id: str) -> GraphNode:
        try:
            return self.node_map[node_id]
        except KeyError as exc:
            raise GraphSchemaError(f"Graph node `{node_id}` does not exist") from exc

    def get_edge(self, edge_id: str) -> GraphEdge:
        try:
            return self.edge_map[edge_id]
        except KeyError as exc:
            raise GraphSchemaError(f"Graph edge `{edge_id}` does not exist") from exc

    def to_dict(self) -> dict[str, Any]:
        extensions = dict(self.extensions)
        uav_payload: dict[str, Any] = {}
        if self.env_id:
            uav_payload["env_id"] = self.env_id
        if self.default_altitude is not None:
            uav_payload["default_altitude"] = _round_float(float(self.default_altitude))
        extensions = _merge_extension(extensions, UAV_EXTENSION_KEY, uav_payload)
        if self.meta:
            extensions = _merge_extension(extensions, WEBUI_EXTENSION_KEY, self.meta)
        else:
            extensions.pop(WEBUI_EXTENSION_KEY, None)

        return _clean_empty_objects({
            "format": CURRENT_GRAPH_FORMAT,
            "format_version": int(self.format_version),
            "id": self.graph_id or self.graph_name,
            "name": self.graph_name,
            "coordinate_system": dict(self.coordinate_system or DEFAULT_COORDINATE_SYSTEM),
            "properties": dict(self.properties),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "extensions": extensions,
        })


@dataclass(slots=True)
class RouteSegment:
    start_anchor: str
    end_anchor: str
    node_ids: list[str]
    edge_ids: list[str]
    length: float
    edge_passes: list["RouteEdgePass"] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RouteSegment":
        return cls(
            start_anchor=str(raw["start_anchor"]),
            end_anchor=str(raw["end_anchor"]),
            node_ids=[str(item) for item in raw.get("node_ids", [])],
            edge_ids=[str(item) for item in raw.get("edge_ids", [])],
            edge_passes=[RouteEdgePass.from_mapping(item) for item in raw.get("edge_passes", [])],
            length=float(raw.get("length", 0.0)),
            meta=dict(raw.get("meta") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_anchor": self.start_anchor,
            "end_anchor": self.end_anchor,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "edge_passes": [edge_pass.to_dict() for edge_pass in self.edge_passes],
            "length": round(float(self.length), 6),
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class RoutePlan:
    env_id: str
    graph_name: str
    anchor_nodes: list[str]
    planned_nodes: list[str]
    segments: list[RouteSegment]
    total_length: float
    edge_passes: list["RouteEdgePass"] = field(default_factory=list)
    node_lookup: dict[str, GraphNode] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    evaluation_version: int = CURRENT_EVALUATION_VERSION

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RoutePlan":
        try:
            evaluation_version = resolve_evaluation_version(raw)
        except ValueError as exc:
            raise GraphSchemaError(str(exc)) from exc
        try:
            env_id = str(raw["env_id"])
            graph_name = str(raw["graph_name"])
        except KeyError as exc:
            raise GraphSchemaError("RoutePlan requires `env_id` and `graph_name`") from exc

        node_lookup_raw = raw.get("node_lookup") or {}
        node_lookup = {
            str(node_id): GraphNode.from_mapping(node_raw)
            for node_id, node_raw in node_lookup_raw.items()
        }
        return cls(
            env_id=env_id,
            graph_name=graph_name,
            anchor_nodes=[str(item) for item in raw.get("anchor_nodes", [])],
            planned_nodes=[str(item) for item in raw.get("planned_nodes", [])],
            segments=[RouteSegment.from_mapping(item) for item in raw.get("segments", [])],
            edge_passes=[RouteEdgePass.from_mapping(item) for item in raw.get("edge_passes", [])],
            total_length=float(raw.get("total_length", 0.0)),
            node_lookup=node_lookup,
            meta=dict(raw.get("meta") or {}),
            evaluation_version=evaluation_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_version": int(self.evaluation_version),
            "env_id": self.env_id,
            "graph_name": self.graph_name,
            "anchor_nodes": list(self.anchor_nodes),
            "planned_nodes": list(self.planned_nodes),
            "segments": [segment.to_dict() for segment in self.segments],
            "edge_passes": [edge_pass.to_dict() for edge_pass in self.edge_passes],
            "total_length": round(float(self.total_length), 6),
            "node_lookup": {
                node_id: node.to_dict() for node_id, node in sorted(self.node_lookup.items())
            },
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class RouteEdgePass:
    pass_index: int
    edge_id: str
    from_node: str
    to_node: str
    segment_index: int
    local_index: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RouteEdgePass":
        return cls(
            pass_index=int(raw["pass_index"]),
            edge_id=str(raw["edge_id"]),
            from_node=str(raw["from_node"]),
            to_node=str(raw["to_node"]),
            segment_index=int(raw.get("segment_index", 0)),
            local_index=int(raw.get("local_index", 0)),
        )

    def signature(self) -> tuple[str, str, str]:
        return (self.edge_id, self.from_node, self.to_node)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_index": int(self.pass_index),
            "edge_id": self.edge_id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "segment_index": int(self.segment_index),
            "local_index": int(self.local_index),
        }


@dataclass(slots=True)
class RouteCandidate:
    candidate_id: str
    rank: int
    planned_nodes: list[str]
    edge_passes: list[RouteEdgePass]
    segments: list[RouteSegment]
    total_length: float
    selected: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RouteCandidate":
        return cls(
            candidate_id=str(raw["candidate_id"]),
            rank=int(raw.get("rank", 0)),
            planned_nodes=[str(item) for item in raw.get("planned_nodes", [])],
            edge_passes=[RouteEdgePass.from_mapping(item) for item in raw.get("edge_passes", [])],
            segments=[RouteSegment.from_mapping(item) for item in raw.get("segments", [])],
            total_length=float(raw.get("total_length", 0.0)),
            selected=_as_bool(
                raw.get("selected", False),
                f"RouteCandidate `{raw['candidate_id']}` field `selected`",
            ),
            meta=dict(raw.get("meta") or {}),
        )

    def signature(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(edge_pass.signature() for edge_pass in self.edge_passes)

    def edge_pass_count(self) -> int:
        return len(self.edge_passes)

    def repeat_node_count(self) -> int:
        seen: set[str] = set()
        repeats = 0
        for node_id in self.planned_nodes:
            if node_id in seen:
                repeats += 1
            else:
                seen.add(node_id)
        return repeats

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "rank": int(self.rank),
            "planned_nodes": list(self.planned_nodes),
            "edge_passes": [edge_pass.to_dict() for edge_pass in self.edge_passes],
            "segments": [segment.to_dict() for segment in self.segments],
            "total_length": round(float(self.total_length), 6),
            "selected": bool(self.selected),
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class RouteCandidateSet:
    env_id: str
    graph_name: str
    anchor_nodes: list[str]
    candidates: list[RouteCandidate]
    node_lookup: dict[str, GraphNode] = field(default_factory=dict)
    selected_candidate_ids: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    evaluation_version: int = CURRENT_EVALUATION_VERSION

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RouteCandidateSet":
        try:
            evaluation_version = resolve_evaluation_version(raw)
        except ValueError as exc:
            raise GraphSchemaError(str(exc)) from exc
        try:
            env_id = str(raw["env_id"])
            graph_name = str(raw["graph_name"])
        except KeyError as exc:
            raise GraphSchemaError("RouteCandidateSet requires `env_id` and `graph_name`") from exc

        node_lookup_raw = raw.get("node_lookup") or {}
        node_lookup = {
            str(node_id): GraphNode.from_mapping(node_raw)
            for node_id, node_raw in node_lookup_raw.items()
        }
        candidates = [RouteCandidate.from_mapping(item) for item in raw.get("candidates", [])]
        selected_ids_raw = raw.get("selected_candidate_ids")
        if selected_ids_raw is None:
            selected_candidate_ids = [candidate.candidate_id for candidate in candidates if candidate.selected]
        else:
            selected_candidate_ids = [str(item) for item in selected_ids_raw]

        selected_set = set(selected_candidate_ids)
        for candidate in candidates:
            candidate.selected = candidate.candidate_id in selected_set

        return cls(
            env_id=env_id,
            graph_name=graph_name,
            anchor_nodes=[str(item) for item in raw.get("anchor_nodes", [])],
            candidates=candidates,
            node_lookup=node_lookup,
            selected_candidate_ids=selected_candidate_ids,
            meta=dict(raw.get("meta") or {}),
            evaluation_version=evaluation_version,
        )

    def get_candidate(self, candidate_id: str) -> RouteCandidate:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise GraphSchemaError(f"Route candidate `{candidate_id}` does not exist")

    def sync_selected_ids(self) -> None:
        self.selected_candidate_ids = [
            candidate.candidate_id for candidate in self.candidates if candidate.selected
        ]

    def to_dict(self) -> dict[str, Any]:
        self.sync_selected_ids()
        return {
            "evaluation_version": int(self.evaluation_version),
            "env_id": self.env_id,
            "graph_name": self.graph_name,
            "anchor_nodes": list(self.anchor_nodes),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "node_lookup": {
                node_id: node.to_dict() for node_id, node in sorted(self.node_lookup.items())
            },
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "meta": dict(self.meta),
        }


def edge_xy_weight(node_a: GraphNode, node_b: GraphNode) -> float:
    dx = float(node_b.position[0]) - float(node_a.position[0])
    dy = float(node_b.position[1]) - float(node_a.position[1])
    return math.sqrt(dx * dx + dy * dy)


def edge_planning_weight(edge: GraphEdge, node_lookup: Mapping[str, GraphNode]) -> float:
    if "cost" in edge.metrics:
        return float(edge.metrics["cost"])
    if "length" in edge.metrics:
        return float(edge.metrics["length"])
    if edge.weight_explicit:
        return float(edge.weight)
    try:
        from_node = node_lookup[edge.from_node]
        to_node = node_lookup[edge.to_node]
    except KeyError as exc:
        raise GraphSchemaError(
            f"GraphEdge `{edge.id}` references unknown node(s) `{edge.from_node}` -> `{edge.to_node}`"
        ) from exc
    return edge_xy_weight(from_node, to_node)


def physical_edge_key(from_node: str, to_node: str) -> tuple[str, str]:
    return tuple(sorted((str(from_node), str(to_node))))

__all__ = [
    "CURRENT_EVALUATION_VERSION",
    "CURRENT_GRAPH_FORMAT",
    "CURRENT_GRAPH_FORMAT_VERSION",
    "DEFAULT_COORDINATE_SYSTEM",
    "GraphEdge",
    "GraphNode",
    "GraphSchemaError",
    "GraphValidationIssue",
    "GraphValidationReport",
    "RouteCandidate",
    "RouteCandidateSet",
    "RouteEdgePass",
    "RouteGraph",
    "RoutePlan",
    "RouteSegment",
    "clone_graph_node",
    "clone_node_lookup",
    "edge_planning_weight",
    "edge_xy_weight",
    "physical_edge_key",
]
