from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    from spelling_compat import (
        CANONICAL_DATA_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_NAME,
        legacy_route_graph_data_roots,
        warn_legacy_spelling,
    )
else:
    from .spelling_compat import (
        CANONICAL_DATA_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_ENV,
        LEGACY_ROUTE_GARPH_DIR_NAME,
        legacy_route_graph_data_roots,
        warn_legacy_spelling,
    )

ROUTE_GRAPH_WEBUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROUTE_GRAPH_WEBUI_DIR
ROUTE_GRAPH_WEBUI_DATA_DIR_ENV = CANONICAL_DATA_DIR_ENV
ROUTE_GRAPH_WEBUI_RELEASE_ENV = "ROUTE_GRAPH_WEBUI_RELEASE"


@dataclass(frozen=True, slots=True)
class GraphStorePaths:
    data: Path
    baselines: Path
    graphs: Path
    plans: Path
    missions: Path
    previews: Path
    progress: Path
    state: Path
    webui_state: Path


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_env_path(raw_value: str) -> Path:
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def default_user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return (Path(base) / "RouteGraphWebUI" / "data").resolve()
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return (Path(base) / "route_graph_webui").resolve()
    return (Path.home() / ".local" / "share" / "route_graph_webui").resolve()


def resolve_data_dir() -> Path:
    raw_data_dir = os.environ.get(ROUTE_GRAPH_WEBUI_DATA_DIR_ENV)
    if raw_data_dir and raw_data_dir.strip():
        return _resolve_env_path(raw_data_dir.strip())
    if _truthy(os.environ.get(ROUTE_GRAPH_WEBUI_RELEASE_ENV)) or getattr(sys, "frozen", False):
        return default_user_data_dir()
    return (PROJECT_ROOT / "data").resolve()


def get_store_paths(data_dir: str | Path | None = None) -> GraphStorePaths:
    root = Path(data_dir).expanduser().resolve() if data_dir is not None else resolve_data_dir()
    return GraphStorePaths(
        data=root,
        baselines=root / "baselines",
        graphs=root / "graphs",
        plans=root / "plans",
        missions=root / "missions",
        previews=root / "previews",
        progress=root / "progress",
        state=root / "state",
        webui_state=root / "webui_state.json",
    )


DATA_DIR = resolve_data_dir()
STORE_PATHS = get_store_paths(DATA_DIR)
GRAPH_ROOT = STORE_PATHS.graphs
PLAN_ROOT = STORE_PATHS.plans
MISSION_ROOT = STORE_PATHS.missions
PREVIEW_ROOT = STORE_PATHS.previews
PROGRESS_ROOT = STORE_PATHS.progress
WEBUI_APP_STATE_PATH = STORE_PATHS.webui_state


def legacy_data_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    raw_legacy_root = os.environ.get(LEGACY_ROUTE_GARPH_DIR_ENV)
    if raw_legacy_root and raw_legacy_root.strip():
        warn_legacy_spelling(
            LEGACY_ROUTE_GARPH_DIR_ENV,
            ROUTE_GRAPH_WEBUI_DATA_DIR_ENV,
            stacklevel=3,
        )
        legacy_root = _resolve_env_path(raw_legacy_root.strip())
        roots.append(legacy_root if legacy_root.name == "data" else legacy_root / "data")
    roots.extend(legacy_route_graph_data_roots(PROJECT_ROOT))
    seen: set[Path] = set()
    resolved: list[Path] = []
    for root in roots:
        candidate = root.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        resolved.append(candidate)
    return tuple(resolved)


def copy_sample_graphs_if_needed(data_dir: str | Path | None = None) -> None:
    paths = get_store_paths(data_dir)
    paths.graphs.mkdir(parents=True, exist_ok=True)
    if any(paths.graphs.glob("*.json")):
        return

    source_roots = [PROJECT_ROOT / "data" / "graphs"]
    source_roots.extend(root / "graphs" for root in legacy_data_roots())
    for source_root in source_roots:
        if source_root.resolve() == paths.graphs.resolve():
            continue
        if not source_root.exists():
            continue
        copied = False
        for source_path in sorted(source_root.glob("*.json")):
            shutil.copy2(source_path, paths.graphs / source_path.name)
            copied = True
        if copied:
            return


def ensure_data_directories(data_dir: str | Path | None = None) -> dict[str, Path]:
    paths = get_store_paths(data_dir)
    directories = {
        "data": paths.data,
        "baselines": paths.baselines,
        "graphs": paths.graphs,
        "plans": paths.plans,
        "missions": paths.missions,
        "previews": paths.previews,
        "progress": paths.progress,
        "state": paths.state,
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    copy_sample_graphs_if_needed(paths.data)
    return directories


def resolve_within_root(
    root: str | Path,
    raw_path: str | Path | None,
    *,
    default: str | Path | None = None,
    expect_json: bool = True,
) -> Path:
    resolved_root = Path(root).resolve()
    if raw_path is None or str(raw_path).strip() == "":
        if default is None:
            raise ValueError("A path must be provided")
        candidate = Path(default).resolve()
    else:
        candidate = Path(str(raw_path).strip())
        if not candidate.is_absolute():
            candidate = (resolved_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if expect_json and candidate.suffix == "":
            candidate = candidate.with_suffix(".json")

    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path must stay inside `{resolved_root}`") from exc

    if expect_json and candidate.suffix.lower() != ".json":
        raise ValueError("Only `.json` files are supported here")
    return candidate


def list_json_files(root: str | Path) -> list[Path]:
    resolved_root = Path(root).resolve()
    if not resolved_root.exists():
        return []
    return sorted(path.resolve() for path in resolved_root.rglob("*.json") if path.is_file())


def relative_to_root(path: str | Path, root: str | Path) -> str:
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def project_relative_path(
    path: str | Path,
    *,
    project_root: str | Path = PROJECT_ROOT,
    data_root: str | Path = DATA_DIR,
) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        pass
    try:
        return f"data/{resolved.relative_to(Path(data_root).resolve()).as_posix()}"
    except ValueError:
        return resolved.as_posix()


def existing_legacy_graph_paths() -> Iterable[Path]:
    for root in legacy_data_roots():
        graph_root = root / "graphs"
        if graph_root.exists():
            yield from list_json_files(graph_root)


__all__ = [
    "DATA_DIR",
    "GRAPH_ROOT",
    "LEGACY_ROUTE_GARPH_DIR_ENV",
    "LEGACY_ROUTE_GARPH_DIR_NAME",
    "MISSION_ROOT",
    "PLAN_ROOT",
    "PREVIEW_ROOT",
    "PROGRESS_ROOT",
    "PROJECT_ROOT",
    "ROUTE_GRAPH_WEBUI_DATA_DIR_ENV",
    "ROUTE_GRAPH_WEBUI_DIR",
    "ROUTE_GRAPH_WEBUI_RELEASE_ENV",
    "STORE_PATHS",
    "WEBUI_APP_STATE_PATH",
    "GraphStorePaths",
    "copy_sample_graphs_if_needed",
    "default_user_data_dir",
    "ensure_data_directories",
    "existing_legacy_graph_paths",
    "get_store_paths",
    "legacy_data_roots",
    "list_json_files",
    "project_relative_path",
    "relative_to_root",
    "resolve_data_dir",
    "resolve_within_root",
]
