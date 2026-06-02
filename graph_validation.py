from __future__ import annotations

from typing import Any, Mapping

if __package__ in {None, ""}:
    from candidate_conversion import resolve_plan_edge_passes
    from graph_grouping import (
        GraphColorGrouping,
        derive_graph_color_grouping,
        get_edge_group_color,
        get_edge_kind,
        get_node_sample_radius_override,
        normalize_hex_color,
    )
    from graph_meta import (
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GRAPH_BRIDGE_STYLE_META_KEY,
        GRAPH_GROUP_CONFIGS_META_KEY,
    )
    from graph_model import GraphSchemaError, GraphValidationIssue, GraphValidationReport, RouteGraph, RoutePlan
    from geometry import segments_intersect_2d
else:
    from .candidate_conversion import resolve_plan_edge_passes
    from .graph_grouping import (
        GraphColorGrouping,
        derive_graph_color_grouping,
        get_edge_group_color,
        get_edge_kind,
        get_node_sample_radius_override,
        normalize_hex_color,
    )
    from .graph_meta import (
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GRAPH_BRIDGE_STYLE_META_KEY,
        GRAPH_GROUP_CONFIGS_META_KEY,
    )
    from .graph_model import GraphSchemaError, GraphValidationIssue, GraphValidationReport, RouteGraph, RoutePlan
    from .geometry import segments_intersect_2d


def validate_graph(graph: RouteGraph) -> GraphValidationReport:
    report = GraphValidationReport()
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    directed_pairs: dict[tuple[str, str], str] = {}
    bidirectional_pairs: dict[tuple[str, str], str] = {}

    if not graph.env_id:
        report.add("error", "missing-env-id", "RouteGraph `env_id` must not be empty")
    if not graph.graph_name:
        report.add("error", "missing-graph-name", "RouteGraph `graph_name` must not be empty")
    if not graph.nodes:
        report.add("warning", "empty-graph", "RouteGraph contains no nodes")

    for node in graph.nodes:
        if node.id in node_ids:
            report.add("error", "duplicate-node-id", f"Duplicate node id `{node.id}`", [node.id])
        node_ids.add(node.id)
        try:
            get_node_sample_radius_override(node)
        except GraphSchemaError as exc:
            report.add(
                "error",
                "invalid-node-sample-radius",
                str(exc),
                [node.id],
            )

    node_map = graph.node_map
    for edge in graph.edges:
        if edge.id in edge_ids:
            report.add("error", "duplicate-edge-id", f"Duplicate edge id `{edge.id}`", [edge.id])
        edge_ids.add(edge.id)
        if edge.from_node == edge.to_node:
            report.add("error", "self-loop", f"Edge `{edge.id}` forms a self-loop", [edge.id])
        if edge.from_node not in node_map or edge.to_node not in node_map:
            report.add(
                "error",
                "missing-node-reference",
                f"Edge `{edge.id}` references unknown node(s) `{edge.from_node}` -> `{edge.to_node}`",
                [edge.id],
            )
        if edge.weight <= 0:
            report.add("error", "non-positive-weight", f"Edge `{edge.id}` must have positive weight", [edge.id])

        pair_key = (edge.from_node, edge.to_node)
        unordered_key = tuple(sorted(pair_key))
        reverse_key = (edge.to_node, edge.from_node)
        if pair_key in directed_pairs:
            report.add(
                "error",
                "duplicate-edge",
                f"Duplicate directed edge `{edge.from_node}` -> `{edge.to_node}`",
                [directed_pairs[pair_key], edge.id],
            )
        elif edge.bidirectional and reverse_key in directed_pairs:
            report.add(
                "error",
                "duplicate-edge",
                f"Bidirectional edge `{edge.id}` conflicts with existing reverse one-way edge "
                f"`{edge.to_node}` -> `{edge.from_node}`",
                [directed_pairs[reverse_key], edge.id],
            )
        elif unordered_key in bidirectional_pairs:
            report.add(
                "error",
                "duplicate-edge",
                f"Edge `{edge.id}` conflicts with existing bidirectional node pair "
                f"`{unordered_key[0]}` <-> `{unordered_key[1]}`",
                [bidirectional_pairs[unordered_key], edge.id],
            )
        directed_pairs[pair_key] = edge.id
        if edge.bidirectional:
            bidirectional_pairs[unordered_key] = edge.id

    connected_nodes: set[str] = set()
    for edge in graph.edges:
        connected_nodes.add(edge.from_node)
        connected_nodes.add(edge.to_node)
    for node in graph.nodes:
        if node.id not in connected_nodes:
            report.add("warning", "isolated-node", f"Node `{node.id}` is isolated", [node.id])

    valid_edges = [edge for edge in graph.edges if edge.from_node in node_map and edge.to_node in node_map]
    intersection_buckets: dict[str | None, list[tuple[Any, tuple[float, float], tuple[float, float]]]] = {}
    for edge in valid_edges:
        edge_kind = get_edge_kind(edge)
        if edge_kind == EDGE_KIND_BRIDGE:
            continue
        group_color = get_edge_group_color(edge) if edge_kind == EDGE_KIND_GROUP else None
        intersection_buckets.setdefault(group_color, []).append(
            (
                edge,
                tuple(node_map[edge.from_node].position[:2]),
                tuple(node_map[edge.to_node].position[:2]),
            )
        )

    for bucket_edges in intersection_buckets.values():
        for index, (edge_a, a1, a2) in enumerate(bucket_edges):
            a_nodes = {edge_a.from_node, edge_a.to_node}
            for edge_b, b1, b2 in bucket_edges[index + 1 :]:
                b_nodes = {edge_b.from_node, edge_b.to_node}
                if a_nodes & b_nodes:
                    continue
                if segments_intersect_2d(a1, a2, b1, b2):
                    report.add(
                        "error",
                        "edge-intersection",
                        f"Edges `{edge_a.id}` and `{edge_b.id}` intersect in XY plane",
                        [edge_a.id, edge_b.id],
                    )
    _append_grouping_validation_issues(graph, report, severity="warning")
    return report


