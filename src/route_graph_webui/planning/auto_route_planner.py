from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from route_graph_webui.graph.grouping import (
    GraphColorGrouping,
    derive_graph_color_grouping,
    normalize_hex_color,
    read_graph_group_configs,
)
from route_graph_webui.graph.meta import GRAPH_GROUP_CONFIGS_META_KEY
from route_graph_webui.graph.model import (
    GraphEdge,
    GraphSchemaError,
    RouteCandidate,
    RouteCandidateSet,
    RouteGraph,
    RoutePlan,
    clone_graph_node,
    physical_edge_key,
)
from route_graph_webui.shared.geometry import distance_3d
from route_graph_webui.mission_export import (
    DEFAULT_CORNER_MAX_YAW_STEP_DEG,
    DEFAULT_CORNER_MIN_ANGLE_DEG,
    DEFAULT_CORNER_RADIUS,
    DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
    DEFAULT_TURN_SMOOTHING_ENABLED,
    DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
    DEFAULT_U_TURN_THRESHOLD_DEG,
    DEFAULT_U_TURN_TRANSITION_DISTANCE,
    MissionExportOptions,
    build_mission_from_plan,
    parse_bool_config,
)
from route_graph_webui.planning.route_planner import (
    PathResult,
    RoutePlanningError,
    compute_shortest_route,
    generate_route_candidates,
    prepare_candidate_set_graph_context,
)


AUTO_ROUTE_SEARCH_OVERSAMPLE_FACTOR = 4


@dataclass(frozen=True, slots=True)
class AutoPlanningProgress:
    phase: str
    pairs_considered: int
    max_pairs_to_evaluate: int
    valid_pairs_found: int
    candidate_pool_size: int
    selected_routes: int
    max_output_routes: int
    done: bool
    searched_candidates: int = 0
    filtered_candidates: int = 0
    kept_candidates: int = 0


@dataclass(frozen=True, slots=True)
class AutoPlanningPair:
    start: str
    end: str
    shortest_length: float
    endpoint_distance: float
    start_degree: int
    end_degree: int
    pair_score: float


@dataclass(frozen=True, slots=True)
class AutoPlanningExportConfig(MissionExportOptions):
    pass


@dataclass(slots=True)
class AutoPlanningConfig:
    max_output_routes: int = 20
    max_routes_per_pair: int = 3
    max_anchor_pairs_to_evaluate: int = 100
    min_frame_count: int | None = None
    max_frame_count: int | None = None
    distance_per_frame: float = 1.0
    min_total_length: float | None = None
    max_total_length: float | None = None
    max_edge_pass_factor: float = 2.5
    max_search_states: int = 50000
    min_endpoint_distance: float = 0.0
    prefer_connected_anchors: bool = True
    prefer_route_diversity: bool = True
    allow_reverse_direction_counterparts: bool = True
    coverage_weight: float = 1.0
    diversity_weight: float = 0.45
    anchor_weight: float = 0.35
    reverse_penalty_weight: float = 0.2
    node_coverage_weight: float = 0.2
    endpoint_reuse_weight: float = 0.2
    progress_interval: int = 25
    allowed_route_group_colors: tuple[str, ...] = ()
    excluded_endpoint_group_colors: tuple[str, ...] = ()
    export_config: AutoPlanningExportConfig | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> "AutoPlanningConfig":
        source = dict(raw or {})
        export_config_raw = source.get("export_config")
        return cls(
            max_output_routes=int(source.get("max_output_routes", 20)),
            max_routes_per_pair=int(source.get("max_routes_per_pair", 3)),
            max_anchor_pairs_to_evaluate=int(source.get("max_anchor_pairs_to_evaluate", 100)),
            min_frame_count=(
                None if source.get("min_frame_count") in {None, ""} else int(source["min_frame_count"])
            ),
            max_frame_count=(
                None if source.get("max_frame_count") in {None, ""} else int(source["max_frame_count"])
            ),
            distance_per_frame=float(source.get("distance_per_frame", 1.0)),
            min_total_length=(
                None if source.get("min_total_length") in {None, ""} else float(source["min_total_length"])
            ),
            max_total_length=(
                None if source.get("max_total_length") in {None, ""} else float(source["max_total_length"])
            ),
            max_edge_pass_factor=float(source.get("max_edge_pass_factor", 2.5)),
            max_search_states=int(source.get("max_search_states", 50000)),
            min_endpoint_distance=float(source.get("min_endpoint_distance", 0.0)),
            prefer_connected_anchors=parse_bool_config(
                source.get("prefer_connected_anchors", True),
                field_name="prefer_connected_anchors",
            ),
            prefer_route_diversity=parse_bool_config(
                source.get("prefer_route_diversity", True),
                field_name="prefer_route_diversity",
            ),
            allow_reverse_direction_counterparts=parse_bool_config(
                source.get("allow_reverse_direction_counterparts", True),
                field_name="allow_reverse_direction_counterparts",
            ),
            coverage_weight=float(source.get("coverage_weight", 1.0)),
            diversity_weight=float(source.get("diversity_weight", 0.45)),
            anchor_weight=float(source.get("anchor_weight", 0.35)),
            reverse_penalty_weight=float(source.get("reverse_penalty_weight", 0.2)),
            node_coverage_weight=float(source.get("node_coverage_weight", 0.2)),
            endpoint_reuse_weight=float(source.get("endpoint_reuse_weight", 0.2)),
            progress_interval=int(source.get("progress_interval", 25)),
            allowed_route_group_colors=_normalize_group_color_sequence(
                source.get("allowed_route_group_colors"),
                field_name="`allowed_route_group_colors`",
            ),
            excluded_endpoint_group_colors=_normalize_group_color_sequence(
                source.get("excluded_endpoint_group_colors"),
                field_name="`excluded_endpoint_group_colors`",
            ),
            export_config=(
                None
                if export_config_raw is None or export_config_raw == ""
                else AutoPlanningExportConfig.from_mapping(export_config_raw)
            ),
        )

    def effective_length_bounds(self) -> tuple[float | None, float | None]:
        frame_min_length = None
        frame_max_length = None
        if self.min_frame_count is not None:
            frame_min_length = float(self.min_frame_count) * float(self.distance_per_frame)
        if self.max_frame_count is not None:
            frame_max_length = float(self.max_frame_count) * float(self.distance_per_frame)
        effective_min = self.min_total_length
        effective_max = self.max_total_length
        if frame_min_length is not None:
            effective_min = frame_min_length if effective_min is None else max(effective_min, frame_min_length)
        if frame_max_length is not None:
            effective_max = frame_max_length if effective_max is None else min(effective_max, frame_max_length)
        return effective_min, effective_max

    def search_length_bounds(self) -> tuple[float | None, float | None]:
        if self.export_config is not None:
            return self.min_total_length, self.max_total_length
        return self.effective_length_bounds()

    def scoring_length_bounds(self) -> tuple[float | None, float | None]:
        if self.export_config is not None:
            return self.min_total_length, self.max_total_length
        return self.effective_length_bounds()

    def uses_export_frame_estimation(self) -> bool:
        return self.export_config is not None

    def has_frame_constraints(self) -> bool:
        return self.min_frame_count is not None or self.max_frame_count is not None

    def search_routes_per_pair(self) -> int:
        return max(
            int(self.max_routes_per_pair),
            int(self.max_routes_per_pair) * AUTO_ROUTE_SEARCH_OVERSAMPLE_FACTOR,
        )


