from __future__ import annotations

import importlib
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def test_graph_target_package_imports_from_src_skeleton() -> None:
    graph_package = importlib.import_module("route_graph_webui.graph")
    package_file = Path(graph_package.__file__).resolve()

    assert package_file.is_relative_to(SRC_ROOT.resolve())


def test_graph_package_does_not_add_legacy_reexport_shim_after_migration() -> None:
    graph_package = importlib.import_module("route_graph_webui.graph")

    forbidden_compat_exports = {
        "GraphNode",
        "GraphEdge",
        "RouteGraph",
        "load_graph",
        "validate_graph",
        "candidate_to_plan",
        "derive_graph_color_grouping",
    }
    leaked_exports = {
        export_name
        for export_name in forbidden_compat_exports
        if hasattr(graph_package, export_name)
    }

    assert leaked_exports == set()
