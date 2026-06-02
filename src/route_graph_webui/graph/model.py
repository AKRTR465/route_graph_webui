from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .versioning import (
    CURRENT_EVALUATION_VERSION,
    CURRENT_GRAPH_SCHEMA_VERSION,
    migrate_graph_mapping,
    resolve_evaluation_version,
)

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


def _as_float_list(value: Iterable[Any], expected_length: int, field_name: str) -> list[float]:
    try:
        values = [float(item) for item in value]
    except Exception as exc:
        raise GraphSchemaError(f"`{field_name}` must be a list of numbers") from exc
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


def clone_graph_node(node: "GraphNode") -> "GraphNode":
    return GraphNode(
        id=str(node.id),
        name=str(node.name),
        position=[float(value) for value in node.position],
        yaw_hint=None if node.yaw_hint is None else float(node.yaw_hint),
        tags=list(node.tags),
        meta=dict(node.meta),
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

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GraphNode":
        try:
            node_id = str(raw["id"])
        except KeyError as exc:
            raise GraphSchemaError("GraphNode is missing required field `id`") from exc
        name = str(raw.get("name") or node_id)
        position = _as_float_list(raw.get("position", []), 3, "position")
        yaw_hint = raw.get("yaw_hint")
        if yaw_hint is not None:
            yaw_hint = float(yaw_hint)
        return cls(
            id=node_id,
            name=name,
            position=position,
            yaw_hint=yaw_hint,
            tags=_ensure_str_list(raw.get("tags")),
            meta=dict(raw.get("meta") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "position": [round(float(v), 6) for v in self.position],
            "yaw_hint": None if self.yaw_hint is None else round(float(self.yaw_hint), 6),
            "tags": list(self.tags),
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class GraphEdge:
    id: str
    from_node: str
    to_node: str
    weight: float
    enabled: bool = True
    bidirectional: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GraphEdge":
        try:
            edge_id = str(raw["id"])
        except KeyError as exc:
            raise GraphSchemaError("GraphEdge is missing required field `id`") from exc

        from_node = raw.get("from", raw.get("from_node"))
        to_node = raw.get("to", raw.get("to_node"))
        if from_node is None or to_node is None:
            raise GraphSchemaError(f"GraphEdge `{edge_id}` must define `from` and `to`")
        try:
            weight = float(raw["weight"])
        except KeyError as exc:
            raise GraphSchemaError(f"GraphEdge `{edge_id}` is missing `weight`") from exc
        except Exception as exc:
            raise GraphSchemaError(f"GraphEdge `{edge_id}` has invalid `weight`") from exc

        return cls(
            id=edge_id,
            from_node=str(from_node),
            to_node=str(to_node),
            weight=weight,
            enabled=_as_bool(raw.get("enabled", True), f"GraphEdge `{edge_id}` field `enabled`"),
            bidirectional=_as_bool(
                raw.get("bidirectional", True),
                f"GraphEdge `{edge_id}` field `bidirectional`",
            ),
            meta=dict(raw.get("meta") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from": self.from_node,
            "to": self.to_node,
            "weight": round(float(self.weight), 6),
            "enabled": bool(self.enabled),
            "bidirectional": bool(self.bidirectional),
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class RouteGraph:
    env_id: str
    graph_name: str
    default_altitude: float | None
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CURRENT_GRAPH_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RouteGraph":
        try:
            raw = migrate_graph_mapping(raw)
        except ValueError as exc:
            raise GraphSchemaError(str(exc)) from exc
        try:
            env_id = str(raw["env_id"])
            graph_name = str(raw["graph_name"])
        except KeyError as exc:
            raise GraphSchemaError("RouteGraph requires `env_id` and `graph_name`") from exc

        default_altitude = raw.get("default_altitude")
        if default_altitude is not None:
            default_altitude = float(default_altitude)

        return cls(
            env_id=env_id,
            graph_name=graph_name,
            default_altitude=default_altitude,
            nodes=[GraphNode.from_mapping(item) for item in raw.get("nodes", [])],
            edges=[GraphEdge.from_mapping(item) for item in raw.get("edges", [])],
            meta=dict(raw.get("meta") or {}),
            schema_version=int(raw["schema_version"]),
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
        return {
            "schema_version": int(self.schema_version),
            "env_id": self.env_id,
            "graph_name": self.graph_name,
            "default_altitude": None
            if self.default_altitude is None
            else round(float(self.default_altitude), 6),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "meta": dict(self.meta),
        }


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


def physical_edge_key(from_node: str, to_node: str) -> tuple[str, str]:
    return tuple(sorted((str(from_node), str(to_node))))

__all__ = [
    "CURRENT_EVALUATION_VERSION",
    "CURRENT_GRAPH_SCHEMA_VERSION",
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
    "edge_xy_weight",
    "physical_edge_key",
]