@dataclass(slots=True)
class _AutoCandidateRecord:
    candidate: RouteCandidate
    pair: AutoPlanningPair
    base_score: float
    directed_signature: tuple[tuple[str, str, str], ...]
    physical_signature: tuple[tuple[str, str], ...]
    node_signature: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _AutoCandidatePoolResult:
    records: list[_AutoCandidateRecord]
    searched_candidates: int
    filtered_candidates: int


@dataclass(frozen=True, slots=True)
class _CandidateExportEstimate:
    frame_count: int
    total_length: float


class AutoRoutePlanningError(ValueError):
    """Raised when automatic route planning cannot produce candidates."""


class _CoverageStats:
    def __init__(self) -> None:
        self.directed_edge_counts: dict[tuple[str, str, str], int] = {}
        self.physical_edge_counts: dict[tuple[str, str], int] = {}
        self.node_counts: dict[str, int] = {}
        self.start_counts: dict[str, int] = {}
        self.end_counts: dict[str, int] = {}

    def add_candidate(self, candidate: RouteCandidate) -> None:
        for edge_pass in candidate.edge_passes:
            directed_key = edge_pass.signature()
            self.directed_edge_counts[directed_key] = self.directed_edge_counts.get(directed_key, 0) + 1
            physical_key = physical_edge_key(edge_pass.from_node, edge_pass.to_node)
            self.physical_edge_counts[physical_key] = self.physical_edge_counts.get(physical_key, 0) + 1
        for node_id in candidate.planned_nodes:
            self.node_counts[node_id] = self.node_counts.get(node_id, 0) + 1
        start_node = candidate.meta.get("auto_start_node")
        end_node = candidate.meta.get("auto_end_node")
        if isinstance(start_node, str):
            self.start_counts[start_node] = self.start_counts.get(start_node, 0) + 1
        if isinstance(end_node, str):
            self.end_counts[end_node] = self.end_counts.get(end_node, 0) + 1


def _normalize_group_color_sequence(
    raw_value: Any,
    *,
    field_name: str,
) -> tuple[str, ...]:
    if raw_value is None or raw_value == "":
        return ()
    if isinstance(raw_value, str):
        raw_items = [raw_value]
    elif isinstance(raw_value, Mapping):
        raise AutoRoutePlanningError(f"{field_name} must be a list of group colors")
    else:
        try:
            raw_items = list(raw_value)
        except TypeError as exc:
            raise AutoRoutePlanningError(f"{field_name} must be a list of group colors") from exc

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if item is None:
            continue
        if isinstance(item, str) and not item.strip():
            continue
        try:
            color = normalize_hex_color(item, field_name=field_name)
        except GraphSchemaError as exc:
            raise AutoRoutePlanningError(str(exc)) from exc
        if color in seen:
            continue
        seen.add(color)
        normalized.append(color)
    return tuple(normalized)


