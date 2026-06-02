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


import graph_gui as graph_gui_module
import takeoff_landing_repair as takeoff_landing_repair_module
import webui_backend.server as server_module
from graph_canvas_view import GRAPH_GUI_CANVAS_VIEW_DEFAULTS, sync_graph_gui_canvas_view
from graph_ui_state import (
    GRAPH_GUI_WEBUI_INPUTS_META_KEY,
    read_graph_gui_webui_inputs,
    write_graph_gui_webui_inputs,
)
from graph_record import (
    _consume_speed_adjustments,
    _load_or_create_graph,
    _resolve_output_path,
    _resolve_runtime_args,
    build_parser as build_graph_record_parser,
)
from graph_editor import (
    GraphEditor,
    INSERTED_NODE_SOURCE_EDGE_ID_META_KEY,
    INSERTED_NODE_SOURCE_EDGE_RATIO_META_KEY,
)
from graph_gui import (
    GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY,
    GRAPH_GUI_CANVAS_VIEW_META_KEY,
    GRAPH_GUI_EXPORT_INPUTS_META_KEY,
    PREVIEW_STATUS_STALE,
    PreviewStateModel,
    _load_validated_graph,
    _blend_hex_color,
    distance_point_to_segment,
    filters_require_auto_keep,
    format_auto_allowed_route_groups_status,
    format_auto_excluded_endpoint_groups_status,
    is_fixed_z_enabled,
    normalize_auto_group_selection,
    read_graph_gui_canvas_view,
    read_graph_gui_export_inputs,
    resolve_auto_endpoint_group_choices,
    resolve_canvas_edge_draw_style,
    resolve_graph_gui_canvas_view,
    resolve_export_options,
    resolve_max_total_length_text,
    resolve_max_frame_count_text,
    resolve_min_total_length_text,
    resolve_min_frame_count_text,
    resolve_node_sample_radius_override_text,
    read_graph_gui_auto_plan_inputs,
    write_graph_gui_canvas_view,
    write_graph_gui_auto_plan_inputs,
    write_graph_gui_export_inputs,
)
from json_store import (
    consume_jsonl_text as _consume_progress_messages,
    read_json_mapping_if_ready as _read_json_mapping_if_ready,
)
from graph_schema import (
    DEFAULT_BRIDGE_COLOR,
    DEFAULT_GROUP_COLOR,
    EDGE_GROUP_COLOR_META_KEY,
    EDGE_KIND_BRIDGE,
    EDGE_KIND_GROUP,
    EDGE_KIND_META_KEY,
    GraphEdge,
    GraphNode,
    GraphSchemaError,
    GRAPH_BRIDGE_STYLE_META_KEY,
    GRAPH_GROUP_CONFIGS_META_KEY,
    NODE_SAMPLE_RADIUS_META_KEY,
    RouteCandidate,
    RouteEdgePass,
    RouteGraph,
    RoutePlan,
    RouteSegment,
    candidate_to_plan,
    derive_graph_color_grouping,
    ensure_valid_grouped_graph_for_routes,
    ensure_valid_plan,
    get_edge_group_color,
    get_edge_kind,
    load_graph,
    read_graph_bridge_style,
    read_graph_group_configs,
    physical_edge_key,
    validate_graph,
    write_graph_bridge_style,
    write_graph_group_configs,
)
from mission_export import build_mission_from_plan
from mission_export import export_candidate_set_missions
from mission_repair import merge_repair_images, repair_mission_payload
from auto_route_planner import (
    AutoPlanningConfig,
    AutoPlanningExportConfig,
    AutoRoutePlanningError,
    auto_plan_routes,
    compute_anchor_node_scores,
)
from route_generation_worker import _FileMessageQueue, run_route_generation_task
from route_planner import RoutePlanningError, RoutePlanningProgress, generate_route_candidates
from runtime import (
    DEFAULT_RESET_LOCATION,
    DEFAULT_RESET_ROTATION,
    KeyboardController,
)
from visualize_graph import (
    CanvasViewState,
    build_canvas_projection,
    compute_canvas_view_center,
    compute_edge_pass_label_layout,
    inverse_canvas_view_position,
    project_point,
    render_graph_preview,
    transform_canvas_view_position,
    unproject_point,
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
