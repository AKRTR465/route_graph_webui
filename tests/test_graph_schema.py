from __future__ import annotations

import copy

from tests.route_graph_test_helpers import *
from route_graph_webui.graph.io import load_json, save_graph
from route_graph_webui.graph.model import RouteCandidateSet, RoutePlan
from route_graph_webui.graph.versioning import CURRENT_EVALUATION_VERSION, CURRENT_GRAPH_FORMAT_VERSION
from route_graph_webui.storage import spelling_compat as _spelling_compat

CANONICAL_GRAPH_CREATOR_PREFIX = _spelling_compat.CANONICAL_GRAPH_CREATOR_PREFIX
LEGACY_GRAPH_CREATOR_META_KEY = _spelling_compat.LEGACY_GRAPH_CREATOR_META_KEY
LEGACY_GRAPH_CREATOR_PREFIX = _spelling_compat.LEGACY_GRAPH_CREATOR_PREFIX

class GraphSchemaValidationTests(unittest.TestCase):
    def test_physical_edge_key_is_direction_agnostic(self) -> None:
        self.assertEqual(physical_edge_key("A", "B"), physical_edge_key("B", "A"))

    def test_base_validation_allows_bidirectional_and_reverse_one_way_duplicate(self) -> None:
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

        self.assertTrue(report.is_valid, report.format_text())

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

    def test_base_validation_allows_intersection_within_same_group_color(self) -> None:
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

        self.assertFalse(any(issue.code == "edge-intersection" for issue in report.errors), report.format_text())

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

    def test_base_validation_allows_negative_node_sample_radius_override(self) -> None:
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

        self.assertTrue(report.is_valid, report.format_text())

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

    def test_graph_roundtrip_writes_new_format_version(self) -> None:
        graph = build_test_square_graph()

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = write_json_file(Path(temp_dir) / "graph.json", graph.to_dict())
            loaded = load_graph(graph_path)
            output_path = Path(temp_dir) / "new_graph.json"
            save_graph(output_path, loaded)
            saved_payload = load_json(output_path)

        self.assertEqual(loaded.format_version, CURRENT_GRAPH_FORMAT_VERSION)
        self.assertEqual(saved_payload["format"], "route-graph")
        self.assertEqual(saved_payload["format_version"], CURRENT_GRAPH_FORMAT_VERSION)
        self.assertNotIn("schema_version", saved_payload)
        self.assertNotIn("graph_name", saved_payload)
        self.assertNotIn("env_id", saved_payload)

    def test_minimal_graph_roundtrip_preserves_id_extensions_and_missing_metrics(self) -> None:
        payload = {
            "format": "route-graph",
            "format_version": 1,
            "id": "graph-id",
            "name": "Display Graph",
            "coordinate_system": {
                "type": "cartesian",
                "axes": ["x", "y", "z"],
                "unit": "cm",
            },
            "nodes": [
                {"id": "A", "label": "Alpha", "position": [0.0, 0.0, 0.0]},
                {"id": "B", "label": "Beta", "position": [3.0, 4.0, 9.0]},
            ],
            "edges": [
                {
                    "id": "E001",
                    "source": "A",
                    "target": "B",
                    "directed": False,
                    "enabled": True,
                }
            ],
            "extensions": {
                "custom_namespace": {
                    "keep": True,
                },
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = write_json_file(Path(temp_dir) / "graph.json", payload)
            loaded = load_graph(graph_path)
            output_path = Path(temp_dir) / "saved.json"
            save_graph(output_path, loaded)
            saved_payload = load_json(output_path)
            reloaded = load_graph(output_path)

        edge = loaded.get_edge("E001")
        self.assertEqual(loaded.graph_id, "graph-id")
        self.assertEqual(loaded.graph_name, "Display Graph")
        self.assertEqual(loaded.env_id, "")
        self.assertAlmostEqual(edge.weight, 5.0)
        self.assertFalse(edge.metrics_explicit)
        self.assertFalse(edge.weight_explicit)
        self.assertEqual(saved_payload["id"], "graph-id")
        self.assertEqual(saved_payload["name"], "Display Graph")
        self.assertNotIn("metrics", saved_payload["edges"][0])
        self.assertNotIn("uav", saved_payload.get("extensions", {}))
        self.assertEqual(saved_payload["extensions"]["custom_namespace"], {"keep": True})
        self.assertAlmostEqual(reloaded.get_edge("E001").weight, 5.0)

    def test_planning_uses_current_xy_fallback_for_edges_without_metrics(self) -> None:
        payload = {
            "format": "route-graph",
            "format_version": 1,
            "id": "graph-id",
            "name": "Display Graph",
            "coordinate_system": {},
            "nodes": [
                {"id": "A", "position": [0.0, 0.0, 0.0]},
                {"id": "B", "position": [3.0, 4.0, 0.0]},
            ],
            "edges": [
                {"id": "E001", "source": "A", "target": "B"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = write_json_file(Path(temp_dir) / "graph.json", payload)
            graph = load_graph(graph_path)

        self.assertAlmostEqual(graph.get_edge("E001").weight, 5.0)
        GraphEditor(graph).update_node_xy("B", 6.0, 8.0)
        candidate_set = generate_route_candidates(graph, "A", "B", max_routes=1)

        self.assertAlmostEqual(graph.get_edge("E001").weight, 5.0)
        self.assertAlmostEqual(candidate_set.candidates[0].total_length, 10.0)

    def test_load_graph_rejects_missing_required_new_format_fields(self) -> None:
        payload = {
            "format": "route-graph",
            "format_version": 1,
            "id": "graph-id",
            "name": "Display Graph",
            "coordinate_system": {},
            "nodes": [
                {"id": "A", "position": [0.0, 0.0, 0.0]},
                {"id": "B", "position": [1.0, 0.0, 0.0]},
            ],
            "edges": [
                {"id": "E001", "source": "A", "target": "B"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            for field_name in ("format", "format_version", "nodes", "edges"):
                candidate = copy.deepcopy(payload)
                candidate.pop(field_name)
                graph_path = write_json_file(Path(temp_dir) / f"missing_{field_name}.json", candidate)
                with self.assertRaises(GraphSchemaError):
                    load_graph(graph_path)

    def test_load_graph_rejects_minimal_structural_errors(self) -> None:
        base_payload = {
            "format": "route-graph",
            "format_version": 1,
            "id": "graph-id",
            "name": "Display Graph",
            "coordinate_system": {},
            "nodes": [
                {"id": "A", "position": [0.0, 0.0, 0.0]},
                {"id": "B", "position": [1.0, 0.0, 0.0]},
            ],
            "edges": [
                {"id": "E001", "source": "A", "target": "B"},
            ],
        }
        cases = {
            "duplicate_node": lambda payload: payload["nodes"].append(
                {"id": "A", "position": [2.0, 0.0, 0.0]}
            ),
            "duplicate_edge": lambda payload: payload["edges"].append(
                {"id": "E001", "source": "B", "target": "A"}
            ),
            "dangling_edge": lambda payload: payload["edges"][0].update({"target": "MISSING"}),
            "self_loop": lambda payload: payload["edges"][0].update({"target": "A"}),
            "invalid_position": lambda payload: payload["nodes"][0].update(
                {"position": [0.0, True, 0.0]}
            ),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            for case_name, mutate in cases.items():
                payload = copy.deepcopy(base_payload)
                mutate(payload)
                graph_path = write_json_file(Path(temp_dir) / f"{case_name}.json", payload)
                with self.assertRaises(GraphSchemaError):
                    load_graph(graph_path)

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

    def test_graph_edge_bool_fields_require_json_booleans_but_candidate_selected_is_lenient(self) -> None:
        edge = GraphEdge.from_mapping(
            {
                "id": "E001",
                "source": "A",
                "target": "B",
                "metrics": {"cost": 1.0},
                "enabled": False,
                "directed": True,
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

        self.assertFalse(edge.enabled)
        self.assertFalse(edge.bidirectional)
        self.assertFalse(candidate.selected)

    def test_graph_edge_bool_fields_reject_invalid_values(self) -> None:
        with self.assertRaises(GraphSchemaError):
            GraphEdge.from_mapping(
                {
                    "id": "E001",
                    "source": "A",
                    "target": "B",
                    "metrics": {"cost": 1.0},
                    "enabled": "false",
                }
            )
        with self.assertRaises(GraphSchemaError):
            GraphEdge.from_mapping(
                {
                    "id": "E002",
                    "source": "A",
                    "target": "B",
                    "metrics": {"cost": 1.0},
                    "directed": 1,
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



