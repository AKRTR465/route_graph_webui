from __future__ import annotations

import ast
import argparse
import inspect
import json
import queue
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from route_graph_webui.storage import json_store as _json_store


from route_graph_webui.runtime_support import runtime as _runtime
from route_graph_webui.graph import canvas_view as _graph_canvas_view
from route_graph_webui.graph import conversion as _graph_conversion
from route_graph_webui.graph import editor as _graph_editor
from route_graph_webui.graph import grouping as _graph_grouping
from route_graph_webui.graph import io as _graph_io
from route_graph_webui.graph import meta as _graph_meta
from route_graph_webui.graph import model as _graph_model
from route_graph_webui.graph import ui_state as _graph_ui_state
from route_graph_webui.graph import validation as _graph_validation
from route_graph_webui.planning import auto_route_planner as auto_route_planner_module
from route_graph_webui.planning import route_planner as _route_planner
from route_graph_webui.apps.workers import route_generation as _route_generation_worker
from route_graph_webui.backend import server as server_module
from route_graph_webui.cli import graph_gui as graph_gui_module
from route_graph_webui.cli import graph_record as _graph_record
from route_graph_webui.cli import route_planner as _route_planner_cli
from route_graph_webui.cli import visualize_graph as _visualize_graph
import route_graph_webui.mission_export as _mission_export
from route_graph_webui.tools.mission import mission_repair as _mission_repair
from route_graph_webui.tools.mission import takeoff_landing_repair as takeoff_landing_repair_module


def _bind(module: Any, names: tuple[str, ...]) -> None:
    globals().update({name: getattr(module, name) for name in names})



_bind(_graph_canvas_view, ("GRAPH_GUI_CANVAS_VIEW_DEFAULTS", "sync_graph_gui_canvas_view"))
_bind(
    _graph_ui_state,
    (
        "GRAPH_GUI_WEBUI_INPUTS_META_KEY",
        "read_graph_gui_webui_inputs",
        "write_graph_gui_webui_inputs",
    ),
)
_bind(
    _graph_record,
    (
        "_consume_speed_adjustments",
        "_load_or_create_graph",
        "_resolve_output_path",
        "_resolve_runtime_args",
    ),
)
build_graph_record_parser = _graph_record.build_parser
_bind(
    _graph_editor,
    (
        "GraphEditor",
        "INSERTED_NODE_SOURCE_EDGE_ID_META_KEY",
        "INSERTED_NODE_SOURCE_EDGE_RATIO_META_KEY",
    ),
)
_bind(
    graph_gui_module,
    (
        "GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY",
        "GRAPH_GUI_CANVAS_VIEW_META_KEY",
        "GRAPH_GUI_EXPORT_INPUTS_META_KEY",
        "PREVIEW_STATUS_STALE",
        "PreviewStateModel",
        "_load_validated_graph",
        "_blend_hex_color",
        "distance_point_to_segment",
        "filters_require_auto_keep",
        "format_auto_allowed_route_groups_status",
        "format_auto_excluded_endpoint_groups_status",
        "is_fixed_z_enabled",
        "normalize_auto_group_selection",
        "read_graph_gui_canvas_view",
        "read_graph_gui_export_inputs",
        "resolve_auto_endpoint_group_choices",
        "resolve_canvas_edge_draw_style",
        "resolve_graph_gui_canvas_view",
        "resolve_export_options",
        "resolve_max_total_length_text",
        "resolve_max_frame_count_text",
        "resolve_min_total_length_text",
        "resolve_min_frame_count_text",
        "resolve_node_sample_radius_override_text",
        "read_graph_gui_auto_plan_inputs",
        "write_graph_gui_canvas_view",
        "write_graph_gui_auto_plan_inputs",
        "write_graph_gui_export_inputs",
    ),
)
_consume_progress_messages = _json_store.consume_jsonl_text
_read_json_mapping_if_ready = _json_store.read_json_mapping_if_ready
_bind(
    _graph_meta,
    (
        "DEFAULT_BRIDGE_COLOR",
        "DEFAULT_GROUP_COLOR",
        "EDGE_GROUP_COLOR_META_KEY",
        "EDGE_KIND_BRIDGE",
        "EDGE_KIND_GROUP",
        "EDGE_KIND_META_KEY",
        "GRAPH_BRIDGE_STYLE_META_KEY",
        "GRAPH_GROUP_CONFIGS_META_KEY",
        "NODE_SAMPLE_RADIUS_META_KEY",
    ),
)
_bind(
    _graph_model,
    (
        "GraphEdge",
        "GraphNode",
        "GraphSchemaError",
        "RouteCandidate",
        "RouteCandidateSet",
        "RouteEdgePass",
        "RouteGraph",
        "RoutePlan",
        "RouteSegment",
        "physical_edge_key",
    ),
)
_bind(_graph_conversion, ("candidate_to_plan",))
_bind(
    _graph_grouping,
    (
        "derive_graph_color_grouping",
        "get_edge_group_color",
        "get_edge_kind",
        "read_graph_bridge_style",
        "read_graph_group_configs",
        "write_graph_bridge_style",
        "write_graph_group_configs",
    ),
)
_bind(_graph_io, ("load_graph", "load_json", "save_graph"))
_bind(
    _graph_validation,
    (
        "ensure_valid_grouped_graph_for_routes",
        "ensure_valid_plan",
        "validate_graph",
    ),
)
_bind(
    _mission_export,
    (
        "MissionExportOptions",
        "build_mission_from_plan",
        "export_candidate_set_missions",
    ),
)
_bind(_mission_repair, ("merge_repair_images", "repair_mission_payload"))
_bind(
    auto_route_planner_module,
    (
        "AutoPlanningConfig",
        "AutoPlanningExportConfig",
        "AutoRoutePlanningError",
        "auto_plan_routes",
        "compute_anchor_node_scores",
    ),
)
_bind(_route_generation_worker, ("_FileMessageQueue", "run_route_generation_task"))
_bind(
    _route_planner,
    (
        "DEFAULT_MAX_EDGE_PASS_FACTOR",
        "DEFAULT_MAX_ROUTES",
        "RoutePlanningError",
        "RoutePlanningProgress",
        "generate_route_candidates",
    ),
)
build_route_planner_parser = _route_planner_cli.build_parser
_bind(_runtime, ("DEFAULT_RESET_LOCATION", "DEFAULT_RESET_ROTATION", "KeyboardController"))
_bind(
    _visualize_graph,
    (
        "CanvasViewState",
        "build_canvas_projection",
        "compute_canvas_view_center",
        "compute_edge_pass_label_layout",
        "inverse_canvas_view_position",
        "project_point",
        "render_graph_preview",
        "transform_canvas_view_position",
        "unproject_point",
    ),
)


