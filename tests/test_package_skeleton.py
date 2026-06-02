from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_canonical_package_skeleton_imports_from_editable_install() -> None:
    script = textwrap.dedent(
        """
        import json
        from importlib import import_module, resources

        package_names = [
            "route_graph_webui",
            "route_graph_webui.graph",
            "route_graph_webui.planning",
            "route_graph_webui.mission",
            "route_graph_webui.mission_export",
            "route_graph_webui.storage",
            "route_graph_webui.runtime_support",
            "route_graph_webui.shared",
            "route_graph_webui.cli",
            "route_graph_webui.apps.workers",
            "route_graph_webui.backend.routers",
            "route_graph_webui.backend.services",
            "route_graph_webui.tools.media",
            "route_graph_webui.tools.mission",
        ]

        for package_name in package_names:
            assert import_module(package_name).__name__ == package_name

        resource_text = (
            resources.files("route_graph_webui.resources")
            .joinpath("registered_env_ids.json")
            .read_text(encoding="utf-8")
        )
        payload = json.loads(resource_text)
        assert isinstance(payload["env_names"], list)
        assert "DowntownWest" in payload["env_names"]
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
