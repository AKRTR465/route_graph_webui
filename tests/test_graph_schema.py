from __future__ import annotations

from graph_schema import RouteCandidateSet, RoutePlan, load_json, save_graph
from graph_versioning import CURRENT_EVALUATION_VERSION, CURRENT_GRAPH_SCHEMA_VERSION
from spelling_compat import (
    CANONICAL_GRAPH_CREATOR_PREFIX,
    LEGACY_GRAPH_CREATOR_META_KEY,
    LEGACY_GRAPH_CREATOR_PREFIX,
)
from tests.route_graph_test_helpers import *

class GraphSchemaValidationTests(unittest.TestCase):
    def test_physical_edge_key_is_direction_agnostic(self) -> None:
        self.assertEqual(physical_edge_key("A", "B"), physical_edge_key("B", "A"))

    def test_rejects_bidirectional_and_reverse_one_way_duplicate(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="graph",
            default_altitude=None,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
                GraphNode(id="B", name="B", position=[1.0, 0.0, 0.0]),
            ],
            edges=[
                GraphEdge(id="E001", from_node="A", to_node="B", weight=1.0, bidirectional=True),
                GraphEdge(id="E002", from_node="B", to_node="A", weight=1.0, bidirectional=False),
            ],
        )

        report = validate_graph(graph)

        self.assertFalse(report.is_valid)
        self.assertTrue(any(issue.code == "duplicate-edge" for issue in report.errors))

    def test_allows_opposite_one_way_edges(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="graph",
            default_altitude=None,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
                GraphNode(id="B", name="B", position=[1.0, 0.0, 0.0]),
            ],
            edges=[
                GraphEdge(id="E001", from_node="A", to_node="B", weight=1.0, bidirectional=False),
                GraphEdge(id="E002", from_node="B", to_node="A", weight=1.0, bidirectional=False),
            ],
        )

        report = validate_graph(graph)

        self.assertTrue(report.is_valid, report.format_text())

    def test_allows_intersection_between_different_group_colors(self) -> None:
        graph = build_crossing_two_edge_graph(
            edge_a_meta={
                EDGE_KIND_META_KEY: EDGE_KIND_GROUP,
                EDGE_GROUP_COLOR_META_KEY: "#FF0000",
            },
            edge_b_meta={
                EDGE_KIND_META_KEY: EDGE_KIND_GROUP,
                EDGE_GROUP_COLOR_META_KEY: "#00AAFF",
            },
        )

        report = validate_graph(graph)

        self.assertFalse(any(issue.code == "edge-intersection" for issue in report.errors), report.format_text())

    def test_rejects_intersection_within_same_group_color(self) -> None:
        graph = build_crossing_two_edge_graph(
            edge_a_meta={
                EDGE_KIND_META_KEY: EDGE_KIND_GROUP,
                EDGE_GROUP_COLOR_META_KEY: "#FF0000",
            },
            edge_b_meta={
                EDGE_KIND_META_KEY: EDGE_KIND_GROUP,
                EDGE_GROUP_COLOR_META_KEY: "#FF0000",
            },
        )

        report = validate_graph(graph)

        self.assertTrue(any(issue.code == "edge-intersection" for issue in report.errors), report.format_text())

    def test_allows_intersection_when_bridge_edge_is_involved(self) -> None:
        graph = build_crossing_two_edge_graph(
            edge_a_meta={EDGE_KIND_META_KEY: EDGE_KIND_BRIDGE},
            edge_b_meta={
                EDGE_KIND_META_KEY: EDGE_KIND_GROUP,
                EDGE_GROUP_COLOR_META_KEY: "#FF0000",
            },
        )

        report = validate_graph(graph)

        self.assertFalse(any(issue.code == "edge-intersection" for issue in report.errors), report.format_text())

    def test_rejects_negative_node_sample_radius_override(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="graph",
            default_altitude=None,
            nodes=[
                GraphNode(
                    id="A",
                    name="A",
                    position=[0.0, 0.0, 0.0],
                    meta={NODE_SAMPLE_RADIUS_META_KEY: -1.0},
                ),
            ],
            edges=[],
        )

        report = validate_graph(graph)

        self.assertFalse(report.is_valid)
        self.assertTrue(any(issue.code == "invalid-node-sample-radius" for issue in report.errors))

    def test_graph_roundtrip_preserves_node_sample_radius_override(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="graph",
            default_altitude=None,
            nodes=[
                GraphNode(
                    id="A",
                    name="A",
                    position=[0.0, 0.0, 0.0],
                    meta={NODE_SAMPLE_RADIUS_META_KEY: 12.5},
                ),
            ],
            edges=[],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = write_json_file(Path(temp_dir) / "graph.json", graph.to_dict())
            loaded = load_graph(graph_path)

        self.assertEqual(loaded.get_node("A").meta[NODE_SAMPLE_RADIUS_META_KEY], 12.5)

    def test_legacy_graph_without_schema_version_loads_and_new_graph_writes_version(self) -> None:
        graph = build_test_square_graph()
        legacy_payload = graph.to_dict()
        legacy_payload.pop("schema_version", None)
        legacy_creator = f"{LEGACY_GRAPH_CREATOR_PREFIX}graph_record"
        canonical_creator = f"{CANONICAL_GRAPH_CREATOR_PREFIX}graph_record"
        legacy_payload["meta"] = {"creator": legacy_creator}

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = write_json_file(Path(temp_dir) / "legacy_graph.json", legacy_payload)
            loaded = load_graph(graph_path)
            output_path = Path(temp_dir) / "new_graph.json"
            save_graph(output_path, loaded)
            saved_payload = load_json(output_path)

        self.assertEqual(loaded.schema_version, CURRENT_GRAPH_SCHEMA_VERSION)
        self.assertEqual(loaded.meta["creator"], canonical_creator)
        self.assertEqual(loaded.meta[LEGACY_GRAPH_CREATOR_META_KEY], legacy_creator)
        self.assertEqual(saved_payload["schema_version"], CURRENT_GRAPH_SCHEMA_VERSION)
        self.assertEqual(saved_payload["meta"]["creator"], canonical_creator)

    def test_plan_and_candidate_set_roundtrip_evaluation_version(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=1)
        candidate_payload = candidate_set.to_dict()
        candidate_payload.pop("evaluation_version", None)
        loaded_candidate_set = RouteCandidateSet.from_mapping(candidate_payload)
        plan = candidate_to_plan(loaded_candidate_set, loaded_candidate_set.candidates[0].candidate_id)
        plan_payload = plan.to_dict()
        plan_payload.pop("evaluation_version", None)
        loaded_plan = RoutePlan.from_mapping(plan_payload)

        self.assertEqual(loaded_candidate_set.evaluation_version, CURRENT_EVALUATION_VERSION)
        self.assertEqual(loaded_candidate_set.to_dict()["evaluation_version"], CURRENT_EVALUATION_VERSION)
        self.assertEqual(loaded_plan.evaluation_version, CURRENT_EVALUATION_VERSION)
        self.assertEqual(loaded_plan.to_dict()["evaluation_version"], CURRENT_EVALUATION_VERSION)

    def test_graph_edge_bool_fields_accept_bool_string_and_integer_values(self) -> None:
        edge_from_string = GraphEdge.from_mapping(
            {
                "id": "E001",
                "from": "A",
                "to": "B",
                "weight": 1.0,
                "enabled": "false",
                "bidirectional": "true",
            }
        )
        edge_from_int = GraphEdge.from_mapping(
            {
                "id": "E002",
                "from": "A",
                "to": "B",
                "weight": 1.0,
                "enabled": 1,
                "bidirectional": 0,
            }
        )
        candidate = RouteCandidate.from_mapping(
            {
                "candidate_id": "C001",
                "planned_nodes": [],
                "edge_passes": [],
                "segments": [],
                "total_length": 0.0,
                "selected": "false",
            }
        )

        self.assertFalse(edge_from_string.enabled)
        self.assertTrue(edge_from_string.bidirectional)
        self.assertTrue(edge_from_int.enabled)
        self.assertFalse(edge_from_int.bidirectional)
        self.assertFalse(candidate.selected)

    def test_graph_edge_bool_fields_reject_invalid_values(self) -> None:
        with self.assertRaises(GraphSchemaError):
            GraphEdge.from_mapping(
                {
                    "id": "E001",
                    "from": "A",
                    "to": "B",
                    "weight": 1.0,
                    "enabled": "off",
                }
            )
        with self.assertRaises(GraphSchemaError):
            GraphEdge.from_mapping(
                {
                    "id": "E002",
                    "from": "A",
                    "to": "B",
                    "weight": 1.0,
                    "bidirectional": 2,
                }
            )
        with self.assertRaises(GraphSchemaError):
            RouteCandidate.from_mapping(
                {
                    "candidate_id": "C001",
                    "planned_nodes": [],
                    "edge_passes": [],
                    "segments": [],
                    "total_length": 0.0,
                    "selected": "bad",
                }
            )


class GraphColorGroupingTests(unittest.TestCase):
    def test_legacy_graph_defaults_to_single_group_color(self) -> None:
        graph = build_test_square_graph()

        grouping = derive_graph_color_grouping(graph)

        self.assertEqual(set(grouping.group_edge_ids), {DEFAULT_GROUP_COLOR})
        self.assertEqual(set(grouping.node_group_lookup), {node.id for node in graph.nodes})
        self.assertEqual(grouping.bridge_edge_ids, set())
        self.assertEqual(get_edge_kind(graph.edges[0]), EDGE_KIND_GROUP)
        self.assertEqual(get_edge_group_color(graph.edges[0]), DEFAULT_GROUP_COLOR)

    def test_group_config_and_bridge_style_roundtrip(self) -> None:
        meta: dict[str, object] = {}

        write_graph_group_configs(
            meta,
            {
                "#ff0000": {
                    "altitude_mode": "fixed",
                    "fixed_z": "120",
                    "altitude_offset": "3",
                }
            },
        )
        write_graph_bridge_style(meta, {"color": "#00ff00"})

        self.assertEqual(
            read_graph_group_configs(meta),
            {
                "#FF0000": {
                    "altitude_mode": "fixed",
                    "fixed_z": "120",
                    "altitude_offset": "3",
                }
            },
        )
        self.assertEqual(read_graph_bridge_style(meta), {"color": "#00FF00"})

    def test_bridge_graph_derives_unique_node_groups(self) -> None:
        graph = build_group_bridge_graph()

        grouping = derive_graph_color_grouping(graph)

        self.assertEqual(grouping.node_group_lookup["A"], "#FF0000")
        self.assertEqual(grouping.node_group_lookup["B"], "#FF0000")
        self.assertEqual(grouping.node_group_lookup["C"], "#00AAFF")
        self.assertEqual(grouping.node_group_lookup["D"], "#00AAFF")
        self.assertEqual(grouping.bridge_edge_ids, {"E_BRIDGE"})
        self.assertAlmostEqual(grouping.group_average_z_lookup["#FF0000"], 0.0)
        self.assertAlmostEqual(grouping.group_average_z_lookup["#00AAFF"], 100.0)

    def test_grouped_route_validation_rejects_multi_group_node(self) -> None:
        graph = build_group_bridge_graph()
        graph.edges.append(
            GraphEdge(
                id="E_BAD",
                from_node="B",
                to_node="D",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#00FF00"},
            )
        )

        with self.assertRaises(GraphSchemaError) as context:
            ensure_valid_grouped_graph_for_routes(graph)

        self.assertIn("node-multi-group", str(context.exception))



class CandidateSnapshotTests(unittest.TestCase):
    def test_candidate_set_node_lookup_is_detached_snapshot(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=2)
        plan = candidate_to_plan(candidate_set, "C001")

        graph.get_node("N001").name = "GRAPH_MUTATED"
        self.assertEqual(candidate_set.node_lookup["N001"].name, "N001")
        self.assertEqual(plan.node_lookup["N001"].name, "N001")

        candidate_set.node_lookup["N001"].name = "CANDIDATE_MUTATED"
        self.assertEqual(plan.node_lookup["N001"].name, "N001")

    def test_candidate_set_node_lookup_uses_uniform_mean_z_snapshot(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="mixed_z_graph",
            default_altitude=None,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 100.0], yaw_hint=0.0),
                GraphNode(id="B", name="B", position=[100.0, 0.0, 300.0], yaw_hint=90.0),
            ],
            edges=[
                GraphEdge(id="E001", from_node="A", to_node="B", weight=100.0, bidirectional=True),
            ],
        )

        candidate_set = generate_route_candidates(graph, "A", "B", max_routes=1)
        plan = candidate_to_plan(candidate_set, "C001")

        self.assertEqual(graph.get_node("A").position[2], 100.0)
        self.assertEqual(graph.get_node("B").position[2], 300.0)
        self.assertEqual(
            {node.position[2] for node in candidate_set.node_lookup.values()},
            {200.0},
        )
        self.assertEqual(
            {node.position[2] for node in plan.node_lookup.values()},
            {200.0},
        )
        self.assertEqual(candidate_set.meta["node_z_preprocess_mode"], "mean_all_recorded_nodes")
        self.assertEqual(candidate_set.meta["uniform_node_z"], 200.0)

    def test_candidate_set_and_plan_preserve_graph_default_altitude_meta(self) -> None:
        graph = build_test_square_graph()
        graph.default_altitude = 350.0

        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=1)
        plan = candidate_to_plan(candidate_set, "C001")

        self.assertEqual(candidate_set.meta["graph_default_altitude"], 350.0)
        self.assertEqual(plan.meta["graph_default_altitude"], 350.0)