def _validate_config(config: AutoPlanningConfig) -> None:
    if config.max_output_routes < 1:
        raise AutoRoutePlanningError("`max_output_routes` must be at least 1")
    if config.max_routes_per_pair < 1:
        raise AutoRoutePlanningError("`max_routes_per_pair` must be at least 1")
    if config.max_anchor_pairs_to_evaluate < 1:
        raise AutoRoutePlanningError("`max_anchor_pairs_to_evaluate` must be at least 1")
    if config.distance_per_frame <= 0:
        raise AutoRoutePlanningError("`distance_per_frame` must be positive")
    if config.min_frame_count is not None and config.min_frame_count <= 0:
        raise AutoRoutePlanningError("`min_frame_count` must be positive")
    if config.max_frame_count is not None and config.max_frame_count <= 0:
        raise AutoRoutePlanningError("`max_frame_count` must be positive")
    if (
        config.min_frame_count is not None
        and config.max_frame_count is not None
        and config.min_frame_count > config.max_frame_count
    ):
        raise AutoRoutePlanningError("`min_frame_count` must be less than or equal to `max_frame_count`")
    if config.min_total_length is not None and config.min_total_length <= 0:
        raise AutoRoutePlanningError("`min_total_length` must be positive")
    if config.max_total_length is not None and config.max_total_length <= 0:
        raise AutoRoutePlanningError("`max_total_length` must be positive")
    effective_min, effective_max = config.search_length_bounds()
    if effective_min is not None and effective_max is not None and effective_min > effective_max:
        raise AutoRoutePlanningError("Frame constraints and length constraints have empty intersection")
    config.allowed_route_group_colors = _normalize_group_color_sequence(
        config.allowed_route_group_colors,
        field_name="`allowed_route_group_colors`",
    )
    config.excluded_endpoint_group_colors = _normalize_group_color_sequence(
        config.excluded_endpoint_group_colors,
        field_name="`excluded_endpoint_group_colors`",
    )
    if config.export_config is not None and not isinstance(config.export_config, AutoPlanningExportConfig):
        config.export_config = AutoPlanningExportConfig.from_mapping(config.export_config)
    if config.export_config is not None:
        _validate_export_config(config.export_config)


def _validate_export_config(config: AutoPlanningExportConfig) -> None:
    if config.step_distance <= 0:
        raise AutoRoutePlanningError("`export_config.step_distance` must be positive")
    if config.fps <= 0:
        raise AutoRoutePlanningError("`export_config.fps` must be positive")
    if config.altitude_mode not in {"fixed", "follow_nodes"}:
        raise AutoRoutePlanningError("`export_config.altitude_mode` must be either `fixed` or `follow_nodes`")
    if config.node_sample_radius < 0:
        raise AutoRoutePlanningError("`export_config.node_sample_radius` must be non-negative")
    if (
        config.takeoff_landing_relative_z is not None
        and float(config.takeoff_landing_relative_z) < 0
    ):
        raise AutoRoutePlanningError("`export_config.takeoff_landing_relative_z` must be non-negative")
    if (
        config.takeoff_landing_step_distance is not None
        and float(config.takeoff_landing_step_distance) <= 0
    ):
        raise AutoRoutePlanningError("`export_config.takeoff_landing_step_distance` must be positive")
    if config.corner_radius <= 0:
        raise AutoRoutePlanningError("`export_config.corner_radius` must be positive")
    if config.small_turn_yaw_blend_threshold_deg < 0:
        raise AutoRoutePlanningError(
            "`export_config.small_turn_yaw_blend_threshold_deg` must be non-negative"
        )
    if config.corner_min_angle_deg < 0 or config.corner_min_angle_deg >= 180:
        raise AutoRoutePlanningError("`export_config.corner_min_angle_deg` must be in [0, 180)")
    if (
        config.u_turn_threshold_deg <= config.corner_min_angle_deg
        or config.u_turn_threshold_deg > 180
    ):
        raise AutoRoutePlanningError(
            "`export_config.u_turn_threshold_deg` must be greater than "
            "`export_config.corner_min_angle_deg` and at most 180"
        )
    if config.u_turn_transition_distance <= 0:
        raise AutoRoutePlanningError("`export_config.u_turn_transition_distance` must be positive")
    if config.corner_max_yaw_step_deg <= 0:
        raise AutoRoutePlanningError("`export_config.corner_max_yaw_step_deg` must be positive")
    if config.u_turn_pivot_yaw_step_deg <= 0:
        raise AutoRoutePlanningError("`export_config.u_turn_pivot_yaw_step_deg` must be positive")


def _estimate_mission_total_length(positions: Iterable[Mapping[str, Any]]) -> float:
    previous_xyz: list[float] | None = None
    total_length = 0.0
    for position in positions:
        state = position.get("state")
        if not isinstance(state, list) or not state:
            continue
        xyz = state[0]
        if not isinstance(xyz, list) or len(xyz) != 3:
            continue
        current_xyz = [float(xyz[0]), float(xyz[1]), float(xyz[2])]
        if previous_xyz is not None:
            dx = current_xyz[0] - previous_xyz[0]
            dy = current_xyz[1] - previous_xyz[1]
            dz = current_xyz[2] - previous_xyz[2]
            total_length += math.sqrt((dx * dx) + (dy * dy) + (dz * dz))
        previous_xyz = current_xyz
    return total_length


