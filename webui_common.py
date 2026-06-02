from __future__ import annotations

import time
from pathlib import Path

if __package__ in {None, ""}:
    from graph_store import (
        DATA_DIR,
        ROUTE_GRAPH_WEBUI_DATA_DIR_ENV,
        ROUTE_GRAPH_WEBUI_DIR,
        ROUTE_GRAPH_WEBUI_RELEASE_ENV,
        ensure_data_directories,
        resolve_data_dir,
    )
    from spelling_compat import (
        LEGACY_ROUTE_GARPH_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_NAME,
        LEGACY_SPELLING_RETIREMENT_DATE,
    )
else:
    from .graph_store import (
        DATA_DIR,
        ROUTE_GRAPH_WEBUI_DATA_DIR_ENV,
        ROUTE_GRAPH_WEBUI_DIR,
        ROUTE_GRAPH_WEBUI_RELEASE_ENV,
        ensure_data_directories,
        resolve_data_dir,
    )
    from .spelling_compat import (
        LEGACY_ROUTE_GARPH_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_NAME,
        LEGACY_SPELLING_RETIREMENT_DATE,
    )


def resolve_route_path(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    path = Path(str(path_value))
    if path.is_absolute():
        return path.resolve()
    return (ROUTE_GRAPH_WEBUI_DIR / path).resolve()


def resolve_data_path(*parts: str) -> Path:
    return (resolve_data_dir().joinpath(*parts)).resolve()


def timestamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


__all__ = [
    "DATA_DIR",
    "LEGACY_ROUTE_GARPH_DIR_ENV",
    "LEGACY_ROUTE_GARPH_DIR_NAME",
    "LEGACY_SPELLING_RETIREMENT_DATE",
    "ROUTE_GRAPH_WEBUI_DATA_DIR_ENV",
    "ROUTE_GRAPH_WEBUI_DIR",
    "ROUTE_GRAPH_WEBUI_RELEASE_ENV",
    "ensure_data_directories",
    "resolve_data_path",
    "resolve_data_dir",
    "resolve_route_path",
    "timestamp_now",
]
