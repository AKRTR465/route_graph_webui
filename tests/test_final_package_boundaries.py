from __future__ import annotations

import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_ROOT_FILES = {
    "__init__.py",
    "bootstrap_paths.py",
    "graph_model.py",
    "graph_meta.py",
    "graph_io.py",
    "graph_validation.py",
    "graph_grouping.py",
    "candidate_conversion.py",
    "graph_schema.py",
    "graph_store.py",
    "json_store.py",
    "runtime.py",
    "env_registry.py",
    "webui_common.py",
    "graph_ui_state.py",
    "graph_canvas_view.py",
    "edge_intent_service.py",
    "auto_route_planner.py",
    "route_generation_worker.py",
    "geometry.py",
    "cli_args.py",
    "image_sequence_utils.py",
    "mission_io.py",
    "spelling_compat.py",
    "calculer.py",
    "resample.py",
    "composed_video.py",
    "mission_repair.py",
    "takeoff_landing_repair.py",
    "registered_env_ids.json",
}

FORBIDDEN_ROOT_DIRS = {
    "mission_export",
    "preview",
    "tools",
    "webui_backend",
    "__pycache__",
}

ROOT_WRAPPERS = {
    "graph_record.py": "route_graph_webui.cli.graph_record",
    "graph_editor.py": "route_graph_webui.cli.graph_editor",
    "route_planner.py": "route_graph_webui.cli.route_planner",
    "mission_export.py": "route_graph_webui.cli.mission_export",
    "graph_gui.py": "route_graph_webui.cli.graph_gui",
    "visualize_graph.py": "route_graph_webui.cli.visualize_graph",
}

LEGACY_IMPORT_RE = re.compile(
    r"^(from|import) "
    r"(graph_|mission_export|route_planner|runtime|json_store|edge_intent_service|"
    r"auto_route_planner|graph_store|graph_ui_state|graph_canvas_view|env_registry|"
    r"composed_video|mission_io|bootstrap_paths|spelling_compat)\b",
    re.MULTILINE,
)


def _python_files_under(*names: str) -> list[Path]:
    files: list[Path] = []
    for name in names:
        root = PROJECT_ROOT / name
        if root.exists():
            files.extend(root.rglob("*.py"))
    return sorted(files)


def test_no_legacy_bare_imports_in_tests_src_or_scripts() -> None:
    offenders: list[str] = []
    for path in _python_files_under("tests", "src", "scripts"):
        text = path.read_text(encoding="utf-8")
        if LEGACY_IMPORT_RE.search(text):
            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert offenders == []


def test_no_manual_sys_path_insertions_in_tests_src_or_scripts() -> None:
    needle = "sys.path" + ".insert"
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _python_files_under("tests", "src", "scripts")
        if needle in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_forbidden_root_modules_and_legacy_directories_are_absent() -> None:
    remaining_files = sorted(name for name in FORBIDDEN_ROOT_FILES if (PROJECT_ROOT / name).exists())
    remaining_dirs = sorted(name for name in FORBIDDEN_ROOT_DIRS if (PROJECT_ROOT / name).exists())

    assert remaining_files == []
    assert remaining_dirs == []


def test_root_cli_wrappers_are_thin_entry_points() -> None:
    for filename, module_name in ROOT_WRAPPERS.items():
        source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        lines = [line.strip() for line in source.splitlines() if line.strip()]

        assert lines == [
            "from __future__ import annotations",
            f"from {module_name} import main",
            'if __name__ == "__main__":',
            "raise SystemExit(main())",
        ]


def test_runtime_graph_examples_are_no_longer_tracked_in_data_graphs() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/graphs"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == ""

    examples = sorted((PROJECT_ROOT / "data" / "examples" / "graphs").glob("*.json"))
    assert [path.name for path in examples] == [
        "DowntownWest.json",
        "Map_ChemicalPlant_1.json",
        "ModularBuilding.json",
        "ModularNeighborhood.json",
        "Venice.json",
    ]