class _AutoExportEstimator:
    def __init__(
        self,
        *,
        graph: RouteGraph,
        graph_context,
        export_config: AutoPlanningExportConfig,
    ) -> None:
        self._graph = graph
        self._graph_context = graph_context
        self._export_config = export_config
        self._estimate_by_signature: dict[tuple[tuple[str, str, str], ...], _CandidateExportEstimate] = {}

    def estimate(
        self,
        candidate: RouteCandidate,
        *,
        pair: AutoPlanningPair,
    ) -> _CandidateExportEstimate:
        signature = tuple(candidate.signature())
        cached = self._estimate_by_signature.get(signature)
        if cached is not None:
            return cached
        plan = RoutePlan(
            env_id=self._graph.env_id,
            graph_name=self._graph.graph_name,
            anchor_nodes=[pair.start, pair.end],
            planned_nodes=list(candidate.planned_nodes),
            segments=list(candidate.segments),
            total_length=float(candidate.total_length),
            edge_passes=list(candidate.edge_passes),
            node_lookup=self._graph_context.normalized_node_lookup,
            meta={
                **dict(self._graph_context.export_meta),
                "graph_default_altitude": dict(self._graph_context.export_meta).get("graph_default_altitude"),
                "candidate_id": candidate.candidate_id,
                "candidate_rank": int(candidate.rank),
                "selected": bool(candidate.selected),
                "candidate_meta": dict(candidate.meta),
            },
        )
        mission = build_mission_from_plan(
            plan,
            **self._export_config.to_mission_kwargs(),
        )
        estimate = _CandidateExportEstimate(
            frame_count=len(mission["positions"]),
            total_length=_estimate_mission_total_length(mission["positions"]),
        )
        self._estimate_by_signature[signature] = estimate
        return estimate


def _update_candidate_frame_estimate_meta(
    candidate: RouteCandidate,
    *,
    config: AutoPlanningConfig,
    export_estimate: _CandidateExportEstimate | None,
) -> int:
    if export_estimate is None:
        estimated_frames = int(round(float(candidate.total_length) / float(config.distance_per_frame)))
        frame_estimation_mode = "distance_per_frame"
        frame_estimation_step_distance = float(config.distance_per_frame)
    else:
        estimated_frames = int(export_estimate.frame_count)
        frame_estimation_mode = "export_mission"
        assert config.export_config is not None
        frame_estimation_step_distance = float(config.export_config.step_distance)
        candidate.meta["estimated_export_total_length"] = round(float(export_estimate.total_length), 6)
    candidate.meta.update(
        {
            "estimated_frames": estimated_frames,
            "distance_per_frame": float(config.distance_per_frame),
            "frame_estimation_mode": frame_estimation_mode,
            "frame_estimation_step_distance": frame_estimation_step_distance,
            "frame_count": estimated_frames,
        }
    )
    return estimated_frames


def _frame_count_satisfies_constraints(
    frame_count: int,
    *,
    config: AutoPlanningConfig,
) -> bool:
    if config.min_frame_count is not None and frame_count < int(config.min_frame_count):
        return False
    if config.max_frame_count is not None and frame_count > int(config.max_frame_count):
        return False
    return True


def _clone_graph_edge(edge: GraphEdge) -> GraphEdge:
    return GraphEdge(
        id=str(edge.id),
        from_node=str(edge.from_node),
        to_node=str(edge.to_node),
        weight=float(edge.weight),
        enabled=bool(edge.enabled),
        bidirectional=bool(edge.bidirectional),
        meta=dict(edge.meta),
    )


def _build_allowed_route_group_graph(
    graph: RouteGraph,
    *,
    config: AutoPlanningConfig,
) -> RouteGraph:
    if not config.allowed_route_group_colors:
        return graph

    grouping = derive_graph_color_grouping(graph)
    used_colors = set(grouping.group_edge_ids)
    invalid_colors = [
        color for color in config.allowed_route_group_colors
        if color not in used_colors
    ]
    if invalid_colors:
        invalid_text = ", ".join(invalid_colors)
        raise AutoRoutePlanningError(
            "Allowed route groups are not present in the current graph: "
            f"{invalid_text}"
        )

    allowed_colors = set(config.allowed_route_group_colors)
    allowed_node_ids = {
        node_id
        for node_id, color in grouping.node_group_lookup.items()
        if color in allowed_colors
    }
    if len(allowed_node_ids) < 2:
        raise AutoRoutePlanningError(
            "Allowed route groups leave fewer than two eligible nodes for auto planning"
        )

    filtered_group_configs = {
        color: dict(values)
        for color, values in read_graph_group_configs(graph.meta).items()
        if color in allowed_colors
    }
    filtered_meta = dict(graph.meta)
    filtered_meta[GRAPH_GROUP_CONFIGS_META_KEY] = filtered_group_configs

    return RouteGraph(
        env_id=graph.env_id,
        graph_name=graph.graph_name,
        default_altitude=graph.default_altitude,
        nodes=[
            clone_graph_node(node)
            for node in graph.nodes
            if node.id in allowed_node_ids
        ],
        edges=[
            _clone_graph_edge(edge)
            for edge in graph.edges
            if edge.from_node in allowed_node_ids and edge.to_node in allowed_node_ids
        ],
        meta=filtered_meta,
    )


def _node_degree_lookup(graph: RouteGraph) -> dict[str, int]:
    degree_lookup = {node.id: 0 for node in graph.nodes}
    for edge in graph.edges:
        if not edge.enabled:
            continue
        degree_lookup[edge.from_node] = degree_lookup.get(edge.from_node, 0) + 1
        degree_lookup[edge.to_node] = degree_lookup.get(edge.to_node, 0) + 1
        if edge.bidirectional:
            degree_lookup[edge.from_node] = degree_lookup.get(edge.from_node, 0) + 1
            degree_lookup[edge.to_node] = degree_lookup.get(edge.to_node, 0) + 1
    return degree_lookup


