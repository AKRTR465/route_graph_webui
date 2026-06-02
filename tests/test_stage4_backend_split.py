from __future__ import annotations

import mission_export
from pathlib import Path

import graph_gui
from mission_export import config as mission_config
from mission_export import exporter as mission_exporter
from mission_export import group_context as mission_group_context
from mission_export import sampling as mission_sampling
from mission_export import smoothing as mission_smoothing
from webui_backend.routers import graphs, health, jobs, missions, plans, ui_state
from webui_backend.services import api_service


def test_mission_export_package_reexports_real_submodule_sources() -> None:
    assert mission_export.MissionExportOptions is mission_config.MissionExportOptions
    assert mission_export.build_mission_from_plan is mission_exporter.build_mission_from_plan
    assert mission_export.export_candidate_set_missions is mission_exporter.export_candidate_set_missions
    assert mission_export.NodeExportSettings is mission_group_context.NodeExportSettings
    assert mission_export._build_sampled_node_positions is mission_sampling._build_sampled_node_positions
    assert mission_export._build_smoothed_route_raw_points is mission_smoothing._build_smoothed_route_raw_points
    assert mission_export.MissionExportOptions.__module__ == "mission_export.config"
    assert mission_export.build_mission_from_plan.__module__ == "mission_export.exporter"


def test_backend_routers_own_endpoint_registration_and_delegate_to_service() -> None:
    routers = (health.router, ui_state.router, graphs.router, plans.router, jobs.router, missions.router)
    assert all(router.routes for router in routers)
    registered_paths = {route.path for router in routers for route in router.routes}
    assert "/api/graphs" in registered_paths
    assert "/api/plan/auto/jobs/{job_id}" in registered_paths
    assert "/api/missions/export" in registered_paths
    assert hasattr(api_service, "list_graphs")
    assert hasattr(api_service, "create_auto_plan_job")


def test_graph_gui_route_generation_uses_shared_job_service() -> None:
    source = Path(graph_gui.__file__).read_text(encoding="utf-8")
    assert "BackgroundJobService" in source
    assert "create_worker_job(" in source
    assert "launch_worker_runtime" not in source
    assert "tempfile.gettempdir" not in source
    assert "_route_generation_process" not in source
