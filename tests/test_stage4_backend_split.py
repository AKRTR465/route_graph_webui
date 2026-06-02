from __future__ import annotations

import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"


def test_mission_export_target_package_imports_from_src_skeleton() -> None:
    mission_export_package = importlib.import_module("route_graph_webui.mission_export")
    package_file = Path(mission_export_package.__file__).resolve()

    assert package_file.is_relative_to(SRC_ROOT.resolve())


def test_mission_export_target_package_owns_export_api_after_t06() -> None:
    mission_export_package = importlib.import_module("route_graph_webui.mission_export")
    owned_exports = {
        "MissionExportOptions",
        "NodeExportSettings",
        "build_mission_from_plan",
        "export_candidate_set_missions",
        "_build_sampled_node_positions",
        "_build_smoothed_route_raw_points",
    }
    present_exports = {
        export_name
        for export_name in owned_exports
        if hasattr(mission_export_package, export_name)
    }

    assert present_exports == owned_exports


def test_mission_export_cli_module_owns_public_entrypoint_after_wrapper_removal() -> None:
    cli_module = importlib.import_module("route_graph_webui.cli.mission_export")

    assert callable(cli_module.main)
    assert callable(cli_module.build_parser)
    assert not (PROJECT_ROOT / "mission_export.py").exists()


def test_backend_routers_own_endpoint_registration_and_delegate_to_service() -> None:
    graphs = importlib.import_module("route_graph_webui.backend.routers.graphs")
    health = importlib.import_module("route_graph_webui.backend.routers.health")
    jobs = importlib.import_module("route_graph_webui.backend.routers.jobs")
    missions = importlib.import_module("route_graph_webui.backend.routers.missions")
    plans = importlib.import_module("route_graph_webui.backend.routers.plans")
    ui_state = importlib.import_module("route_graph_webui.backend.routers.ui_state")
    api_service = importlib.import_module("route_graph_webui.backend.services.api_service")

    routers = (health.router, ui_state.router, graphs.router, plans.router, jobs.router, missions.router)
    assert all(router.routes for router in routers)
    registered_paths = {route.path for router in routers for route in router.routes}
    assert "/api/graphs" in registered_paths
    assert "/api/plan/auto/jobs/{job_id}" in registered_paths
    assert "/api/missions/export" in registered_paths
    assert hasattr(api_service, "list_graphs")
    assert hasattr(api_service, "create_auto_plan_job")


def test_graph_gui_route_generation_uses_shared_job_service() -> None:
    source = (PROJECT_ROOT / "src" / "route_graph_webui" / "cli" / "graph_gui.py").read_text(encoding="utf-8")
    assert "BackgroundJobService" in source
    assert "create_worker_job(" in source
    assert "launch_worker_runtime" not in source
    assert "tempfile.gettempdir" not in source
    assert "_route_generation_process" not in source
