from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Mapping


LEGACY_SPELLING_RETIREMENT_DATE = "2026-12-31"

CANONICAL_PHOTOS_DIR_NAME = "photos"
LEGACY_PHOTOS_DIR_NAME = "phtots"

CANONICAL_DATA_DIR_ENV = "ROUTE_GRAPH_WEBUI_DATA_DIR"
LEGACY_ROUTE_GARPH_DIR_ENV = "ROUTE_GARPH_DIR"
LEGACY_ROUTE_GARPH_DIR_NAME = "route_garph"

LEGACY_GRAPH_CREATOR_PREFIX = "route_garph."
CANONICAL_GRAPH_CREATOR_PREFIX = "route_graph."
LEGACY_GRAPH_CREATOR_META_KEY = "legacy_creator"


def legacy_spelling_message(legacy_name: str, replacement: str) -> str:
    return (
        f"`{legacy_name}` is a legacy misspelling. Use `{replacement}` instead. "
        f"Compatibility is read-only and is scheduled for removal after "
        f"{LEGACY_SPELLING_RETIREMENT_DATE}."
    )


def warn_legacy_spelling(legacy_name: str, replacement: str, *, stacklevel: int = 2) -> None:
    warnings.warn(
        legacy_spelling_message(legacy_name, replacement),
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def resolve_photos_root(data_root: str | Path, *, scene_name: str | None = None) -> Path:
    root = Path(data_root)
    preferred = root / CANONICAL_PHOTOS_DIR_NAME
    fallback = root / LEGACY_PHOTOS_DIR_NAME
    if scene_name:
        preferred = preferred / scene_name
        fallback = fallback / scene_name
    if preferred.exists():
        return preferred.resolve()
    if fallback.exists():
        warn_legacy_spelling(
            LEGACY_PHOTOS_DIR_NAME,
            CANONICAL_PHOTOS_DIR_NAME,
            stacklevel=3,
        )
        return fallback.resolve()
    return preferred.resolve()


def legacy_route_graph_data_roots(project_root: str | Path) -> tuple[Path, ...]:
    root = Path(project_root)
    return (
        root / LEGACY_ROUTE_GARPH_DIR_NAME / "data",
        root.parent / LEGACY_ROUTE_GARPH_DIR_NAME / "data",
    )


def normalize_legacy_graph_meta(raw_meta: Any) -> Any:
    if not isinstance(raw_meta, Mapping):
        return raw_meta
    meta = dict(raw_meta)
    creator = meta.get("creator")
    if isinstance(creator, str) and creator.startswith(LEGACY_GRAPH_CREATOR_PREFIX):
        meta.setdefault(LEGACY_GRAPH_CREATOR_META_KEY, creator)
        meta["creator"] = CANONICAL_GRAPH_CREATOR_PREFIX + creator[len(LEGACY_GRAPH_CREATOR_PREFIX) :]
    return meta


__all__ = [
    "CANONICAL_DATA_DIR_ENV",
    "CANONICAL_GRAPH_CREATOR_PREFIX",
    "CANONICAL_PHOTOS_DIR_NAME",
    "LEGACY_GRAPH_CREATOR_META_KEY",
    "LEGACY_GRAPH_CREATOR_PREFIX",
    "LEGACY_PHOTOS_DIR_NAME",
    "LEGACY_ROUTE_GARPH_DIR_ENV",
    "LEGACY_ROUTE_GARPH_DIR_NAME",
    "LEGACY_SPELLING_RETIREMENT_DATE",
    "legacy_route_graph_data_roots",
    "legacy_spelling_message",
    "normalize_legacy_graph_meta",
    "resolve_photos_root",
    "warn_legacy_spelling",
]
