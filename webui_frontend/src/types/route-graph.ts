export type {
  AutoPlanJobProgress,
  AutoPlanJobStatus,
  CandidateSaveResponse,
  GraphCatalogResponse,
  GraphEdge,
  GraphEnvelope,
  GraphNode,
  GraphSummary,
  MissionExportResponse,
  MissionPosition,
  MissionPositionState,
  MissionPreview,
  MissionPreviewResponse,
  MissionRouteMeta,
  Position3,
  RouteCandidate,
  RouteCandidateSet,
  RouteEdgePass,
  RouteGraph,
  RouteSegment,
  ValidationIssue,
  ValidationReport,
} from './api-contract'

export interface PlannerInputsState {
  planning_mode?: 'manual' | 'auto' | string
  max_routes?: string
  max_edge_pass_factor?: string
  min_total_length?: string
  max_total_length?: string
  min_frame_count?: string
  max_frame_count?: string
}

export interface GroupInputsState {
  active_group_color?: string
}

export interface AutoPlanInputsState {
  planning_mode?: 'manual' | 'auto' | string
  auto_max_output_routes?: string
  auto_max_routes_per_pair?: string
  auto_max_anchor_pairs_to_evaluate?: string
  auto_distance_per_frame?: string
  auto_min_total_length?: string
  auto_max_total_length?: string
  auto_min_frame_count?: string
  auto_max_frame_count?: string
  auto_min_endpoint_distance?: string
  auto_max_search_states?: string
  auto_coverage_weight?: string
  auto_diversity_weight?: string
  auto_anchor_weight?: string
  auto_reverse_penalty_weight?: string
  auto_node_coverage_weight?: string
  auto_endpoint_reuse_weight?: string
  auto_prefer_connected_anchors?: boolean
  auto_prefer_route_diversity?: boolean
  auto_allow_reverse_direction_counterparts?: boolean
  auto_enable_global_coverage?: boolean
  auto_allowed_route_group_colors?: string[]
  auto_excluded_endpoint_group_colors?: string[]
}

export interface ExportInputsState {
  step_distance?: string
  fps?: string
  random_seed?: string
  turn_smoothing_enabled?: boolean
  altitude_mode?: 'fixed' | 'follow_nodes' | string
  fixed_z?: string
  altitude_offset?: string
  takeoff_landing_relative_z?: string
  takeoff_landing_step_distance?: string
  node_sample_radius?: string
  corner_radius?: string
  small_turn_yaw_blend_threshold_deg?: string
  corner_min_angle_deg?: string
  u_turn_threshold_deg?: string
  u_turn_transition_distance?: string
  corner_max_yaw_step_deg?: string
  u_turn_pivot_yaw_step_deg?: string
  candidate_set_file_name?: string
  missions_output_dir?: string
}

export interface GroupConfigInputsState {
  label?: string
  altitude_mode?: 'fixed' | 'follow_nodes' | string
  fixed_z?: string
  altitude_offset?: string
  node_sample_radius?: string
  takeoff_landing_relative_z?: string
  takeoff_landing_step_distance?: string
}

export interface GroupEditorState {
  bridge_color: string
  group_configs: Record<string, GroupConfigInputsState>
}

export interface GraphUiState {
  planner_inputs: PlannerInputsState
  group_inputs: GroupInputsState
  auto_plan_inputs: AutoPlanInputsState
  export_inputs: ExportInputsState
}

export type MissionPreviewStatus = 'no_candidate' | 'stale' | 'cached' | 'ready' | 'error'