def compute_anchor_node_scores(graph: RouteGraph) -> dict[str, float]:
    degree_lookup = _node_degree_lookup(graph)
    max_degree = max(degree_lookup.values(), default=0)
    if max_degree <= 0:
        return {node_id: 0.0 for node_id in degree_lookup}
    return {node_id: float(degree) / float(max_degree) for node_id, degree in degree_lookup.items()}


def _endpoint_distance(graph: RouteGraph, start: str, end: str) -> float:
    node_map = graph.node_map
    start_node = node_map[start]
    end_node = node_map[end]
    return distance_3d(start_node.position, end_node.position)


def _length_fit_score(length: float, min_length: float | None, max_length: float | None) -> float:
    if min_length is None and max_length is None:
        return 1.0
    if min_length is not None and max_length is not None:
        midpoint = (float(min_length) + float(max_length)) / 2.0
        spread = max((float(max_length) - float(min_length)) / 2.0, 1e-6)
        return max(0.0, 1.0 - abs(length - midpoint) / spread)
    target = float(min_length if min_length is not None else max_length)
    return 1.0 / (1.0 + abs(length - target) / max(target, 1.0))


def _enumerate_anchor_pairs(
    graph: RouteGraph,
    *,
    config: AutoPlanningConfig,
    grouping: GraphColorGrouping | None = None,
    progress_callback=None,
) -> tuple[list[AutoPlanningPair], dict[str, int], dict[str, float]]:
    node_degree_lookup = _node_degree_lookup(graph)
    anchor_scores = compute_anchor_node_scores(graph)
    effective_min, effective_max = config.search_length_bounds()
    node_ids = [node.id for node in graph.nodes if node_degree_lookup.get(node.id, 0) > 0]
    excluded_endpoint_colors = set(config.excluded_endpoint_group_colors)
    if excluded_endpoint_colors and grouping is not None:
        node_ids = [
            node_id
            for node_id in node_ids
            if grouping.node_group_lookup.get(node_id) not in excluded_endpoint_colors
        ]
        if len(node_ids) < 2:
            raise AutoRoutePlanningError(
                "Excluded endpoint groups leave fewer than two eligible endpoint nodes for auto planning"
            )
    scored_pairs: list[AutoPlanningPair] = []
    pairs_considered = 0
    valid_pairs = 0

    def publish_progress(*, done: bool = False) -> None:
        if progress_callback is None:
            return
        progress_callback(
            AutoPlanningProgress(
                phase="enumerating_pairs" if not done else "enumeration_completed",
                pairs_considered=pairs_considered,
                max_pairs_to_evaluate=max(len(node_ids) * max(len(node_ids) - 1, 0), 1),
                valid_pairs_found=valid_pairs,
                candidate_pool_size=0,
                selected_routes=0,
                max_output_routes=config.max_output_routes,
                done=done,
            )
        )

    publish_progress(done=False)
    for start in node_ids:
        for end in node_ids:
            if start == end:
                continue
            pairs_considered += 1
            endpoint_distance = _endpoint_distance(graph, start, end)
            if endpoint_distance + 1e-9 < float(config.min_endpoint_distance):
                continue
            try:
                shortest = compute_shortest_route(graph, [start, end])
            except RoutePlanningError:
                continue
            if effective_max is not None and shortest.length > effective_max + 1e-9:
                continue
            length_score = _length_fit_score(shortest.length, effective_min, effective_max)
            start_score = anchor_scores.get(start, 0.0) if config.prefer_connected_anchors else 0.0
            end_score = anchor_scores.get(end, 0.0) if config.prefer_connected_anchors else 0.0
            endpoint_score = 0.0 if endpoint_distance <= 0 else min(endpoint_distance / max(shortest.length, 1.0), 1.0)
            pair_score = (0.5 * length_score) + (config.anchor_weight * (start_score + end_score) / 2.0) + (0.15 * endpoint_score)
            scored_pairs.append(
                AutoPlanningPair(
                    start=start,
                    end=end,
                    shortest_length=float(shortest.length),
                    endpoint_distance=float(endpoint_distance),
                    start_degree=int(node_degree_lookup.get(start, 0)),
                    end_degree=int(node_degree_lookup.get(end, 0)),
                    pair_score=float(pair_score),
                )
            )
            valid_pairs += 1
            if pairs_considered % max(config.progress_interval, 1) == 0:
                publish_progress(done=False)

    scored_pairs.sort(
        key=lambda item: (
            -item.pair_score,
            -item.start_degree,
            -item.end_degree,
            -item.endpoint_distance,
            item.shortest_length,
            item.start,
            item.end,
        )
    )
    if not scored_pairs and excluded_endpoint_colors and grouping is not None:
        raise AutoRoutePlanningError(
            "No valid start/end pairs satisfy the current constraints after applying excluded endpoint groups"
        )
    publish_progress(done=True)
    return scored_pairs, node_degree_lookup, anchor_scores


def _report_progress(progress_callback, progress: AutoPlanningProgress) -> None:
    if progress_callback is not None:
        progress_callback(progress)


