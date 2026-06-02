from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mission_export import (
    DEFAULT_CORNER_MAX_YAW_STEP_DEG,
    DEFAULT_CORNER_MIN_ANGLE_DEG,
    DEFAULT_CORNER_RADIUS,
    DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
    DEFAULT_TURN_SMOOTHING_ENABLED,
    DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    DEFAULT_U_TURN_THRESHOLD_DEG,
    DEFAULT_U_TURN_TRANSITION_DISTANCE,
)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopedGraphRequest(StrictRequest):
    graph: str | None = None


class UpdateGraphUiStateRequest(ScopedGraphRequest):
    planner_inputs: dict[str, Any] = Field(default_factory=dict)
    group_inputs: dict[str, Any] = Field(default_factory=dict)
    auto_plan_inputs: dict[str, Any] = Field(default_factory=dict)
    export_inputs: dict[str, Any] = Field(default_factory=dict)


class GeneratePlanRequest(ScopedGraphRequest):
    start_node: str
    end_node: str
    via_nodes: list[str] = Field(default_factory=list)
    max_routes: int = Field(default=5, ge=1)
    max_edge_pass_factor: float = Field(default=2.5, ge=1.0)
    min_total_length: float | None = Field(default=None, gt=0.0)
    max_total_length: float | None = Field(default=None, gt=0.0)
    min_frame_count: int | None = Field(default=None, gt=0)
    max_frame_count: int | None = Field(default=None, gt=0)
    export_config: dict[str, Any] | None = None


class GenerateAutoPlanRequest(ScopedGraphRequest):
    max_output_routes: int = Field(default=20, ge=1)
    max_routes_per_pair: int = Field(default=3, ge=1)
    max_anchor_pairs_to_evaluate: int = Field(default=100, ge=1)
    min_frame_count: int | None = Field(default=None, gt=0)
    max_frame_count: int | None = Field(default=None, gt=0)
    distance_per_frame: float = Field(default=1.0, gt=0.0)
    min_total_length: float | None = Field(default=None, gt=0.0)
    max_total_length: float | None = Field(default=None, gt=0.0)
    max_edge_pass_factor: float = Field(default=2.5, ge=1.0)
    max_search_states: int = Field(default=50000, ge=1)
    min_endpoint_distance: float = Field(default=0.0, ge=0.0)
    prefer_connected_anchors: bool = True
    prefer_route_diversity: bool = True
    allow_reverse_direction_counterparts: bool = True
    coverage_weight: float = Field(default=1.0, ge=0.0)
    diversity_weight: float = Field(default=0.45, ge=0.0)
    anchor_weight: float = Field(default=0.35, ge=0.0)
    reverse_penalty_weight: float = Field(default=0.2, ge=0.0)
    node_coverage_weight: float = Field(default=0.2, ge=0.0)
    endpoint_reuse_weight: float = Field(default=0.2, ge=0.0)
    allowed_route_group_colors: list[str] = Field(default_factory=list)
    excluded_endpoint_group_colors: list[str] = Field(default_factory=list)
    export_config: dict[str, Any] | None = None


class NodeMoveRequest(ScopedGraphRequest):
    node_id: str
    x: float
    y: float


class NodeUpdateRequest(ScopedGraphRequest):
    node_id: str
    name: str | None = None
    tags: list[str] | None = None
    yaw_hint: float | None = None
    sample_radius: float | None = None


class AddEdgeRequest(ScopedGraphRequest):
    from_node: str
    to_node: str
    bidirectional: bool = True
    edge_kind: str | None = None
    group_color: str | None = None


class UpdateEdgeRequest(ScopedGraphRequest):
    edge_id: str
    enabled: bool | None = None
    bidirectional: bool | None = None
    edge_kind: str | None = None
    group_color: str | None = None


class RemoveEdgeRequest(ScopedGraphRequest):
    edge_id: str


