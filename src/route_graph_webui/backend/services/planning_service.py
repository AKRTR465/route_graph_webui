from __future__ import annotations

from typing import Any, Mapping

from route_graph_webui.graph.conversion import candidate_to_plan
from route_graph_webui.graph.model import GraphSchemaError, RouteCandidateSet, RouteGraph
from route_graph_webui.graph.ui_state import read_graph_gui_export_inputs
from route_graph_webui.mission_export import MissionExportOptions, export_mission
from route_graph_webui.planning.auto_route_planner import auto_plan_routes
from route_graph_webui.planning.route_planner import generate_route_candidates


def resolve_manual_export_config(
    graph: RouteGraph,
    export_config: Mapping[str, Any] | None,
) -> MissionExportOptions:
    if export_config is not None:
        return MissionExportOptions.from_mapping(export_config)

    saved_export_inputs = read_graph_gui_export_inputs(graph.meta)
    if not saved_export_inputs:
        return MissionExportOptions()

    return MissionExportOptions.from_mapping(saved_export_inputs)


def candidate_frame_count(
    candidate_set: RouteCandidateSet,
    candidate_id: str,
    export_config: MissionExportOptions,
) -> int:
    plan = candidate_to_plan(candidate_set, candidate_id)
    mission = export_mission(
        plan,
        output_path=None,
        **export_config.to_mission_kwargs(),
    )
    return len(mission["positions"])


def annotate_candidate_frame_counts(
    candidate_set: RouteCandidateSet,
    export_config: MissionExportOptions,
) -> None:
    for candidate in candidate_set.candidates:
        candidate.meta["frame_count"] = int(
            candidate_frame_count(
                candidate_set,
                candidate.candidate_id,
                export_config,
            )
        )


def apply_manual_generation_filters(
    candidate_set: RouteCandidateSet,
    *,
    min_frame_count: int | None,
    max_frame_count: int | None,
) -> RouteCandidateSet:
    if min_frame_count is None and max_frame_count is None:
        return candidate_set

    filtered_candidates = []
    for candidate in candidate_set.candidates:
        frame_count = int(candidate.meta.get("frame_count", 0))
        if min_frame_count is not None and frame_count < min_frame_count:
            continue
        if max_frame_count is not None and frame_count > max_frame_count:
            continue
        filtered_candidates.append(candidate)

    candidate_set.candidates = filtered_candidates
    candidate_set.meta["min_frame_count"] = min_frame_count
    candidate_set.meta["max_frame_count"] = max_frame_count
    if not filtered_candidates:
        raise GraphSchemaError("当前帧数限制下没有可用候选轨迹。")

    for index, candidate in enumerate(candidate_set.candidates, start=1):
        candidate.rank = index
        candidate.selected = index == 1
    candidate_set.sync_selected_ids()
    return candidate_set


def filters_require_auto_keep(
    *,
    min_total_length: float | None,
    max_total_length: float | None,
    min_frame_count: int | None,
    max_frame_count: int | None,
) -> bool:
    return any(
        value is not None
        for value in (
            min_total_length,
            max_total_length,
            min_frame_count,
            max_frame_count,
        )
    )


def apply_auto_keep_to_candidate_set(candidate_set: RouteCandidateSet) -> None:
    for candidate in candidate_set.candidates:
        candidate.selected = True
    candidate_set.sync_selected_ids()
    candidate_set.meta["auto_keep_candidates"] = True


def generate_manual_candidate_set(
    graph: RouteGraph,
    *,
    start_node: str,
    end_node: str,
    via_nodes: list[str],
    max_routes: int,
    max_edge_pass_factor: float,
    min_total_length: float | None,
    max_total_length: float | None,
    min_frame_count: int | None,
    max_frame_count: int | None,
    export_config: Mapping[str, Any] | None,
) -> RouteCandidateSet:
    resolved_export_config = resolve_manual_export_config(graph, export_config)
    candidate_set = generate_route_candidates(
        graph,
        start_node,
        end_node,
        via=via_nodes,
        max_routes=max_routes,
        max_edge_pass_factor=max_edge_pass_factor,
        min_total_length=min_total_length,
        max_total_length=max_total_length,
    )
    annotate_candidate_frame_counts(candidate_set, resolved_export_config)
    candidate_set.meta["min_frame_count"] = min_frame_count
    candidate_set.meta["max_frame_count"] = max_frame_count
    candidate_set = apply_manual_generation_filters(
        candidate_set,
        min_frame_count=min_frame_count,
        max_frame_count=max_frame_count,
    )
    if filters_require_auto_keep(
        min_total_length=min_total_length,
        max_total_length=max_total_length,
        min_frame_count=min_frame_count,
        max_frame_count=max_frame_count,
    ):
        apply_auto_keep_to_candidate_set(candidate_set)
    return candidate_set


def generate_auto_candidate_set(
    graph: RouteGraph,
    *,
    config: Mapping[str, Any],
) -> RouteCandidateSet:
    return auto_plan_routes(graph, config=config)


__all__ = [
    "annotate_candidate_frame_counts",
    "apply_auto_keep_to_candidate_set",
    "apply_manual_generation_filters",
    "candidate_frame_count",
    "filters_require_auto_keep",
    "generate_auto_candidate_set",
    "generate_manual_candidate_set",
    "resolve_manual_export_config",
]
