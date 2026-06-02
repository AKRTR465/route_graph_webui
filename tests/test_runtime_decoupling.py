from __future__ import annotations

import builtins
import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"


class RuntimeDecouplingTests(unittest.TestCase):
    def test_pytest_process_uses_src_route_graph_webui_package(self) -> None:
        sys.modules.pop("route_graph_webui", None)
        package = importlib.import_module("route_graph_webui")
        package_file = Path(package.__file__).resolve()

        self.assertTrue(package_file.is_relative_to(SRC_ROOT.resolve()))
        self.assertNotEqual(package_file, (PROJECT_ROOT / "__init__.py").resolve())

    def test_canonical_runtime_import_does_not_need_legacy_project_root_markers(self) -> None:
        env = dict(os.environ)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import route_graph_webui.runtime_support.runtime as rt; "
                    "print(rt.ROUTE_GRAPH_WEBUI_DIR)"
                ),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(Path(result.stdout.strip()).resolve(), PROJECT_ROOT.resolve())

    def test_runtime_project_root_lookup_failure_does_not_mutate_sys_path(self) -> None:
        sys.modules.pop("route_graph_webui.runtime_support.runtime", None)
        runtime_module = importlib.import_module("route_graph_webui.runtime_support.runtime")

        self.assertTrue(hasattr(runtime_module, "timestamp_now"))
        self.assertTrue(hasattr(runtime_module, "KeyboardController"))
        self.assertIsNone(runtime_module.PROJECT_ROOT)

        before = list(sys.path)
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(os.environ, {"UAVMEM_PROJECT_ROOT": ""}, clear=False):
                with self.assertRaisesRegex(RuntimeError, "Unable to find project root"):
                    runtime_module.ensure_project_root(temp_dir)

        self.assertEqual(sys.path, before)
        self.assertIsNone(runtime_module.PROJECT_ROOT)

    def test_legacy_import_transition_does_not_need_external_helper_package(self) -> None:
        blocked_prefix = "_".join(["batch", "infer", "vln"])
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == blocked_prefix or name.startswith(f"{blocked_prefix}."):
                raise ModuleNotFoundError(name)
            return real_import(name, globals, locals, fromlist, level)

        for module_name in (
            "route_graph_webui.runtime_support.runtime",
            "route_graph_webui.runtime_support.bootstrap_paths",
            "route_graph_webui.runtime_support.env_registry",
            "route_graph_webui.planning.route_planner",
            "route_graph_webui.mission_export",
        ):
            sys.modules.pop(module_name, None)

        importlib.invalidate_caches()
        with mock.patch("builtins.__import__", side_effect=guarded_import):
            runtime_module = importlib.import_module("route_graph_webui.runtime_support.runtime")
            route_planner_module = importlib.import_module("route_graph_webui.planning.route_planner")
            mission_export_module = importlib.import_module("route_graph_webui.mission_export")

        self.assertTrue(hasattr(runtime_module, "timestamp_now"))
        self.assertTrue(hasattr(route_planner_module, "generate_route_candidates"))
        self.assertTrue(hasattr(mission_export_module, "export_candidate_set_missions"))