def ensure_valid_graph(graph: RouteGraph) -> GraphValidationReport:
    report = validate_graph(graph)
    if report.errors:
        raise GraphSchemaError(report.format_text())
    return report


def _append_grouping_validation_issues(
    graph: RouteGraph,
    report: GraphValidationReport,
    *,
    severity: str,
) -> GraphColorGrouping:
    grouping = derive_graph_color_grouping(graph)
    raw_group_configs = graph.meta.get(GRAPH_GROUP_CONFIGS_META_KEY)
    if raw_group_configs is not None and not isinstance(raw_group_configs, Mapping):
        report.add(
            severity,
            "invalid-group-configs",
            f"RouteGraph `meta.{GRAPH_GROUP_CONFIGS_META_KEY}` must be a mapping",
        )
    elif isinstance(raw_group_configs, Mapping):
        for raw_color, raw_payload in raw_group_configs.items():
            try:
                normalize_hex_color(raw_color, field_name="group color")
            except GraphSchemaError as exc:
                report.add(severity, "invalid-group-color-key", str(exc), [str(raw_color)])
                continue
            if not isinstance(raw_payload, Mapping):
                report.add(
                    severity,
                    "invalid-group-config-entry",
                    f"Group config `{raw_color}` must be a mapping",
                    [str(raw_color)],
                )

    raw_bridge_style = graph.meta.get(GRAPH_BRIDGE_STYLE_META_KEY)
    if raw_bridge_style is not None and not isinstance(raw_bridge_style, Mapping):
        report.add(
            severity,
            "invalid-bridge-style",
            f"RouteGraph `meta.{GRAPH_BRIDGE_STYLE_META_KEY}` must be a mapping",
        )
    elif isinstance(raw_bridge_style, Mapping) and "color" in raw_bridge_style:
        try:
            normalize_hex_color(raw_bridge_style["color"], field_name="bridge color")
        except GraphSchemaError as exc:
            report.add(severity, "invalid-bridge-color", str(exc))

    for edge in graph.edges:
        raw_kind = edge.meta.get(EDGE_KIND_META_KEY)
        if raw_kind is not None and raw_kind not in {EDGE_KIND_GROUP, EDGE_KIND_BRIDGE}:
            report.add(
                severity,
                "invalid-edge-kind",
                f"GraphEdge `{edge.id}` has unsupported `{EDGE_KIND_META_KEY}` value `{raw_kind}`",
                [edge.id],
            )
        if get_edge_kind(edge) == EDGE_KIND_GROUP and EDGE_GROUP_COLOR_META_KEY in edge.meta:
            try:
                normalize_hex_color(
                    edge.meta.get(EDGE_GROUP_COLOR_META_KEY),
                    field_name=f"GraphEdge `{edge.id}` field `{EDGE_GROUP_COLOR_META_KEY}`",
                )
            except GraphSchemaError as exc:
                report.add(severity, "invalid-edge-group-color", str(exc), [edge.id])

    for node_id, colors in sorted(grouping.conflicting_node_groups.items()):
        color_list = ", ".join(sorted(colors))
        report.add(
            severity,
            "node-multi-group",
            f"Node `{node_id}` belongs to multiple color groups: {color_list}",
            [node_id],
        )

    for node_id in sorted(grouping.ungrouped_node_ids):
        connected = any(
            edge.from_node == node_id or edge.to_node == node_id
            for edge in graph.edges
        )
        if connected:
            report.add(
                severity,
                "node-without-group",
                f"Node `{node_id}` is only connected by bridge edges and has no color-group membership",
                [node_id],
            )

    for edge in graph.edges:
        if grouping.edge_kind_lookup.get(edge.id) != EDGE_KIND_BRIDGE:
            continue
        from_group = grouping.node_group_lookup.get(edge.from_node)
        to_group = grouping.node_group_lookup.get(edge.to_node)
        if from_group is None or to_group is None:
            report.add(
                severity,
                "bridge-edge-node-group-missing",
                f"Bridge edge `{edge.id}` must connect nodes with unique group membership",
                [edge.id, edge.from_node, edge.to_node],
            )
            continue
        if from_group == to_group:
            report.add(
                severity,
                "bridge-edge-same-group",
                f"Bridge edge `{edge.id}` connects nodes in the same color group `{from_group}`",
                [edge.id],
            )
    return grouping