def build_test_square_graph(
    *,
    env_id: str = "env",
    graph_name: str = "test_square_graph",
) -> RouteGraph:
    return RouteGraph(
        env_id=env_id,
        graph_name=graph_name,
        default_altitude=None,
        nodes=[
            GraphNode(id="N001", name="N001", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="N002", name="N002", position=[0.0, 100.0, 0.0], yaw_hint=90.0),
            GraphNode(id="N003", name="N003", position=[100.0, 100.0, 0.0], yaw_hint=0.0),
            GraphNode(id="N004", name="N004", position=[100.0, 0.0, 0.0], yaw_hint=-90.0),
        ],
        edges=[
            GraphEdge(id="E001", from_node="N001", to_node="N004", weight=100.0, bidirectional=True),
            GraphEdge(id="E002", from_node="N001", to_node="N003", weight=141.421356, bidirectional=True),
            GraphEdge(id="E003", from_node="N003", to_node="N004", weight=100.0, bidirectional=True),
            GraphEdge(id="E004", from_node="N001", to_node="N002", weight=100.0, bidirectional=True),
            GraphEdge(id="E005", from_node="N002", to_node="N003", weight=100.0, bidirectional=True),
        ],
    )


def build_repeated_sampling_plan() -> RoutePlan:
    return RoutePlan(
        env_id="env",
        graph_name="repeated_sampling_plan",
        anchor_nodes=["A", "D"],
        planned_nodes=["A", "B", "C", "A", "B", "D"],
        segments=[
            RouteSegment(
                start_anchor="A",
                end_anchor="D",
                node_ids=["A", "B", "C", "A", "B", "D"],
                edge_ids=["E001", "E002", "E003", "E004", "E005"],
                length=500.0,
            )
        ],
        total_length=500.0,
        node_lookup={
            "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            "B": GraphNode(id="B", name="B", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
            "C": GraphNode(id="C", name="C", position=[100.0, 100.0, 0.0], yaw_hint=90.0),
            "D": GraphNode(id="D", name="D", position=[200.0, 0.0, 0.0], yaw_hint=0.0),
        },
    )


