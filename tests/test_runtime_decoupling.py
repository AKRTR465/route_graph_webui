from __future__ import annotations

import builtins
import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class RuntimeDecouplingTests(unittest.TestCase):
    def test_runtime_and_dependents_import_without_external_helper_package(self) -> None:
        blocked_prefix = "_".join(["batch", "infer", "vln"])
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == blocked_prefix or name.startswith(f"{blocked_prefix}."):
                raise ModuleNotFoundError(name)
            return real_import(name, globals, locals, fromlist, level)

        for module_name in (
            "runtime",
            "route_planner",
            "mission_export",
            "bootstrap_paths",
            "env_registry",
        ):
            sys.modules.pop(module_name, None)

        importlib.invalidate_caches()
        with mock.patch("builtins.__import__", side_effect=guarded_import):
            runtime_module = importlib.import_module("runtime")
            route_planner_module = importlib.import_module("route_planner")
            mission_export_module = importlib.import_module("mission_export")

        self.assertTrue(hasattr(runtime_module, "timestamp_now"))
        self.assertTrue(hasattr(route_planner_module, "generate_route_candidates"))
        self.assertTrue(hasattr(mission_export_module, "export_candidate_set_missions"))

    def test_webui_modules_import_from_standalone_copy_without_parent_repo_markers(self) -> None:
        source_root = Path(__file__).resolve().parents[1]
        module_names = (
            "route_planner",
            "mission_export",
            "auto_route_planner",
            "route_generation_worker",
            "webui_backend",
            "webui_backend.server",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            standalone_root = Path(temp_dir) / "route_graph_webui"
            standalone_root.mkdir(parents=True, exist_ok=True)

            for source_file in source_root.glob("*.py"):
                shutil.copy2(source_file, standalone_root / source_file.name)
            for package_name in ("mission_export", "webui_backend"):
                shutil.copytree(
                    source_root / package_name,
                    standalone_root / package_name,
                    ignore=shutil.ignore_patterns("__pycache__"),
                )

            for module_name in module_names:
                sys.modules.pop(module_name, None)

            sys.path.insert(0, str(standalone_root))
            try:
                imported_modules = [importlib.import_module(module_name) for module_name in module_names]
            finally:
                sys.path.pop(0)
                for module_name in module_names:
                    sys.modules.pop(module_name, None)

        self.assertTrue(hasattr(imported_modules[0], "generate_route_candidates"))
        self.assertTrue(hasattr(imported_modules[1], "export_candidate_set_missions"))
        self.assertTrue(hasattr(imported_modules[-1], "app"))
