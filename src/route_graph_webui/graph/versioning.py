from __future__ import annotations

from typing import Any, Mapping

from route_graph_webui.storage.spelling_compat import normalize_legacy_graph_meta


CURRENT_GRAPH_SCHEMA_VERSION = 1
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


def migrate_graph_mapping(raw: Mapping[str, Any]) -> dict[str, Any]:
    migrated = dict(raw)
    if "meta" in migrated:
        migrated["meta"] = normalize_legacy_graph_meta(migrated.get("meta"))
    migrated["schema_version"] = normalize_version(
        migrated.get("schema_version"),
        default=CURRENT_GRAPH_SCHEMA_VERSION,
        field_name="schema_version",
    )
    return migrated


def resolve_graph_schema_version(raw: Mapping[str, Any]) -> int:
    return normalize_version(
        raw.get("schema_version"),
        default=CURRENT_GRAPH_SCHEMA_VERSION,
        field_name="schema_version",
    )


def resolve_evaluation_version(raw: Mapping[str, Any]) -> int:
    return normalize_version(
        raw.get("evaluation_version"),
        default=CURRENT_EVALUATION_VERSION,
        field_name="evaluation_version",
    )


__all__ = [
    "CURRENT_EVALUATION_VERSION",
    "CURRENT_GRAPH_SCHEMA_VERSION",
    "migrate_graph_mapping",
    "normalize_version",
    "resolve_evaluation_version",
    "resolve_graph_schema_version",
]