def _build_candidate_record(
    candidate: RouteCandidate,
    *,
    pair: AutoPlanningPair,
    config: AutoPlanningConfig,
    scoring_min_length: float | None,
    scoring_max_length: float | None,
    anchor_scores: Mapping[str, float],
    export_estimate: _CandidateExportEstimate | None = None,
) -> _AutoCandidateRecord:
    directed_signature = tuple(candidate.signature())
    physical_signature = tuple(
        physical_edge_key(from_node, to_node)
        for _edge_id, from_node, to_node in directed_signature
    )
    estimated_frames = _update_candidate_frame_estimate_meta(
        candidate,
        config=config,
        export_estimate=export_estimate,
    )
    fit_components: list[float] = []
    if scoring_min_length is not None or scoring_max_length is not None:
        fit_components.append(
            _length_fit_score(candidate.total_length, scoring_min_length, scoring_max_length)
        )
    if config.has_frame_constraints():
        fit_components.append(
            _length_fit_score(float(estimated_frames), config.min_frame_count, config.max_frame_count)
        )
    length_fit = 1.0 if not fit_components else sum(fit_components) / float(len(fit_components))
    anchor_score = (anchor_scores.get(pair.start, 0.0) + anchor_scores.get(pair.end, 0.0)) / 2.0
    base_score = (0.55 * length_fit) + (config.anchor_weight * anchor_score) + (0.15 * pair.pair_score)
    candidate.meta.update(
        {
            "generation_mode": "auto",
            "auto_start_node": pair.start,
            "auto_end_node": pair.end,
            "auto_pair_rank": 0,
            "auto_pair_score": round(float(pair.pair_score), 6),
            "auto_shortest_length": round(float(pair.shortest_length), 6),
            "start_degree": int(pair.start_degree),
            "end_degree": int(pair.end_degree),
            "coverage_base_score": round(float(base_score), 6),
        }
    )
    return _AutoCandidateRecord(
        candidate=candidate,
        pair=pair,
        base_score=float(base_score),
        directed_signature=directed_signature,
        physical_signature=physical_signature,
        node_signature=tuple(candidate.planned_nodes),
    )


def _build_candidate_pool(
    graph: RouteGraph,
    *,
    config: AutoPlanningConfig,
    scored_pairs: Iterable[AutoPlanningPair],
    anchor_scores: Mapping[str, float],
    export_estimator: _AutoExportEstimator | None = None,
    progress_callback=None,
) -> _AutoCandidatePoolResult:
    effective_min, effective_max = config.search_length_bounds()
    scoring_min_length, scoring_max_length = config.scoring_length_bounds()
    candidate_pool: list[_AutoCandidateRecord] = []
    seen_signatures: set[tuple[tuple[str, str, str], ...]] = set()
    pair_count = 0
    valid_pairs_found = 0
    searched_candidates = 0
    filtered_candidates = 0
    search_routes_per_pair = config.search_routes_per_pair()
    for pair in scored_pairs:
        if pair_count >= config.max_anchor_pairs_to_evaluate:
            break
        pair_count += 1
        try:
            candidate_set = generate_route_candidates(
                graph,
                start=pair.start,
                end=pair.end,
                max_routes=search_routes_per_pair,
                max_edge_pass_factor=config.max_edge_pass_factor,
                min_total_length=effective_min,
                max_total_length=effective_max,
                max_search_states=config.max_search_states,
            )
        except RoutePlanningError:
            continue
        valid_pairs_found += 1
        searched_candidates += len(candidate_set.candidates)
        kept_for_pair = 0
        for candidate in candidate_set.candidates:
            if kept_for_pair >= config.max_routes_per_pair:
                break
            signature = tuple(candidate.signature())
            if signature in seen_signatures:
                filtered_candidates += 1
                continue
            seen_signatures.add(signature)
            export_estimate: _CandidateExportEstimate | None = None
            if export_estimator is not None and config.has_frame_constraints():
                export_estimate = export_estimator.estimate(candidate, pair=pair)
                if not _frame_count_satisfies_constraints(
                    export_estimate.frame_count,
                    config=config,
                ):
                    filtered_candidates += 1
                    continue
            candidate_pool.append(
                _build_candidate_record(
                    candidate,
                    pair=pair,
                    config=config,
                    scoring_min_length=scoring_min_length,
                    scoring_max_length=scoring_max_length,
                    anchor_scores=anchor_scores,
                    export_estimate=export_estimate,
                )
            )
            kept_for_pair += 1
        _report_progress(
            progress_callback,
            AutoPlanningProgress(
                phase="planning_routes",
                pairs_considered=pair_count,
                max_pairs_to_evaluate=config.max_anchor_pairs_to_evaluate,
                valid_pairs_found=valid_pairs_found,
                candidate_pool_size=len(candidate_pool),
                selected_routes=0,
                max_output_routes=config.max_output_routes,
                done=False,
                searched_candidates=searched_candidates,
                filtered_candidates=filtered_candidates,
                kept_candidates=len(candidate_pool),
            ),
        )
    if not candidate_pool:
        if config.allowed_route_group_colors:
            raise AutoRoutePlanningError(
                "No valid auto-planned routes satisfy the current constraints after applying allowed route groups"
            )
        raise AutoRoutePlanningError("No valid auto-planned routes satisfy the current constraints")
    return _AutoCandidatePoolResult(
        records=candidate_pool,
        searched_candidates=searched_candidates,
        filtered_candidates=filtered_candidates,
    )


