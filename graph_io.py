from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    from graph_model import GraphSchemaError, RouteCandidateSet, RouteGraph, RoutePlan
    from graph_validation import ensure_valid_graph, ensure_valid_plan
    from json_store import read_json, write_json_atomic
else:
    from .graph_model import GraphSchemaError, RouteCandidateSet, RouteGraph, RoutePlan
    from .graph_validation import ensure_valid_graph, ensure_valid_plan
    from .json_store import read_json, write_json_atomic

def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    try:
        payload = read_json(resolved)
    except FileNotFoundError as exc:
        raise GraphSchemaError(f"JSON file not found: {resolved}") from exc
    except ValueError as exc:
        raise GraphSchemaError(f"JSON file is invalid: {resolved}") from exc
    if not isinstance(payload, dict):
        raise GraphSchemaError(f"JSON file root must be an object: {resolved}")
    return payload


def dump_json(path: str | Path, data: Mapping[str, Any]) -> Path:
    resolved = Path(path).resolve()
    return write_json_atomic(resolved, dict(data), indent=2)


def load_graph(path: str | Path) -> RouteGraph:
    return RouteGraph.from_mapping(load_json(path))


def save_graph(path: str | Path, graph: RouteGraph) -> Path:
    ensure_valid_graph(graph)
    return dump_json(path, graph.to_dict())


def load_plan(path: str | Path) -> RoutePlan:
    return RoutePlan.from_mapping(load_json(path))


def save_plan(path: str | Path, plan: RoutePlan) -> Path:
    ensure_valid_plan(plan)
    return dump_json(path, plan.to_dict())


def load_candidate_set(path: str | Path) -> RouteCandidateSet:
    return RouteCandidateSet.from_mapping(load_json(path))


def save_candidate_set(path: str | Path, candidate_set: RouteCandidateSet) -> Path:
    return dump_json(path, candidate_set.to_dict())

__all__ = [
    "dump_json",
    "load_candidate_set",
    "load_graph",
    "load_json",
    "load_plan",
    "save_candidate_set",
    "save_graph",
    "save_plan",
]