class RemoveEdgeBetweenRequest(ScopedGraphRequest):
    from_node: str
    to_node: str


class UpdateGraphGroupConfigRequest(ScopedGraphRequest):
    group_color: str | None = None
    group_config: dict[str, Any] = Field(default_factory=dict)
    bridge_color: str | None = None


class UpdateCanvasViewRequest(ScopedGraphRequest):
    rotation_quadrants: int = Field(default=0, ge=0, le=3)
    flip_horizontal: bool = False
    flip_vertical: bool = False


class SaveCandidateSetRequest(StrictRequest):
    candidate_set: dict[str, Any]
    file_name: str | None = None


class MissionExportConfigRequest(StrictRequest):
    step_distance: float = Field(default=60.0, gt=0.0)
    fps: float = Field(default=4.0, gt=0.0)
    altitude_mode: str = "fixed"
    fixed_z: float | None = None
    altitude_offset: float = 0.0
    takeoff_landing_relative_z: float | None = Field(default=None, ge=0.0)
    takeoff_landing_step_distance: float | None = Field(default=None, gt=0.0)
    node_sample_radius: float = Field(default=0.0, ge=0.0)
    random_seed: int | None = None
    turn_smoothing_enabled: bool = DEFAULT_TURN_SMOOTHING_ENABLED
    corner_radius: float = Field(default=DEFAULT_CORNER_RADIUS, gt=0.0)
    small_turn_yaw_blend_threshold_deg: float = Field(
        default=DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
        ge=0.0,
    )
    corner_min_angle_deg: float = Field(default=DEFAULT_CORNER_MIN_ANGLE_DEG, ge=0.0, lt=180.0)
    u_turn_threshold_deg: float = Field(default=DEFAULT_U_TURN_THRESHOLD_DEG, gt=0.0, le=180.0)
    u_turn_transition_distance: float = Field(default=DEFAULT_U_TURN_TRANSITION_DISTANCE, gt=0.0)
    corner_max_yaw_step_deg: float = Field(default=DEFAULT_CORNER_MAX_YAW_STEP_DEG, gt=0.0)
    u_turn_pivot_yaw_step_deg: float = Field(default=DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG, gt=0.0)


class ExportMissionsRequest(MissionExportConfigRequest):
    candidate_set: dict[str, Any]
    output_dir: str | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    candidate_id: str | None = None


class PreviewMissionRequest(MissionExportConfigRequest):
    candidate_set: dict[str, Any]
    candidate_id: str


class FrontendDistHealth(BaseModel):
    path: str
    exists: bool
    index_exists: bool


class DataDirHealth(BaseModel):
    path: str
    writable: bool


class GraphStoreHealth(BaseModel):
    root: str
    count: int = Field(ge=0)


class WorkerServiceHealth(BaseModel):
    worker_path: str
    worker_exists: bool
    runtime_root: str
    active_jobs: int = Field(ge=0)
    jobs_by_state: dict[str, int] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str
    frontend_dist: FrontendDistHealth
    data_dir: DataDirHealth
    graphs: GraphStoreHealth
    workers: dict[str, WorkerServiceHealth]


__all__ = [
    "AddEdgeRequest",
    "DataDirHealth",
    "ExportMissionsRequest",
    "FrontendDistHealth",
    "GenerateAutoPlanRequest",
    "GeneratePlanRequest",
    "GraphStoreHealth",
    "HealthResponse",
    "MissionExportConfigRequest",
    "NodeMoveRequest",
    "NodeUpdateRequest",
    "PreviewMissionRequest",
    "RemoveEdgeBetweenRequest",
    "RemoveEdgeRequest",
    "SaveCandidateSetRequest",
    "ScopedGraphRequest",
    "StrictRequest",
    "UpdateCanvasViewRequest",
    "UpdateEdgeRequest",
    "UpdateGraphGroupConfigRequest",
    "UpdateGraphUiStateRequest",
    "WorkerServiceHealth",
]
