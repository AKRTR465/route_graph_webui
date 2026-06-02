from __future__ import annotations

from typing import Any, Mapping


from .meta import (
    GRAPH_GUI_CANVAS_VIEW_BOOL_KEYS,
    GRAPH_GUI_CANVAS_VIEW_DEFAULTS,
    GRAPH_GUI_CANVAS_VIEW_META_KEY,
)


def normalize_graph_gui_canvas_view(payload: Any) -> dict[str, int | bool]:
    if not isinstance(payload, Mapping):
        return {}

    normalized: dict[str, int | bool] = {}
    raw_rotation = payload.get("rotation_quadrants")
    if isinstance(raw_rotation, int) and not isinstance(raw_rotation, bool) and raw_rotation in {0, 1, 2, 3}:
        normalized["rotation_quadrants"] = raw_rotation

    for key in GRAPH_GUI_CANVAS_VIEW_BOOL_KEYS:
        if key not in payload:
            continue
        raw_value = payload.get(key)
        if isinstance(raw_value, bool):
            normalized[key] = raw_value
        elif isinstance(raw_value, int) and raw_value in {0, 1}:
            normalized[key] = bool(raw_value)

    return normalized


def read_graph_gui_canvas_view(meta: Mapping[str, Any] | None) -> dict[str, int | bool]:
    if not isinstance(meta, Mapping):
        return {}
    raw_payload = meta.get(GRAPH_GUI_CANVAS_VIEW_META_KEY)
    return normalize_graph_gui_canvas_view(raw_payload)


def resolve_graph_gui_canvas_view(meta: Mapping[str, Any] | None) -> dict[str, int | bool]:
    resolved = dict(GRAPH_GUI_CANVAS_VIEW_DEFAULTS)
    resolved.update(read_graph_gui_canvas_view(meta))
    return resolved


def write_graph_gui_canvas_view(
    meta: dict[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, int | bool]:
    normalized = normalize_graph_gui_canvas_view(dict(payload))
    meta[GRAPH_GUI_CANVAS_VIEW_META_KEY] = normalized
    return normalized


def sync_graph_gui_canvas_view(meta: dict[str, Any], payload: Mapping[str, Any]) -> bool:
    current = normalize_graph_gui_canvas_view(dict(payload))
    defaults = dict(GRAPH_GUI_CANVAS_VIEW_DEFAULTS)
    raw_has_key = GRAPH_GUI_CANVAS_VIEW_META_KEY in meta
    if current == defaults:
        if raw_has_key:
            meta.pop(GRAPH_GUI_CANVAS_VIEW_META_KEY, None)
            return True
        return False

    existing = resolve_graph_gui_canvas_view(meta)
    if existing == current and raw_has_key:
        return False

    write_graph_gui_canvas_view(meta, current)
    return True
