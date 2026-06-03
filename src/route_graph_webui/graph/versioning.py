from __future__ import annotations

from typing import Any, Mapping


CURRENT_GRAPH_FORMAT = "route-graph"
CURRENT_GRAPH_FORMAT_VERSION = 1
CURRENT_EVALUATION_VERSION = 1


def normalize_version(value: Any, *, default: int, field_name: str) -> int:
    if value is None:
        return int(default)
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{field_name}` must be an integer") from exc
    if version < 1:
        raise ValueError(f"`{field_name}` must be at least 1")
    return version


def resolve_graph_format_version(raw: Mapping[str, Any]) -> int:
    return normalize_version(
        raw.get("format_version"),
        default=CURRENT_GRAPH_FORMAT_VERSION,
        field_name="format_version",
    )


def resolve_evaluation_version(raw: Mapping[str, Any]) -> int:
    return normalize_version(
        raw.get("evaluation_version"),
        default=CURRENT_EVALUATION_VERSION,
        field_name="evaluation_version",
    )


__all__ = [
    "CURRENT_GRAPH_FORMAT",
    "CURRENT_GRAPH_FORMAT_VERSION",
    "CURRENT_EVALUATION_VERSION",
    "normalize_version",
    "resolve_evaluation_version",
    "resolve_graph_format_version",
]