def _candidate_marginal_score(
    record: _AutoCandidateRecord,
    stats: _CoverageStats,
    *,
    config: AutoPlanningConfig,
) -> tuple[float, dict[str, float]]:
    new_directed_gain = 0.0
    directed_overlap = 0.0
    reverse_overlap = 0.0
    for directed_key, physical_key in zip(record.directed_signature, record.physical_signature):
        prior_directed = stats.directed_edge_counts.get(directed_key, 0)
        prior_physical = stats.physical_edge_counts.get(physical_key, 0)
        if prior_directed == 0:
            new_directed_gain += 1.0
        else:
            directed_overlap += 1.0 + (0.25 * prior_directed)
        if prior_physical > 0:
            reverse_overlap += 0.5 + (0.15 * prior_physical)
    new_node_gain = sum(1.0 for node_id in record.node_signature if stats.node_counts.get(node_id, 0) == 0)
    endpoint_reuse_penalty = float(stats.start_counts.get(record.pair.start, 0) + stats.end_counts.get(record.pair.end, 0))
    if config.prefer_route_diversity:
        diversity_penalty = directed_overlap
    else:
        diversity_penalty = directed_overlap * 0.25
    if config.allow_reverse_direction_counterparts:
        reverse_penalty = reverse_overlap * float(config.reverse_penalty_weight)
    else:
        reverse_penalty = reverse_overlap * max(float(config.reverse_penalty_weight), 1.0)
    score = (
        float(config.coverage_weight) * new_directed_gain
        + float(config.node_coverage_weight) * new_node_gain
        + record.base_score
        - float(config.diversity_weight) * diversity_penalty
        - reverse_penalty
        - float(config.endpoint_reuse_weight) * endpoint_reuse_penalty
    )
    return score, {
        "new_directed_edges": new_directed_gain,
        "new_nodes": new_node_gain,
        "directed_overlap": directed_overlap,
        "reverse_overlap": reverse_overlap,
        "endpoint_reuse": endpoint_reuse_penalty,
    }


def _select_candidates_globally(
    candidate_pool: list[_AutoCandidateRecord],
    *,
    config: AutoPlanningConfig,
    export_estimator: _AutoExportEstimator | None = None,
    progress_callback=None,
    searched_candidates: int = 0,
    filtered_candidates: int = 0,
) -> list[RouteCandidate]:
    selected_records: list[_AutoCandidateRecord] = []
    stats = _CoverageStats()
    remaining = list(candidate_pool)
    while remaining and len(selected_records) < config.max_output_routes:
        best_index = -1
        best_score = -float("inf")
        best_metrics: dict[str, float] | None = None
        for index, record in enumerate(remaining):
            score, metrics = _candidate_marginal_score(record, stats, config=config)
            if score > best_score + 1e-9:
                best_index = index
                best_score = score
                best_metrics = metrics
        if best_index < 0:
            break
        record = remaining.pop(best_index)
        metrics = best_metrics or {}
        record.candidate.meta.update(
            {
                "coverage_marginal_score": round(float(best_score), 6),
                "new_directed_edges_at_selection": int(metrics.get("new_directed_edges", 0.0)),
                "new_nodes_at_selection": int(metrics.get("new_nodes", 0.0)),
                "directed_edge_count": len(record.directed_signature),
                "physical_edge_count": len(set(record.physical_signature)),
            }
        )
        selected_records.append(record)
        stats.add_candidate(record.candidate)
        _report_progress(
            progress_callback,
            AutoPlanningProgress(
                phase="optimizing_coverage",
                pairs_considered=len(candidate_pool),
                max_pairs_to_evaluate=max(len(candidate_pool), 1),
                valid_pairs_found=len(candidate_pool),
                candidate_pool_size=len(candidate_pool),
                selected_routes=len(selected_records),
                max_output_routes=config.max_output_routes,
                done=False,
                searched_candidates=searched_candidates,
                filtered_candidates=filtered_candidates,
                kept_candidates=len(candidate_pool),
            ),
        )
    for index, record in enumerate(selected_records, start=1):
        if export_estimator is not None and not config.has_frame_constraints():
            export_estimate = export_estimator.estimate(record.candidate, pair=record.pair)
            _update_candidate_frame_estimate_meta(
                record.candidate,
                config=config,
                export_estimate=export_estimate,
            )
        record.candidate.rank = index
        record.candidate.selected = False
        record.candidate.meta["auto_pair_rank"] = int(index)
    return [record.candidate for record in selected_records]


def _assign_auto_candidate_ids(candidates: list[RouteCandidate]) -> None:
    for index, candidate in enumerate(candidates, start=1):
        candidate.candidate_id = f"AC{index:04d}"


