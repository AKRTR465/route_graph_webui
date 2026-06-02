from __future__ import annotations

import candidate_conversion
import graph_grouping
import graph_io
import graph_model
import graph_schema
import graph_validation


def test_graph_schema_compat_reexports_graph_model_sources() -> None:
    assert graph_model.GraphNode is graph_schema.GraphNode
    assert graph_model.GraphEdge is graph_schema.GraphEdge
    assert graph_model.RouteGraph is graph_schema.RouteGraph
    assert graph_model.RoutePlan is graph_schema.RoutePlan
    assert graph_model.RouteCandidateSet is graph_schema.RouteCandidateSet
    assert graph_model.GraphNode.__module__ == "graph_model"
    assert graph_model.RouteCandidateSet.__module__ == "graph_model"


def test_graph_schema_compat_reexports_graph_io_sources() -> None:
    assert graph_io.load_graph is graph_schema.load_graph
    assert graph_io.save_graph is graph_schema.save_graph
    assert graph_io.load_candidate_set is graph_schema.load_candidate_set
    assert graph_io.save_candidate_set is graph_schema.save_candidate_set
    assert graph_io.load_graph.__module__ == "graph_io"
    assert graph_io.save_candidate_set.__module__ == "graph_io"


def test_graph_schema_compat_reexports_graph_validation_sources() -> None:
    assert graph_validation.validate_graph is graph_schema.validate_graph
    assert graph_validation.ensure_valid_graph is graph_schema.ensure_valid_graph
    assert graph_validation.validate_plan is graph_schema.validate_plan
    assert graph_validation.GraphSchemaError is graph_schema.GraphSchemaError
    assert graph_validation.validate_graph.__module__ == "graph_validation"
    assert graph_validation.validate_plan.__module__ == "graph_validation"


def test_graph_schema_compat_reexports_candidate_conversion_sources() -> None:
    assert candidate_conversion.candidate_to_plan is graph_schema.candidate_to_plan
    assert candidate_conversion.resolve_plan_edge_passes is graph_schema.resolve_plan_edge_passes
    assert candidate_conversion.candidate_to_plan.__module__ == "candidate_conversion"
    assert candidate_conversion.resolve_plan_edge_passes.__module__ == "candidate_conversion"


def test_graph_schema_compat_reexports_grouping_sources() -> None:
    assert graph_grouping.derive_graph_color_grouping is graph_schema.derive_graph_color_grouping
    assert graph_grouping.write_graph_group_configs is graph_schema.write_graph_group_configs
    assert graph_grouping.GraphColorGrouping is graph_schema.GraphColorGrouping
    assert graph_grouping.derive_graph_color_grouping.__module__ == "graph_grouping"
    assert graph_grouping.GraphColorGrouping.__module__ == "graph_grouping"