def validate_grouped_graph_for_routes(graph: RouteGraph) -> GraphValidationReport:
    report = validate_graph(graph)
    _append_grouping_validation_issues(graph, report, severity="error")
    return report


def ensure_valid_grouped_graph_for_routes(graph: RouteGraph) -> GraphValidationReport:
    report = validate_grouped_graph_for_routes(graph)
    if report.errors:
        raise GraphSchemaError(report.format_text())
    return report


def validate_plan(plan: RoutePlan) -> GraphValidationReport:
    report = GraphValidationReport()
    node_lookup = plan.node_lookup

    if not plan.env_id:
        report.add("error", "missing-env-id", "RoutePlan `env_id` must not be empty")
    if not plan.graph_name:
        report.add("error", "missing-graph-name", "RoutePlan `graph_name` must not be empty")
    if not plan.anchor_nodes:
        report.add("error", "missing-anchor-nodes", "RoutePlan must contain at least one anchor node")
    if not plan.planned_nodes:
        report.add("error", "empty-plan", "RoutePlan must contain at least one planned node")
    if not node_lookup:
        report.add("error", "missing-node-lookup", "RoutePlan must include node_lookup entries")

    for anchor_node in plan.anchor_nodes:
        if anchor_node not in node_lookup:
            report.add(
                "error",
                "missing-anchor-node",
                f"Anchor node `{anchor_node}` is not present in node_lookup",
                [anchor_node],
            )

    for node_id in plan.planned_nodes:
        if node_id not in node_lookup:
            report.add(
                "error",
                "missing-plan-node",
                f"Planned node `{node_id}` is not present in node_lookup",
                [node_id],
            )

    if plan.anchor_nodes and plan.planned_nodes:
        if plan.planned_nodes[0] != plan.anchor_nodes[0]:
            report.add(
                "error",
                "anchor-start-mismatch",
                "RoutePlan planned_nodes must start at the first anchor node",
                [plan.anchor_nodes[0], plan.planned_nodes[0]],
            )
        if plan.planned_nodes[-1] != plan.anchor_nodes[-1]:
            report.add(
                "error",
                "anchor-end-mismatch",
                "RoutePlan planned_nodes must end at the last anchor node",
                [plan.anchor_nodes[-1], plan.planned_nodes[-1]],
            )

    expected_segment_count = max(len(plan.anchor_nodes) - 1, 0)
    if len(plan.segments) != expected_segment_count:
        report.add(
            "error",
            "anchor-segment-count-mismatch",
            "RoutePlan segments must contain exactly one segment for each adjacent anchor pair",
        )

    flattened_segment_nodes: list[str] = []
    for segment_index, segment in enumerate(plan.segments):
        segment_label = f"{segment.start_anchor}->{segment.end_anchor}"
        expected_start_anchor = plan.anchor_nodes[segment_index] if segment_index < len(plan.anchor_nodes) else None
        expected_end_anchor = (
            plan.anchor_nodes[segment_index + 1]
            if segment_index + 1 < len(plan.anchor_nodes)
            else None
        )
        if (
            expected_start_anchor is not None
            and expected_end_anchor is not None
            and (
                segment.start_anchor != expected_start_anchor
                or segment.end_anchor != expected_end_anchor
            )
        ):
            report.add(
                "error",
                "segment-anchor-mismatch",
                f"Segment `{segment_label}` does not match the expected anchor pair "
                f"`{expected_start_anchor}->{expected_end_anchor}`",
                [segment_label],
            )
        if not segment.node_ids:
            report.add(
                "error",
                "empty-segment",
                f"Segment `{segment_label}` must contain at least one node",
                [segment_label],
            )
            continue
        if len(segment.node_ids) != len(segment.edge_ids) + 1:
            report.add(
                "error",
                "segment-node-edge-mismatch",
                f"Segment `{segment_label}` must have len(node_ids) == len(edge_ids) + 1",
                [segment_label],
            )
        for node_id in segment.node_ids:
            if node_id not in node_lookup:
                report.add(
                    "error",
                    "missing-segment-node",
                    f"Segment `{segment_label}` references node `{node_id}` missing from node_lookup",
                    [segment_label, node_id],
                )
        if segment.node_ids:
            if segment.node_ids[0] != segment.start_anchor:
                report.add(
                    "error",
                    "segment-start-anchor-boundary",
                    f"Segment `{segment_label}` must start at its start_anchor",
                    [segment_label, segment.node_ids[0]],
                )
            if segment.node_ids[-1] != segment.end_anchor:
                report.add(
                    "error",
                    "segment-end-anchor-boundary",
                    f"Segment `{segment_label}` must end at its end_anchor",
                    [segment_label, segment.node_ids[-1]],
                )
        if segment.edge_passes and len(segment.edge_passes) != len(segment.edge_ids):
            report.add(
                "error",
                "segment-edge-pass-mismatch",
                f"Segment `{segment_label}` edge_passes count must match edge_ids count",
                [segment_label],
            )

        if not flattened_segment_nodes:
            flattened_segment_nodes.extend(segment.node_ids)
        else:
            if flattened_segment_nodes[-1] != segment.node_ids[0]:
                report.add(
                    "error",
                    "disconnected-segments",
                    f"Segment `{segment_label}` does not continue from the previous segment",
                    [segment_label],
                )
            flattened_segment_nodes.extend(segment.node_ids[1:])

        for local_index, edge_pass in enumerate(segment.edge_passes, start=1):
            if edge_pass.segment_index != segment_index:
                report.add(
                    "error",
                    "segment-index-mismatch",
                    f"Segment `{segment_label}` contains edge pass `{edge_pass.edge_id}` with mismatched segment_index",
                    [segment_label, edge_pass.edge_id],
                )
            if edge_pass.local_index != local_index:
                report.add(
                    "error",
                    "local-index-mismatch",
                    f"Segment `{segment_label}` contains non-consecutive local_index values",
                    [segment_label, edge_pass.edge_id],
                )
            expected_edge_id = segment.edge_ids[local_index - 1] if local_index - 1 < len(segment.edge_ids) else None
            expected_from = segment.node_ids[local_index - 1] if local_index - 1 < len(segment.node_ids) else None
            expected_to = segment.node_ids[local_index] if local_index < len(segment.node_ids) else None
            if expected_edge_id is not None and edge_pass.edge_id != expected_edge_id:
                report.add(
                    "error",
                    "segment-edge-id-mismatch",
                    f"Segment `{segment_label}` edge_pass `{edge_pass.edge_id}` does not match edge_ids ordering",
                    [segment_label, edge_pass.edge_id],
                )
            if edge_pass.from_node != expected_from or edge_pass.to_node != expected_to:
                report.add(
                    "error",
                    "segment-edge-pass-direction",
                    f"Segment `{segment_label}` edge_pass `{edge_pass.edge_id}` does not match segment node ordering",
                    [segment_label, edge_pass.edge_id],
                )

    if plan.segments and flattened_segment_nodes and flattened_segment_nodes != plan.planned_nodes:
        report.add(
            "error",
            "planned-node-segment-mismatch",
            "RoutePlan planned_nodes do not match the concatenated segment node sequence",
        )

    try:
        resolved_edge_passes = resolve_plan_edge_passes(plan)
    except GraphSchemaError as exc:
        report.add("error", "invalid-edge-pass-layout", str(exc))
        resolved_edge_passes = []

    if resolved_edge_passes:
        if len(plan.planned_nodes) != len(resolved_edge_passes) + 1:
            report.add(
                "error",
                "planned-node-edge-pass-mismatch",
                "RoutePlan planned_nodes must contain exactly one more element than edge_passes",
            )
        for index, edge_pass in enumerate(resolved_edge_passes, start=1):
            if edge_pass.pass_index != index:
                report.add(
                    "error",
                    "pass-index-mismatch",
                    "RoutePlan edge_passes must use consecutive pass_index values starting at 1",
                    [edge_pass.edge_id],
                )
            if edge_pass.from_node not in node_lookup or edge_pass.to_node not in node_lookup:
                report.add(
                    "error",
                    "missing-edge-pass-node",
                    f"Edge pass `{edge_pass.edge_id}` references nodes missing from node_lookup",
                    [edge_pass.edge_id],
                )
            planned_index = index - 1
            if planned_index + 1 < len(plan.planned_nodes):
                expected_from = plan.planned_nodes[planned_index]
                expected_to = plan.planned_nodes[planned_index + 1]
                if edge_pass.from_node != expected_from or edge_pass.to_node != expected_to:
                    report.add(
                        "error",
                        "edge-pass-direction",
                        f"Edge pass `{edge_pass.edge_id}` does not match planned_nodes ordering",
                        [edge_pass.edge_id],
                    )
    elif len(plan.planned_nodes) > 1:
        report.add(
            "error",
            "missing-edge-passes",
            "RoutePlan with multiple planned nodes must include edge_passes or reconstructable segments",
        )

    return report


def ensure_valid_plan(plan: RoutePlan) -> GraphValidationReport:
    report = validate_plan(plan)
    if report.errors:
        raise GraphSchemaError(report.format_text())
    return report

__all__ = [
    "GraphSchemaError",
    "GraphValidationIssue",
    "GraphValidationReport",
    "ensure_valid_graph",
    "ensure_valid_grouped_graph_for_routes",
    "ensure_valid_plan",
    "validate_graph",
    "validate_grouped_graph_for_routes",
    "validate_plan",
]