def auto_plan_routes(
    graph: RouteGraph,
    config: AutoPlanningConfig | Mapping[str, Any] | None = None,
    *,
    progress_callback=None,
) -> RouteCandidateSet:
    resolved_config = config if isinstance(config, AutoPlanningConfig) else AutoPlanningConfig.from_mapping(config)
    _validate_config(resolved_config)
    if not graph.nodes:
        raise AutoRoutePlanningError("Route graph is empty")
    planning_graph = _build_allowed_route_group_graph(graph, config=resolved_config)
    graph_context = prepare_candidate_set_graph_context(planning_graph)
    export_estimator = (
        None
        if resolved_config.export_config is None
        else _AutoExportEstimator(
            graph=planning_graph,
            graph_context=graph_context,
            export_config=resolved_config.export_config,
        )
    )

    scored_pairs, node_degree_lookup, anchor_scores = _enumerate_anchor_pairs(
        planning_graph,
        config=resolved_config,
        grouping=graph_context.grouping,
        progress_callback=progress_callback,
    )
    if not scored_pairs:
        if resolved_config.allowed_route_group_colors:
            raise AutoRoutePlanningError(
                "No valid start/end pairs satisfy the current constraints after applying allowed route groups"
            )
        raise AutoRoutePlanningError("No valid start/end pairs satisfy the current constraints")

    candidate_pool_result = _build_candidate_pool(
        planning_graph,
        config=resolved_config,
        scored_pairs=scored_pairs,
        anchor_scores=anchor_scores,
        export_estimator=export_estimator,
        progress_callback=progress_callback,
    )
    candidate_pool = candidate_pool_result.records
    selected_candidates = _select_candidates_globally(
        candidate_pool,
        config=resolved_config,
        export_estimator=export_estimator,
        progress_callback=progress_callback,
        searched_candidates=candidate_pool_result.searched_candidates,
        filtered_candidates=candidate_pool_result.filtered_candidates,
    )
    if not selected_candidates:
        raise AutoRoutePlanningError("Auto planning did not produce any candidate routes")
    _assign_auto_candidate_ids(selected_candidates)
    selected_candidates[0].selected = True
    selected_candidate_ids = [selected_candidates[0].candidate_id]
    directed_coverage = {
        edge_pass.signature()
        for candidate in selected_candidates
        for edge_pass in candidate.edge_passes
    }
    physical_coverage = {
        physical_edge_key(edge_pass.from_node, edge_pass.to_node)
        for candidate in selected_candidates
        for edge_pass in candidate.edge_passes
    }
    covered_nodes = {node_id for candidate in selected_candidates for node_id in candidate.planned_nodes}
    effective_min, effective_max = resolved_config.search_length_bounds()
    meta = {
        **graph_context.export_meta,
        "planning_mode": "auto",
        "global_coverage_optimized": True,
        "candidate_pool_size": len(candidate_pool),
        "candidate_count": len(selected_candidates),
        "directed_edge_coverage_count": len(directed_coverage),
        "physical_edge_coverage_count": len(physical_coverage),
        "node_coverage_count": len(covered_nodes),
        "evaluated_pair_count": min(len(scored_pairs), resolved_config.max_anchor_pairs_to_evaluate),
        "valid_pair_count": len(scored_pairs),
        "max_output_routes": int(resolved_config.max_output_routes),
        "max_routes_per_pair": int(resolved_config.max_routes_per_pair),
        "search_routes_per_pair": int(resolved_config.search_routes_per_pair()),
        "route_search_oversample_factor": int(AUTO_ROUTE_SEARCH_OVERSAMPLE_FACTOR),
        "max_anchor_pairs_to_evaluate": int(resolved_config.max_anchor_pairs_to_evaluate),
        "min_frame_count": resolved_config.min_frame_count,
        "max_frame_count": resolved_config.max_frame_count,
        "distance_per_frame": float(resolved_config.distance_per_frame),
        "frame_estimation_mode": (
            "export_mission" if resolved_config.export_config is not None else "distance_per_frame"
        ),
        "frame_estimation_step_distance": float(
            resolved_config.distance_per_frame
            if resolved_config.export_config is None
            else resolved_config.export_config.step_distance
        ),
        "min_total_length": None if resolved_config.min_total_length is None else float(resolved_config.min_total_length),
        "max_total_length": None if resolved_config.max_total_length is None else float(resolved_config.max_total_length),
        "effective_min_length": None if effective_min is None else round(float(effective_min), 6),
        "effective_max_length": None if effective_max is None else round(float(effective_max), 6),
        "prefer_connected_anchors": bool(resolved_config.prefer_connected_anchors),
        "prefer_route_diversity": bool(resolved_config.prefer_route_diversity),
        "allow_reverse_direction_counterparts": bool(resolved_config.allow_reverse_direction_counterparts),
        "coverage_selection_weights": {
            "coverage_weight": float(resolved_config.coverage_weight),
            "diversity_weight": float(resolved_config.diversity_weight),
            "anchor_weight": float(resolved_config.anchor_weight),
            "reverse_penalty_weight": float(resolved_config.reverse_penalty_weight),
            "node_coverage_weight": float(resolved_config.node_coverage_weight),
            "endpoint_reuse_weight": float(resolved_config.endpoint_reuse_weight),
        },
        "node_degree_lookup_v1": {node_id: int(value) for node_id, value in sorted(node_degree_lookup.items())},
        "allowed_route_group_colors": list(resolved_config.allowed_route_group_colors),
        "excluded_endpoint_group_colors": list(resolved_config.excluded_endpoint_group_colors),
    }
    _report_progress(
        progress_callback,
        AutoPlanningProgress(
            phase="completed",
            pairs_considered=min(len(scored_pairs), resolved_config.max_anchor_pairs_to_evaluate),
            max_pairs_to_evaluate=resolved_config.max_anchor_pairs_to_evaluate,
            valid_pairs_found=len(scored_pairs),
            candidate_pool_size=len(candidate_pool),
            selected_routes=len(selected_candidates),
            max_output_routes=resolved_config.max_output_routes,
            done=True,
            searched_candidates=candidate_pool_result.searched_candidates,
            filtered_candidates=candidate_pool_result.filtered_candidates,
            kept_candidates=len(candidate_pool),
        ),
    )
    return RouteCandidateSet(
        env_id=planning_graph.env_id,
        graph_name=planning_graph.graph_name,
        anchor_nodes=[],
        candidates=selected_candidates,
        node_lookup=graph_context.normalized_node_lookup,
        selected_candidate_ids=selected_candidate_ids,
        meta=meta,
    )
