from __future__ import annotations

import os
import sys
from pathlib import Path


ROUTE_GRAPH_WEBUI_DIR = Path(__file__).resolve().parent
ROOT_MARKERS = ("gym_unrealcv", "env_config.py", "pyproject.toml")


def _validate_project_root(path: Path) -> tuple[bool, list[str]]:
    missing = []
    for marker in ROOT_MARKERS:
        target = path / marker
        exists = target.is_dir() if marker == "gym_unrealcv" else target.exists()
        if not exists:
            missing.append(marker)
    return len(missing) == 0, missing


def find_project_root(start_path: str | os.PathLike | None = None) -> Path:
    env_override = os.environ.get("UAVMEM_PROJECT_ROOT")
    if env_override:
        candidate = Path(env_override).expanduser().resolve()
        ok, missing = _validate_project_root(candidate)
        if not ok:
            raise RuntimeError(
                f"UAVMEM_PROJECT_ROOT is invalid: {candidate}. Missing: {', '.join(missing)}"
            )
        return candidate

    anchor = Path(start_path).resolve() if start_path else ROUTE_GRAPH_WEBUI_DIR
    if anchor.is_file():
        anchor = anchor.parent

    checked: list[str] = []
    current = anchor
    while True:
        checked.append(str(current))
        ok, _ = _validate_project_root(current)
        if ok:
            return current

        parent = current.parent
        if parent == current:
            break
        current = parent

    raise RuntimeError(
        "Unable to find project root by traversing parent directories. "
        f"Start: {anchor}. Checked: {' -> '.join(checked)}. "
        f"Expected markers: {', '.join(ROOT_MARKERS)}"
    )


def inject_project_root(start_path: str | os.PathLike | None = None) -> Path:
    root = find_project_root(start_path=start_path)
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def resolve_project_path(path_value: str | os.PathLike | None) -> str | None:
    if path_value is None:
        return None

    path_str = str(path_value).strip()
    if not path_str:
        return path_str

    path = Path(path_str)
    if path.is_absolute():
        return str(path.resolve())
    return str((ROUTE_GRAPH_WEBUI_DIR / path).resolve())


__all__ = [
    "ROOT_MARKERS",
    "ROUTE_GRAPH_WEBUI_DIR",
    "find_project_root",
    "inject_project_root",
    "resolve_project_path",
]
