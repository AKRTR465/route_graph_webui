from __future__ import annotations

if __package__ in {None, ""}:
    from graph_meta import (
        DEFAULT_BRIDGE_COLOR,
        DEFAULT_GROUP_COLOR,
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GRAPH_BRIDGE_STYLE_META_KEY,
        GRAPH_GROUP_CONFIGS_META_KEY,
        GROUP_CONFIG_LABEL_KEY,
        GROUP_CONFIG_TEXT_KEYS,
        NODE_SAMPLE_RADIUS_META_KEY,
        NODE_Z_PREPROCESS_MODE,
    )
    from graph_model import *
    from graph_grouping import *
    from graph_io import *
    from candidate_conversion import *
    from graph_validation import *
    from graph_versioning import CURRENT_EVALUATION_VERSION, CURRENT_GRAPH_SCHEMA_VERSION
else:
    from .graph_meta import (
        DEFAULT_BRIDGE_COLOR,
        DEFAULT_GROUP_COLOR,
        EDGE_GROUP_COLOR_META_KEY,
        EDGE_KIND_BRIDGE,
        EDGE_KIND_GROUP,
        EDGE_KIND_META_KEY,
        GRAPH_BRIDGE_STYLE_META_KEY,
        GRAPH_GROUP_CONFIGS_META_KEY,
        GROUP_CONFIG_LABEL_KEY,
        GROUP_CONFIG_TEXT_KEYS,
        NODE_SAMPLE_RADIUS_META_KEY,
        NODE_Z_PREPROCESS_MODE,
    )
    from .graph_model import *
    from .graph_grouping import *
    from .graph_io import *
    from .candidate_conversion import *
    from .graph_validation import *
    from .graph_versioning import CURRENT_EVALUATION_VERSION, CURRENT_GRAPH_SCHEMA_VERSION

__all__ = [
    "DEFAULT_BRIDGE_COLOR",
    "DEFAULT_GROUP_COLOR",
    "CURRENT_EVALUATION_VERSION",
    "CURRENT_GRAPH_SCHEMA_VERSION",
    "EDGE_GROUP_COLOR_META_KEY",
    "EDGE_KIND_BRIDGE",
    "EDGE_KIND_GROUP",
    "EDGE_KIND_META_KEY",
    "GRAPH_BRIDGE_STYLE_META_KEY",
    "GRAPH_GROUP_CONFIGS_META_KEY",
    "GROUP_CONFIG_LABEL_KEY",
    "GROUP_CONFIG_TEXT_KEYS",
    "NODE_SAMPLE_RADIUS_META_KEY",
    "NODE_Z_PREPROCESS_MODE",
    "GraphColorGrouping",
    "GraphEdge",
    "GraphNode",
    "GraphSchemaError",
    "GraphValidationIssue",
    "GraphValidationReport",
    "RouteCandidate",
    "RouteCandidateSet",
    "RouteEdgePass",
    "RouteGraph",
    "RoutePlan",
    "RouteSegment",
    "build_uniform_z_node_lookup",
    "candidate_to_plan",
    "clone_graph_node",
    "clone_node_lookup",
    "compute_uniform_node_z",
    "derive_graph_color_grouping",
    "dump_json",
    "edge_xy_weight",
    "ensure_valid_graph",
    "ensure_valid_grouped_graph_for_routes",
    "ensure_valid_plan",
    "get_edge_group_color",
    "get_edge_kind",
    "get_node_sample_radius_override",
    "graph_uses_color_groups",
    "load_candidate_set",
    "load_graph",
    "load_json",
    "load_plan",
    "normalize_hex_color",
    "physical_edge_key",
    "read_graph_bridge_style",
    "read_graph_group_configs",
    "resolve_bridge_color",
    "resolve_plan_edge_passes",
    "save_candidate_set",
    "save_graph",
    "save_plan",
    "validate_graph",
    "validate_grouped_graph_for_routes",
    "validate_plan",
    "write_graph_bridge_style",
    "write_graph_group_configs",
]
