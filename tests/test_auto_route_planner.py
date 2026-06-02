from __future__ import annotations

from tests.route_graph_test_helpers import *

class AutoRoutePlannerTests(unittest.TestCase):
    def test_compute_anchor_node_scores_prefers_more_connected_nodes(self) -> None:
        graph = build_test_square_graph()
        scores = compute_anchor_node_scores(graph)
        self.assertGreaterEqual(scores["N001"], scores["N002"])
        self.assertGreaterEqual(scores["N003"], scores["N004"])

    def test_auto_planning_config_normalizes_allowed_route_group_colors(self) -> None:
        config = AutoPlanningConfig.from_mapping(
            {
                "allowed_route_group_colors": ["#ff0000", " #00ff00 ", "#FF0000", None, ""],
            }
        )

        self.assertEqual(config.allowed_route_group_colors, ("#FF0000", "#00FF00"))

    def test_auto_planning_config_rejects_invalid_allowed_route_group_color(self) -> None:
        with self.assertRaises(AutoRoutePlanningError):
            AutoPlanningConfig.from_mapping(
                {
                    "allowed_route_group_colors": ["not-a-color"],
                }
            )

    def test_auto_planning_config_normalizes_excluded_endpoint_group_colors(self) -> None:
        config = AutoPlanningConfig.from_mapping(
            {
                "excluded_endpoint_group_colors": ["#ff0000", " #00ff00 ", "#FF0000", None, ""],
            }
        )

        self.assertEqual(config.excluded_endpoint_group_colors, ("#FF0000", "#00FF00"))

    def test_auto_planning_config_rejects_invalid_excluded_endpoint_group_color(self) -> None:
        with self.assertRaises(AutoRoutePlanningError):
            AutoPlanningConfig.from_mapping(
                {
                    "excluded_endpoint_group_colors": ["not-a-color"],
                }
            )

    def test_auto_plan_routes_keeps_reverse_direction_routes(self) -> None:
        graph = build_test_square_graph()
        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=12,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=50.0,
                min_frame_count=2,
                max_frame_count=3,
            ),
        )
        route_pairs = {
            (candidate.meta.get("auto_start_node"), candidate.meta.get("auto_end_node"))
            for candidate in candidate_set.candidates
        }
        self.assertIn(("N001", "N004"), route_pairs)
        self.assertIn(("N004", "N001"), route_pairs)

    def test_auto_plan_routes_records_coverage_metadata(self) -> None:
        graph = build_test_square_graph()
        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=3,
                max_routes_per_pair=2,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=50.0,
                min_frame_count=2,
                max_frame_count=4,
            ),
        )
        self.assertEqual(candidate_set.meta["planning_mode"], "auto")
        self.assertTrue(candidate_set.meta["global_coverage_optimized"])
        self.assertGreater(candidate_set.meta["directed_edge_coverage_count"], 0)
        self.assertGreater(candidate_set.meta["physical_edge_coverage_count"], 0)
        self.assertGreater(candidate_set.meta["node_coverage_count"], 0)
        self.assertTrue(all("estimated_frames" in candidate.meta for candidate in candidate_set.candidates))

    def test_auto_plan_routes_uses_real_export_frames_for_frame_constraints(self) -> None:
        graph = build_group_bridge_graph()
        write_graph_group_configs(
            graph.meta,
            {
                "#FF0000": {
                    "altitude_mode": "fixed",
                    "fixed_z": "20",
                    "altitude_offset": "0",
                    "node_sample_radius": "0",
                    "takeoff_landing_relative_z": "30",
                    "takeoff_landing_step_distance": "10",
                },
                "#00AAFF": {
                    "altitude_mode": "fixed",
                    "fixed_z": "80",
                    "altitude_offset": "0",
                    "node_sample_radius": "0",
                    "takeoff_landing_relative_z": "30",
                    "takeoff_landing_step_distance": "10",
                },
            },
        )

        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=12,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=100.0,
                min_frame_count=11,
                max_frame_count=11,
                export_config=AutoPlanningExportConfig(
                    step_distance=100.0,
                    fps=4.0,
                    turn_smoothing_enabled=False,
                ),
            ),
        )

        candidate = next(
            (
                item
                for item in candidate_set.candidates
                if item.meta.get("auto_start_node") == "A" and item.meta.get("auto_end_node") == "D"
            ),
            None,
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.meta["frame_estimation_mode"], "export_mission")
        self.assertEqual(candidate.meta["frame_estimation_step_distance"], 100.0)
        self.assertEqual(candidate.meta["frame_count"], 11)
        self.assertEqual(candidate.meta["estimated_frames"], 11)
        self.assertGreater(candidate.meta["estimated_export_total_length"], candidate.total_length)
        self.assertEqual(candidate_set.meta["frame_estimation_mode"], "export_mission")
        self.assertEqual(candidate_set.meta["frame_estimation_step_distance"], 100.0)

        plan = candidate_to_plan(candidate_set, candidate.candidate_id)
        mission = build_mission_from_plan(
            plan,
            step_distance=100.0,
            turn_smoothing_enabled=False,
        )
        self.assertEqual(len(mission["positions"]), 11)

    def test_auto_plan_routes_keeps_pairs_whose_shortest_route_is_below_min_length(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="auto_shortest_below_min",
            default_altitude=0.0,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
                GraphNode(id="B", name="B", position=[5.0, 0.0, 0.0]),
                GraphNode(id="C", name="C", position=[20.0, 0.0, 0.0]),
            ],
            edges=[
                GraphEdge(id="E_AB_DIRECT", from_node="A", to_node="B", weight=5.0, bidirectional=True),
                GraphEdge(id="E_AC", from_node="A", to_node="C", weight=20.0, bidirectional=True),
                GraphEdge(id="E_CB", from_node="C", to_node="B", weight=20.0, bidirectional=True),
            ],
        )

        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=2,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=6,
                min_total_length=30.0,
                max_total_length=50.0,
                distance_per_frame=10.0,
            ),
        )

        self.assertTrue(candidate_set.candidates)
        self.assertTrue(all(candidate.total_length >= 30.0 for candidate in candidate_set.candidates))
        self.assertTrue(
            any(
                candidate.planned_nodes in (["A", "C", "B"], ["B", "C", "A"])
                for candidate in candidate_set.candidates
            )
        )

    def test_auto_plan_routes_oversamples_before_export_frame_filtering(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="auto_export_frame_oversample",
            default_altitude=0.0,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
                GraphNode(id="B", name="B", position=[5.0, 0.0, 0.0]),
                GraphNode(id="C", name="C", position=[20.0, 0.0, 0.0]),
            ],
            edges=[
                GraphEdge(id="E_AB_DIRECT", from_node="A", to_node="B", weight=5.0, bidirectional=True),
                GraphEdge(id="E_AC", from_node="A", to_node="C", weight=20.0, bidirectional=True),
                GraphEdge(id="E_CB", from_node="C", to_node="B", weight=20.0, bidirectional=True),
            ],
        )

        class FakeEstimate:
            def __init__(self, *, frame_count: int, total_length: float) -> None:
                self.frame_count = frame_count
                self.total_length = total_length

        class FakeExportEstimator:
            def __init__(self, **_kwargs) -> None:
                pass

            def estimate(self, candidate, *, pair):
                frame_count = 4 if candidate.total_length >= 30.0 else 1
                return FakeEstimate(frame_count=frame_count, total_length=candidate.total_length)

        with mock.patch.object(auto_route_planner_module, "_AutoExportEstimator", FakeExportEstimator):
            candidate_set = auto_plan_routes(
                graph,
                AutoPlanningConfig(
                    max_output_routes=2,
                    max_routes_per_pair=1,
                    max_anchor_pairs_to_evaluate=6,
                    min_frame_count=4,
                    max_frame_count=4,
                    distance_per_frame=100.0,
                    export_config=AutoPlanningExportConfig(
                        step_distance=100.0,
                        fps=4.0,
                        turn_smoothing_enabled=False,
                    ),
                ),
            )

        self.assertTrue(candidate_set.candidates)
        self.assertGreater(candidate_set.meta["search_routes_per_pair"], candidate_set.meta["max_routes_per_pair"])
        self.assertTrue(all(candidate.meta["frame_count"] == 4 for candidate in candidate_set.candidates))
        self.assertTrue(all(candidate.total_length >= 30.0 for candidate in candidate_set.candidates))

    def test_auto_plan_routes_with_empty_allowed_groups_matches_default_behavior(self) -> None:
        graph = build_three_group_corridor_graph()
        baseline = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=4,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=20,
                distance_per_frame=100.0,
                min_total_length=250.0,
                max_total_length=500.0,
            ),
        )
        with_empty_allowed = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=4,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=20,
                distance_per_frame=100.0,
                min_total_length=250.0,
                max_total_length=500.0,
                allowed_route_group_colors=(),
            ),
        )

        baseline_signatures = [tuple(candidate.planned_nodes) for candidate in baseline.candidates]
        filtered_signatures = [tuple(candidate.planned_nodes) for candidate in with_empty_allowed.candidates]
        self.assertEqual(filtered_signatures, baseline_signatures)
        self.assertEqual(with_empty_allowed.meta["allowed_route_group_colors"], [])

    def test_auto_plan_routes_limits_all_planned_nodes_to_allowed_groups(self) -> None:
        graph = build_three_group_corridor_graph()
        write_graph_group_configs(
            graph.meta,
            {
                "#FF0000": {"altitude_mode": "fixed", "fixed_z": "", "altitude_offset": "0", "node_sample_radius": "0", "takeoff_landing_relative_z": "", "takeoff_landing_step_distance": ""},
                "#00FF00": {"altitude_mode": "fixed", "fixed_z": "", "altitude_offset": "0", "node_sample_radius": "0", "takeoff_landing_relative_z": "", "takeoff_landing_step_distance": ""},
                "#0000FF": {"altitude_mode": "fixed", "fixed_z": "", "altitude_offset": "0", "node_sample_radius": "0", "takeoff_landing_relative_z": "", "takeoff_landing_step_distance": ""},
            },
        )

        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=4,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=20,
                distance_per_frame=100.0,
                min_total_length=250.0,
                max_total_length=400.0,
                allowed_route_group_colors=("#FF0000", "#00FF00"),
            ),
        )

        allowed_nodes = {"A", "B", "C", "D"}
        self.assertEqual(candidate_set.meta["allowed_route_group_colors"], ["#FF0000", "#00FF00"])
        self.assertTrue(candidate_set.candidates)
        self.assertTrue(all(set(candidate.planned_nodes).issubset(allowed_nodes) for candidate in candidate_set.candidates))
        self.assertTrue(
            any(
                any(edge_pass.edge_id == "E_RED_TO_GREEN" for edge_pass in candidate.edge_passes)
                for candidate in candidate_set.candidates
            )
        )
        self.assertEqual(set(candidate_set.meta["group_configs_v1"]), {"#FF0000", "#00FF00"})
        self.assertEqual(set(candidate_set.meta["node_group_lookup_v1"].values()), {"#FF0000", "#00FF00"})
        self.assertEqual(set(candidate_set.meta["node_group_lookup_v1"]), allowed_nodes)
        self.assertEqual(set(candidate_set.node_lookup), allowed_nodes)

    def test_auto_plan_routes_excludes_selected_groups_from_endpoints_only(self) -> None:
        graph = build_three_group_corridor_graph()
        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=6,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=20,
                distance_per_frame=100.0,
                min_total_length=250.0,
                max_total_length=500.0,
                excluded_endpoint_group_colors=("#00FF00",),
            ),
        )

        excluded_nodes = {"C", "D"}
        self.assertEqual(candidate_set.meta["excluded_endpoint_group_colors"], ["#00FF00"])
        self.assertTrue(candidate_set.candidates)
        self.assertTrue(
            all(candidate.meta.get("auto_start_node") not in excluded_nodes for candidate in candidate_set.candidates)
        )
        self.assertTrue(
            all(candidate.meta.get("auto_end_node") not in excluded_nodes for candidate in candidate_set.candidates)
        )
        self.assertTrue(
            any(
                any(node_id in excluded_nodes for node_id in candidate.planned_nodes[1:-1])
                for candidate in candidate_set.candidates
            )
        )

    def test_auto_plan_routes_combines_allowed_groups_with_endpoint_exclusion(self) -> None:
        graph = build_three_group_corridor_graph()
        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=6,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=20,
                distance_per_frame=100.0,
                max_total_length=500.0,
                allowed_route_group_colors=("#FF0000", "#00FF00"),
                excluded_endpoint_group_colors=("#00FF00",),
            ),
        )

        allowed_nodes = {"A", "B", "C", "D"}
        excluded_endpoint_nodes = {"C", "D"}
        self.assertTrue(candidate_set.candidates)
        self.assertTrue(all(set(candidate.planned_nodes).issubset(allowed_nodes) for candidate in candidate_set.candidates))
        self.assertTrue(
            all(candidate.meta.get("auto_start_node") not in excluded_endpoint_nodes for candidate in candidate_set.candidates)
        )
        self.assertTrue(
            all(candidate.meta.get("auto_end_node") not in excluded_endpoint_nodes for candidate in candidate_set.candidates)
        )

    def test_auto_plan_routes_rejects_allowed_group_colors_not_in_graph(self) -> None:
        graph = build_three_group_corridor_graph()

        with self.assertRaises(AutoRoutePlanningError) as context:
            auto_plan_routes(
                graph,
                AutoPlanningConfig(
                    max_output_routes=4,
                    max_routes_per_pair=1,
                    max_anchor_pairs_to_evaluate=20,
                    distance_per_frame=100.0,
                    allowed_route_group_colors=("#ABCDEF",),
                ),
            )

        self.assertIn("Allowed route groups are not present", str(context.exception))

    def test_auto_plan_routes_reports_when_allowed_groups_leave_no_valid_routes(self) -> None:
        graph = build_three_group_corridor_graph()

        with self.assertRaises(AutoRoutePlanningError) as context:
            auto_plan_routes(
                graph,
                AutoPlanningConfig(
                    max_output_routes=4,
                    max_routes_per_pair=1,
                    max_anchor_pairs_to_evaluate=20,
                    distance_per_frame=100.0,
                    min_total_length=250.0,
                    max_total_length=500.0,
                    allowed_route_group_colors=("#FF0000",),
                ),
            )

        self.assertIn("allowed route groups", str(context.exception).lower())

    def test_auto_plan_routes_reports_when_excluded_groups_remove_all_endpoint_nodes(self) -> None:
        graph = build_group_bridge_graph()

        with self.assertRaises(AutoRoutePlanningError) as context:
            auto_plan_routes(
                graph,
                AutoPlanningConfig(
                    max_output_routes=4,
                    max_routes_per_pair=1,
                    max_anchor_pairs_to_evaluate=12,
                    distance_per_frame=50.0,
                    min_frame_count=1,
                    max_frame_count=10,
                    excluded_endpoint_group_colors=("#FF0000", "#00AAFF"),
                ),
            )

        self.assertIn("Excluded endpoint groups", str(context.exception))

    def test_auto_plan_routes_preserves_grouped_export_metadata(self) -> None:
        graph = build_group_bridge_graph()
        write_graph_group_configs(
            graph.meta,
            {
                "#FF0000": {
                    "altitude_mode": "fixed",
                    "fixed_z": "",
                    "altitude_offset": "0",
                    "node_sample_radius": "0",
                    "takeoff_landing_relative_z": "",
                    "takeoff_landing_step_distance": "",
                },
                "#00AAFF": {
                    "altitude_mode": "fixed",
                    "fixed_z": "",
                    "altitude_offset": "0",
                    "node_sample_radius": "0",
                    "takeoff_landing_relative_z": "",
                    "takeoff_landing_step_distance": "",
                },
            },
        )

        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=4,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=50.0,
                min_frame_count=1,
                max_frame_count=10,
            ),
        )

        self.assertEqual({node.position[2] for node in candidate_set.node_lookup.values()}, {50.0})
        self.assertEqual(candidate_set.meta["node_z_preprocess_mode"], "mean_all_recorded_nodes")
        self.assertEqual(candidate_set.meta["uniform_node_z"], 50.0)
        self.assertEqual(
            candidate_set.meta["node_group_lookup_v1"],
            {"A": "#FF0000", "B": "#FF0000", "C": "#00AAFF", "D": "#00AAFF"},
        )
        self.assertEqual(candidate_set.meta["group_average_z_lookup_v1"], {"#00AAFF": 100.0, "#FF0000": 0.0})
        self.assertEqual(
            candidate_set.meta["original_node_z_lookup_v1"],
            {"A": 0.0, "B": 0.0, "C": 100.0, "D": 100.0},
        )
        self.assertIn("group_configs_v1", candidate_set.meta)

    def test_auto_planned_group_bridge_export_uses_grouped_context(self) -> None:
        graph = build_group_bridge_graph()
        write_graph_group_configs(
            graph.meta,
            {
                "#FF0000": {
                    "altitude_mode": "fixed",
                    "fixed_z": "20",
                    "altitude_offset": "0",
                    "node_sample_radius": "0",
                    "takeoff_landing_relative_z": "10",
                    "takeoff_landing_step_distance": "5",
                },
                "#00AAFF": {
                    "altitude_mode": "fixed",
                    "fixed_z": "80",
                    "altitude_offset": "0",
                    "node_sample_radius": "0",
                    "takeoff_landing_relative_z": "30",
                    "takeoff_landing_step_distance": "6",
                },
            },
        )

        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=12,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=50.0,
                min_frame_count=1,
                max_frame_count=10,
            ),
        )
        candidate = next(
            (
                item
                for item in candidate_set.candidates
                if item.meta.get("auto_start_node") == "A" and item.meta.get("auto_end_node") == "D"
            ),
            None,
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None

        plan = candidate_to_plan(candidate_set, candidate.candidate_id)
        mission = build_mission_from_plan(plan, step_distance=50.0, turn_smoothing_enabled=False)

        bridge_samples = [
            position["state"][0][2]
            for position in mission["positions"]
            if position["info"].get("edge_id") == "E_BRIDGE"
        ]
        self.assertGreater(len(bridge_samples), 1)
        self.assertLess(min(bridge_samples), max(bridge_samples))
        self.assertTrue(any(20.0 < sample < 80.0 for sample in bridge_samples))
        self.assertEqual(
            mission["route_meta"]["node_group_lookup_v1"],
            {"A": "#FF0000", "B": "#FF0000", "C": "#00AAFF", "D": "#00AAFF"},
        )
        self.assertEqual(set(mission["route_meta"]["group_configs_v1"]), {"#FF0000", "#00AAFF"})
        self.assertAlmostEqual(mission["positions"][0]["state"][0][2], 10.0)
        self.assertAlmostEqual(mission["positions"][-1]["state"][0][2], 50.0)



class RouteGenerationWorkerTests(unittest.TestCase):
    def test_worker_emits_progress_and_success_messages(self) -> None:
        graph = build_test_square_graph()
        message_queue: queue.Queue[dict] = queue.Queue()

        run_route_generation_task(
            {
                "job_id": 7,
                "graph": graph.to_dict(),
                "start": "N001",
                "via": [],
                "end": "N004",
                "max_routes": 3,
                "max_edge_pass_factor": 2.5,
                "max_search_states": 50000,
                "progress_interval": 1,
            },
            message_queue,
        )

        messages: list[dict] = []
        while not message_queue.empty():
            messages.append(message_queue.get_nowait())

        self.assertTrue(any(message["type"] == "progress" for message in messages))
        self.assertEqual(messages[-1]["type"], "success")
        self.assertTrue(all(message["job_id"] == 7 for message in messages))
        self.assertIn("candidate_set", messages[-1])

    def test_worker_returns_error_message_for_invalid_anchor(self) -> None:
        graph = build_test_square_graph()
        message_queue: queue.Queue[dict] = queue.Queue()

        run_route_generation_task(
            {
                "job_id": 8,
                "graph": graph.to_dict(),
                "start": "N001",
                "via": [],
                "end": "MISSING",
                "max_routes": 3,
                "max_edge_pass_factor": 2.5,
                "max_search_states": 50000,
                "progress_interval": 1,
            },
            message_queue,
        )

        messages: list[dict] = []
        while not message_queue.empty():
            messages.append(message_queue.get_nowait())

        self.assertEqual(messages[-1]["type"], "error")
        self.assertEqual(messages[-1]["job_id"], 8)
        self.assertIn("does not exist", messages[-1]["error"])
        self.assertIn("error_type", messages[-1])

    def test_worker_supports_auto_planning_mode(self) -> None:
        graph = build_test_square_graph()
        message_queue: queue.Queue[dict] = queue.Queue()

        run_route_generation_task(
            {
                "job_id": 10,
                "graph": graph.to_dict(),
                "planning_mode": "auto",
                "auto_config": {
                    "max_output_routes": 3,
                    "max_routes_per_pair": 1,
                    "max_anchor_pairs_to_evaluate": 12,
                    "distance_per_frame": 50.0,
                    "min_frame_count": 2,
                    "max_frame_count": 4,
                },
            },
            message_queue,
        )

        messages: list[dict] = []
        while not message_queue.empty():
            messages.append(message_queue.get_nowait())

        progress_messages = [message for message in messages if message["type"] == "progress"]
        self.assertTrue(progress_messages)
        self.assertTrue(
            any(
                {"searched_candidates", "filtered_candidates", "kept_candidates"}.issubset(
                    message["progress"]
                )
                for message in progress_messages
            )
        )
        self.assertEqual(messages[-1]["type"], "success")
        self.assertEqual(messages[-1]["candidate_set"]["meta"]["planning_mode"], "auto")

    def test_worker_auto_planning_passes_through_excluded_endpoint_group_colors(self) -> None:
        graph = build_three_group_corridor_graph()
        message_queue: queue.Queue[dict] = queue.Queue()

        run_route_generation_task(
            {
                "job_id": 11,
                "graph": graph.to_dict(),
                "planning_mode": "auto",
                "auto_config": {
                    "max_output_routes": 4,
                    "max_routes_per_pair": 1,
                    "max_anchor_pairs_to_evaluate": 20,
                    "distance_per_frame": 100.0,
                    "min_total_length": 250.0,
                    "max_total_length": 500.0,
                    "excluded_endpoint_group_colors": ["#00ff00"],
                },
            },
            message_queue,
        )

        messages: list[dict] = []
        while not message_queue.empty():
            messages.append(message_queue.get_nowait())

        self.assertEqual(messages[-1]["type"], "success")
        candidate_set = messages[-1]["candidate_set"]
        self.assertEqual(candidate_set["meta"]["excluded_endpoint_group_colors"], ["#00FF00"])
        excluded_nodes = {"C", "D"}
        for candidate in candidate_set["candidates"]:
            self.assertNotIn(candidate["meta"].get("auto_start_node"), excluded_nodes)
            self.assertNotIn(candidate["meta"].get("auto_end_node"), excluded_nodes)

    def test_worker_auto_planning_passes_through_allowed_route_group_colors(self) -> None:
        graph = build_three_group_corridor_graph()
        message_queue: queue.Queue[dict] = queue.Queue()

        run_route_generation_task(
            {
                "job_id": 12,
                "graph": graph.to_dict(),
                "planning_mode": "auto",
                "auto_config": {
                    "max_output_routes": 4,
                    "max_routes_per_pair": 1,
                    "max_anchor_pairs_to_evaluate": 20,
                    "distance_per_frame": 100.0,
                    "min_total_length": 250.0,
                    "max_total_length": 400.0,
                    "allowed_route_group_colors": ["#ff0000", "#00ff00"],
                },
            },
            message_queue,
        )

        messages: list[dict] = []
        while not message_queue.empty():
            messages.append(message_queue.get_nowait())

        self.assertEqual(messages[-1]["type"], "success")
        candidate_set = messages[-1]["candidate_set"]
        self.assertEqual(candidate_set["meta"]["allowed_route_group_colors"], ["#FF0000", "#00FF00"])
        allowed_nodes = {"A", "B", "C", "D"}
        for candidate in candidate_set["candidates"]:
            self.assertTrue(set(candidate["planned_nodes"]).issubset(allowed_nodes))

        graph = build_test_square_graph()

        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "job_id": 9,
                        "graph": graph.to_dict(),
                        "start": "N001",
                        "via": [],
                        "end": "N004",
                        "max_routes": 1,
                        "max_edge_pass_factor": 2.5,
                        "max_search_states": 50000,
                        "progress_interval": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "route_graph_webui.apps.workers.route_generation",
                    "--payload",
                    str(payload_path),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        messages = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        self.assertTrue(any(message["type"] == "progress" for message in messages))
        self.assertEqual(messages[-1]["type"], "success")
        self.assertEqual(messages[-1]["job_id"], 9)

    def test_file_message_queue_writes_terminal_messages_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = _FileMessageQueue(temp_dir)

            queue.put({"type": "success", "job_id": 11, "candidate_set": {"env_id": "env"}})
            result_payload = json.loads(queue.result_path.read_text(encoding="utf-8"))

            self.assertEqual(result_payload["job_id"], 11)
            self.assertFalse((queue.result_path.with_name(f"{queue.result_path.name}.tmp")).exists())

            queue.put({"type": "error", "job_id": 11, "error": "boom"})
            error_payload = json.loads(queue.error_path.read_text(encoding="utf-8"))

            self.assertEqual(error_payload["error"], "boom")
            self.assertFalse((queue.error_path.with_name(f"{queue.error_path.name}.tmp")).exists())



