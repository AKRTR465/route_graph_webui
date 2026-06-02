from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

if __package__ in {None, ""}:
    from graph_schema import GraphSchemaError
else:
    from .graph_schema import GraphSchemaError


def load_mission_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GraphSchemaError(f"Failed to read JSON `{resolved}`: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GraphSchemaError(f"Invalid JSON `{resolved}`: {exc}") from exc
    if not isinstance(payload, dict):
        raise GraphSchemaError(f"JSON root must be a mapping: {resolved}")
    return payload


def write_mission_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved


def infer_image_name_template(
    positions: Iterable[Mapping[str, Any]],
    *,
    default_digits: int = 6,
    default_suffix: str = ".png",
) -> tuple[int, str]:
    for point in positions:
        image_path = point.get("image_path")
        if not isinstance(image_path, str) or "." not in image_path:
            continue
        stem, suffix = image_path.rsplit(".", 1)
        digits = len(stem) if stem.isdigit() else default_digits
        return digits, f".{suffix}"
    return default_digits, default_suffix


def build_image_name(index: int, *, digits: int, suffix: str) -> str:
    return f"{int(index):0{int(digits)}d}{suffix}"


def reindex_positions(
    positions: Iterable[Mapping[str, Any]],
    *,
    fps: float,
    start_time: float,
    image_digits: int,
    image_suffix: str,
) -> list[dict[str, Any]]:
    reindexed: list[dict[str, Any]] = []
    for index, point in enumerate(positions):
        updated = dict(point)
        updated["frame"] = index
        updated["time"] = float(start_time) + (index / fps)
        updated["image_path"] = build_image_name(index, digits=image_digits, suffix=image_suffix)
        reindexed.append(updated)
    return reindexed


__all__ = [
    "build_image_name",
    "infer_image_name_template",
    "load_mission_json",
    "reindex_positions",
    "write_mission_json",
]