def build_group_bridge_graph() -> RouteGraph:
    return RouteGraph(
        env_id="env",
        graph_name="group_bridge_graph",
        default_altitude=None,
        nodes=[
            GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="B", name="B", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="C", name="C", position=[200.0, 0.0, 100.0], yaw_hint=0.0),
            GraphNode(id="D", name="D", position=[300.0, 0.0, 100.0], yaw_hint=0.0),
        ],
        edges=[
            GraphEdge(
                id="E_RED",
                from_node="A",
                to_node="B",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#FF0000"},
            ),
            GraphEdge(
                id="E_BRIDGE",
                from_node="B",
                to_node="C",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_BRIDGE},
            ),
            GraphEdge(
                id="E_BLUE",
                from_node="C",
                to_node="D",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#00AAFF"},
            ),
        ],
    )


def build_three_group_corridor_graph() -> RouteGraph:
    return RouteGraph(
        env_id="env",
        graph_name="three_group_corridor_graph",
        default_altitude=None,
        nodes=[
            GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="B", name="B", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="C", name="C", position=[200.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="D", name="D", position=[300.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="E", name="E", position=[400.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="F", name="F", position=[500.0, 0.0, 0.0], yaw_hint=0.0),
        ],
        edges=[
            GraphEdge(
                id="E_RED",
                from_node="A",
                to_node="B",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#FF0000"},
            ),
            GraphEdge(
                id="E_RED_TO_GREEN",
                from_node="B",
                to_node="C",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_BRIDGE},
            ),
            GraphEdge(
                id="E_GREEN",
                from_node="C",
                to_node="D",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#00FF00"},
            ),
            GraphEdge(
                id="E_GREEN_TO_BLUE",
                from_node="D",
                to_node="E",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_BRIDGE},
            ),
            GraphEdge(
                id="E_BLUE",
                from_node="E",
                to_node="F",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#0000FF"},
            ),
        ],
    )


def build_crossing_two_edge_graph(
    *,
    edge_a_meta: dict | None = None,
    edge_b_meta: dict | None = None,
) -> RouteGraph:
    return RouteGraph(
        env_id="env",
        graph_name="crossing_two_edge_graph",
        default_altitude=None,
        nodes=[
            GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="B", name="B", position=[0.0, 100.0, 0.0], yaw_hint=0.0),
            GraphNode(id="C", name="C", position=[100.0, 100.0, 0.0], yaw_hint=0.0),
            GraphNode(id="D", name="D", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
        ],
        edges=[
            GraphEdge(
                id="E_AC",
                from_node="A",
                to_node="C",
                weight=141.421356,
                bidirectional=True,
                meta=dict(edge_a_meta or {}),
            ),
            GraphEdge(
                id="E_BD",
                from_node="B",
                to_node="D",
                weight=141.421356,
                bidirectional=True,
                meta=dict(edge_b_meta or {}),
            ),
        ],
    )


def write_json_file(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def build_simple_repair_plan(
    *,
    env_id: str = "UnrealTrack-Venice-ContinuousColor-v0",
    graph_name: str = "simple_repair_graph",
) -> RoutePlan:
    graph = RouteGraph(
        env_id=env_id,
        graph_name=graph_name,
        default_altitude=None,
        nodes=[
            GraphNode(id="A", name="A", position=[0.0, 0.0, 100.0], yaw_hint=0.0),
            GraphNode(id="B", name="B", position=[100.0, 0.0, 100.0], yaw_hint=0.0),
        ],
        edges=[
            GraphEdge(id="E001", from_node="A", to_node="B", weight=100.0, bidirectional=True),
        ],
    )
    candidate_set = generate_route_candidates(graph, "A", "B", max_routes=1)
    return candidate_to_plan(candidate_set, "C001")


def build_manual_filter_graph() -> RouteGraph:
    return RouteGraph(
        env_id="env",
        graph_name="manual_filter_graph",
        default_altitude=0.0,
        nodes=[
            GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="B", name="B", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="C", name="C", position=[200.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="D", name="D", position=[100.0, 100.0, 0.0], yaw_hint=0.0),
        ],
        edges=[
            GraphEdge(id="E_AC", from_node="A", to_node="C", weight=200.0, bidirectional=True),
            GraphEdge(id="E_AB", from_node="A", to_node="B", weight=100.0, bidirectional=True),
            GraphEdge(id="E_BC", from_node="B", to_node="C", weight=100.0, bidirectional=True),
            GraphEdge(id="E_AD", from_node="A", to_node="D", weight=141.421356, bidirectional=True),
            GraphEdge(id="E_DC", from_node="D", to_node="C", weight=141.421356, bidirectional=True),
        ],
    )



__all__ = [name for name in globals() if not name.startswith("__")]
