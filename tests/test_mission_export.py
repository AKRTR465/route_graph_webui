from __future__ import annotations

import time

from tests.route_graph_test_helpers import *
from mission_export import MissionExportOptions

class MissionExportValidationTests(unittest.TestCase):
    def test_mission_export_options_parse_boolean_strings(self) -> None:
        options = MissionExportOptions.from_mapping({"turn_smoothing_enabled": "false"})

        self.assertFalse(options.turn_smoothing_enabled)
        self.assertFalse(options.to_mission_kwargs()["turn_smoothing_enabled"])

    def test_build_mission_accepts_clock_for_position_time_and_generated_at(self) -> None:
        fixed_time = 1_700_000_000.0
        mission = build_mission_from_plan(
            self._sample_plan(),
            step_distance=50.0,
            turn_smoothing_enabled=False,
            clock=lambda: fixed_time,
        )

        self.assertEqual(mission["positions"][0]["time"], fixed_time)
        self.assertEqual(mission["positions"][1]["time"], fixed_time + 0.25)
        self.assertEqual(
            mission["route_meta"]["generated_at"],
            time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(fixed_time)),
        )

    def _sample_plan(self) -> RoutePlan:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=1)
        return candidate_to_plan(candidate_set, "C001")

    def _mixed_z_plan(self) -> RoutePlan:
        graph = RouteGraph(
            env_id="env",
            graph_name="mixed_z_graph",
            default_altitude=None,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 100.0], yaw_hint=10.0),
                GraphNode(id="B", name="B", position=[100.0, 0.0, 300.0], yaw_hint=20.0),
            ],
            edges=[
                GraphEdge(id="E001", from_node="A", to_node="B", weight=100.0, bidirectional=True),
            ],
        )
        candidate_set = generate_route_candidates(graph, "A", "B", max_routes=1)
        return candidate_to_plan(candidate_set, "C001")

    def _legacy_raw_mixed_z_plan(self) -> RoutePlan:
        return RoutePlan(
            env_id="env",
            graph_name="legacy_mixed_z_plan",
            anchor_nodes=["A", "B"],
            planned_nodes=["A", "B"],
            segments=[
                RouteSegment(
                    start_anchor="A",
                    end_anchor="B",
                    node_ids=["A", "B"],
                    edge_ids=["E001"],
                    length=100.0,
                )
            ],
            total_length=100.0,
            node_lookup={
                "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 100.0], yaw_hint=10.0),
                "B": GraphNode(id="B", name="B", position=[100.0, 0.0, 300.0], yaw_hint=20.0),
            },
        )

    def _node_radius_override_plan(self) -> RoutePlan:
        return RoutePlan(
            env_id="env",
            graph_name="node_radius_override_plan",
            anchor_nodes=["A", "B"],
            planned_nodes=["A", "B"],
            segments=[
                RouteSegment(
                    start_anchor="A",
                    end_anchor="B",
                    node_ids=["A", "B"],
                    edge_ids=["E001"],
                    length=100.0,
                )
            ],
            total_length=100.0,
            node_lookup={
                "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
                "B": GraphNode(id="B", name="B", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
            },
        )

    def _right_angle_plan(self) -> RoutePlan:
        return RoutePlan(
            env_id="env",
            graph_name="right_angle_plan",
            anchor_nodes=["A", "C"],
            planned_nodes=["A", "B", "C"],
            segments=[
                RouteSegment(
                    start_anchor="A",
                    end_anchor="C",
                    node_ids=["A", "B", "C"],
                    edge_ids=["E001", "E002"],
                    length=2000.0,
                )
            ],
            total_length=2000.0,
            node_lookup={
                "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
                "B": GraphNode(id="B", name="B", position=[1000.0, 0.0, 0.0], yaw_hint=45.0),
                "C": GraphNode(id="C", name="C", position=[1000.0, 1000.0, 0.0], yaw_hint=90.0),
            },
        )

    def _u_turn_plan(self) -> RoutePlan:
        return RoutePlan(
            env_id="env",
            graph_name="u_turn_plan",
            anchor_nodes=["A", "C"],
            planned_nodes=["A", "B", "C"],
            segments=[
                RouteSegment(
                    start_anchor="A",
                    end_anchor="C",
                    node_ids=["A", "B", "C"],
                    edge_ids=["E001", "E002"],
                    length=2000.0,
                )
            ],
            total_length=2000.0,
            node_lookup={
                "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
                "B": GraphNode(id="B", name="B", position=[1000.0, 0.0, 0.0], yaw_hint=180.0),
                "C": GraphNode(id="C", name="C", position=[0.0, 0.0, 0.0], yaw_hint=180.0),
            },
        )

    def _landing_yaw_plan(self, *, end_yaw_hint: float) -> RoutePlan:
        graph = RouteGraph(
            env_id="env",
            graph_name="landing_yaw_plan",
            default_altitude=None,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
                GraphNode(id="B", name="B", position=[0.0, 100.0, 0.0], yaw_hint=end_yaw_hint),
            ],
            edges=[
                GraphEdge(id="E001", from_node="A", to_node="B", weight=100.0, bidirectional=True),
            ],
        )
        candidate_set = generate_route_candidates(graph, "A", "B", max_routes=1)
        return candidate_to_plan(candidate_set, "C001")

    def test_group_bridge_export_interpolates_height_between_groups(self) -> None:
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
        candidate_set = generate_route_candidates(graph, "A", "D", max_routes=1)
        plan = candidate_to_plan(candidate_set, "C001")

        mission = build_mission_from_plan(plan, step_distance=50.0, turn_smoothing_enabled=False)

        bridge_samples = [
            position["state"][0][2]
            for position in mission["positions"]
            if position["info"].get("edge_id") == "E_BRIDGE"
        ]
        self.assertGreater(len(bridge_samples), 1)
        self.assertLess(min(bridge_samples), max(bridge_samples))
        self.assertTrue(any(0.0 < sample < 100.0 for sample in bridge_samples))
        self.assertAlmostEqual(max(bridge_samples), 100.0)
        self.assertIn("group_configs_v1", mission["route_meta"])
        self.assertEqual(
            mission["route_meta"]["node_group_lookup_v1"],
            {"A": "#FF0000", "B": "#FF0000", "C": "#00AAFF", "D": "#00AAFF"},
        )

    def test_group_specific_takeoff_and_landing_offsets_can_differ(self) -> None:
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
        plan = candidate_to_plan(generate_route_candidates(graph, "A", "D", max_routes=1), "C001")

        mission = build_mission_from_plan(plan, step_distance=50.0, turn_smoothing_enabled=False)

        first_z = mission["positions"][0]["state"][0][2]
        last_z = mission["positions"][-1]["state"][0][2]
        self.assertAlmostEqual(first_z, 10.0)
        self.assertAlmostEqual(last_z, 50.0)

    def test_rejects_non_positive_step_distance(self) -> None:
        plan = self._sample_plan()

        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(plan, step_distance=0.0)
        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(plan, step_distance=-1.0)
        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(plan, takeoff_landing_step_distance=0.0)
        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(plan, takeoff_landing_step_distance=-1.0)

    def test_rejects_non_positive_fps(self) -> None:
        plan = self._sample_plan()

        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(plan, fps=0.0)
        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(plan, fps=-1.0)

    def test_rejects_negative_node_sample_radius(self) -> None:
        plan = self._sample_plan()

        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(plan, node_sample_radius=-0.1)

    def test_zero_node_sample_radius_keeps_center_point_geometry(self) -> None:
        plan = self._sample_plan()

        default_mission = build_mission_from_plan(plan)
        zero_radius_mission = build_mission_from_plan(
            plan,
            node_sample_radius=0.0,
            random_seed=7,
        )

        self.assertEqual(
            [position["state"] for position in zero_radius_mission["positions"]],
            [position["state"] for position in default_mission["positions"]],
        )
        self.assertEqual(
            zero_radius_mission["route_meta"]["node_sample_radius"],
            0.0,
        )
        self.assertEqual(
            zero_radius_mission["route_meta"]["random_seed"],
            7,
        )
        self.assertEqual(
            zero_radius_mission["route_meta"]["node_sampling_mode"],
            "point_center",
        )

    def test_node_sampling_is_reproducible_with_seed(self) -> None:
        plan = self._sample_plan()

        mission_a = build_mission_from_plan(plan, node_sample_radius=25.0, random_seed=11)
        mission_b = build_mission_from_plan(plan, node_sample_radius=25.0, random_seed=11)
        mission_c = build_mission_from_plan(plan, node_sample_radius=25.0, random_seed=12)

        states_a = [position["state"] for position in mission_a["positions"]]
        states_b = [position["state"] for position in mission_b["positions"]]
        states_c = [position["state"] for position in mission_c["positions"]]

        self.assertEqual(states_a, states_b)
        self.assertNotEqual(states_a, states_c)
        self.assertEqual(mission_a["route_meta"]["node_sampling_mode"], "xy_disk_per_occurrence")

    def test_node_sampling_is_per_occurrence_for_repeated_nodes(self) -> None:
        plan = build_repeated_sampling_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            node_sample_radius=25.0,
            random_seed=5,
            turn_smoothing_enabled=False,
        )
        occurrence_points = [position["state"][0] for position in mission["positions"]]

        self.assertEqual(len(occurrence_points), len(plan.planned_nodes))
        self.assertNotEqual(occurrence_points[0], occurrence_points[3])
        self.assertNotEqual(occurrence_points[1], occurrence_points[4])

    def test_node_sampling_override_uses_node_specific_radius(self) -> None:
        plan = self._node_radius_override_plan()
        plan.node_lookup["B"].meta[NODE_SAMPLE_RADIUS_META_KEY] = 10.0

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            node_sample_radius=0.0,
            random_seed=7,
            turn_smoothing_enabled=False,
        )

        self.assertEqual(mission["positions"][0]["state"][0][:2], [0.0, 0.0])
        self.assertNotEqual(mission["positions"][1]["state"][0][:2], [100.0, 0.0])
        self.assertEqual(mission["route_meta"]["node_sampling_mode"], "xy_disk_per_occurrence")
        self.assertEqual(mission["route_meta"]["node_sample_radius_overrides"], {"B": 10.0})

    def test_node_sampling_override_zero_disables_sampling_for_that_node(self) -> None:
        plan = self._node_radius_override_plan()
        plan.node_lookup["B"].meta[NODE_SAMPLE_RADIUS_META_KEY] = 0.0

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            node_sample_radius=25.0,
            random_seed=7,
            turn_smoothing_enabled=False,
        )

        self.assertNotEqual(mission["positions"][0]["state"][0][:2], [0.0, 0.0])
        self.assertEqual(mission["positions"][1]["state"][0][:2], [100.0, 0.0])
        self.assertEqual(mission["route_meta"]["node_sample_radius_overrides"], {"B": 0.0})

    def test_node_sampling_override_negative_is_rejected(self) -> None:
        plan = self._node_radius_override_plan()
        plan.node_lookup["B"].meta[NODE_SAMPLE_RADIUS_META_KEY] = -1.0

        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(
                plan,
                step_distance=1000.0,
                node_sample_radius=25.0,
            )

    def test_follow_nodes_uses_uniform_mean_z(self) -> None:
        plan = self._mixed_z_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="follow_nodes",
            altitude_offset=5.0,
        )

        self.assertEqual(
            [position["state"][0][2] for position in mission["positions"]],
            [205.0, 205.0],
        )
        self.assertEqual(mission["route_meta"]["node_z_preprocess_mode"], "mean_all_recorded_nodes")
        self.assertEqual(mission["route_meta"]["uniform_node_z"], 200.0)

    def test_fixed_mode_prefers_graph_default_altitude_over_uniform_mean_z(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="default_altitude_graph",
            default_altitude=350.0,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 100.0], yaw_hint=0.0),
                GraphNode(id="B", name="B", position=[100.0, 0.0, 300.0], yaw_hint=0.0),
            ],
            edges=[
                GraphEdge(id="E001", from_node="A", to_node="B", weight=100.0, bidirectional=True),
            ],
        )
        plan = candidate_to_plan(generate_route_candidates(graph, "A", "B", max_routes=1), "C001")

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="fixed",
            fixed_z=None,
        )

        self.assertEqual(
            [position["state"][0][2] for position in mission["positions"]],
            [350.0, 350.0],
        )
        self.assertEqual(mission["route_meta"]["fixed_z"], 350.0)

    def test_fixed_mode_legacy_plan_without_default_altitude_falls_back_to_uniform_mean_z(self) -> None:
        plan = self._legacy_raw_mixed_z_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="fixed",
            fixed_z=None,
        )

        self.assertEqual(
            [position["state"][0][2] for position in mission["positions"]],
            [200.0, 200.0],
        )
        self.assertEqual(mission["route_meta"]["fixed_z"], 200.0)

    def test_turn_smoothing_disabled_preserves_legacy_polyline_geometry(self) -> None:
        plan = self._right_angle_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=500.0,
            turn_smoothing_enabled=False,
        )

        self.assertEqual(
            [position["state"][0][:2] for position in mission["positions"]],
            [
                [0.0, 0.0],
                [500.0, 0.0],
                [1000.0, 0.0],
                [1000.0, 500.0],
                [1000.0, 1000.0],
            ],
        )
        self.assertFalse(mission["route_meta"]["turn_smoothing_enabled"])
        self.assertEqual(mission["route_meta"]["corner_turn_count"], 0)
        self.assertEqual(mission["route_meta"]["u_turn_count"], 0)

    def test_turn_smoothing_applies_local_arc_only_at_corner(self) -> None:
        plan = self._right_angle_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=100.0,
            corner_radius=200.0,
            corner_max_yaw_step_deg=30.0,
        )

        positions = mission["positions"]
        states_xy = [position["state"][0][:2] for position in positions]
        arc_positions = [
            position for position in positions
            if position["info"].get("turn_type") == "left_arc"
        ]
        arc_yaws = [position["state"][1][1] for position in arc_positions]

        self.assertTrue(mission["route_meta"]["turn_smoothing_enabled"])
        self.assertEqual(mission["route_meta"]["corner_turn_count"], 1)
        self.assertEqual(mission["route_meta"]["u_turn_count"], 0)
        self.assertTrue(any(xy == [100.0, 0.0] for xy in states_xy))
        self.assertTrue(any(xy == [800.0, 0.0] for xy in states_xy))
        self.assertTrue(any(xy == [1000.0, 300.0] for xy in states_xy))
        self.assertFalse(any(xy == [1000.0, 0.0] for xy in states_xy))
        self.assertTrue(all(position["info"]["mode"] == "graph_route" for position in arc_positions))
        self.assertEqual({position["info"].get("turn_node_id") for position in arc_positions}, {"B"})
        self.assertTrue(any(position["info"].get("node_id") == "B" for position in arc_positions))
        self.assertTrue(all(0.0 <= yaw <= 90.0 for yaw in arc_yaws))
        self.assertTrue(
            all(
                (arc_yaws[index + 1] - arc_yaws[index]) <= 30.0 + 1e-6
                for index in range(len(arc_yaws) - 1)
            )
        )
        self.assertTrue(
            all(
                (arc_yaws[index + 1] - arc_yaws[index]) >= -1e-6
                for index in range(len(arc_yaws) - 1)
            )
        )

    def test_turn_smoothing_generates_local_u_turn_pivot(self) -> None:
        plan = self._u_turn_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=100.0,
            u_turn_transition_distance=200.0,
            u_turn_pivot_yaw_step_deg=45.0,
        )

        positions = mission["positions"]
        pivot_positions = [
            position for position in positions
            if position["info"]["mode"] == "graph_turn"
        ]
        pivot_xy = [position["state"][0][:2] for position in pivot_positions]
        pivot_yaws = [position["state"][1][1] for position in pivot_positions]

        self.assertEqual(mission["route_meta"]["corner_turn_count"], 0)
        self.assertEqual(mission["route_meta"]["u_turn_count"], 1)
        self.assertTrue(pivot_positions)
        self.assertTrue(all(xy == [1000.0, 0.0] for xy in pivot_xy))
        self.assertEqual(
            {position["info"].get("turn_type") for position in pivot_positions},
            {"u_turn_pivot"},
        )
        self.assertEqual(
            {position["info"].get("turn_node_id") for position in pivot_positions},
            {"B"},
        )
        self.assertTrue(any(position["info"].get("node_id") == "B" for position in pivot_positions))
        self.assertTrue(
            all(
                abs(pivot_yaws[index + 1] - pivot_yaws[index]) <= 45.0 + 1e-6
                for index in range(len(pivot_yaws) - 1)
            )
        )
        straight_prefix = [position["state"][0][:2] for position in positions[:8]]
        self.assertTrue(any(xy == [100.0, 0.0] for xy in straight_prefix))

    def test_legacy_plan_node_lookup_is_normalized_at_export(self) -> None:
        plan = self._legacy_raw_mixed_z_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="follow_nodes",
            altitude_offset=5.0,
        )

        self.assertEqual(
            [position["state"][0][2] for position in mission["positions"]],
            [205.0, 205.0],
        )
        self.assertEqual(mission["route_meta"]["uniform_node_z"], 200.0)

    def test_takeoff_landing_relative_z_adds_vertical_segments(self) -> None:
        plan = self._mixed_z_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="follow_nodes",
            altitude_offset=5.0,
            takeoff_landing_relative_z=10.0,
        )

        positions = mission["positions"]
        self.assertEqual(
            [position["info"]["mode"] for position in positions],
            ["graph_takeoff", "graph_route", "graph_route", "graph_landing"],
        )
        self.assertEqual(
            [position["state"][0][2] for position in positions],
            [195.0, 205.0, 205.0, 195.0],
        )
        self.assertEqual(positions[0]["state"][0][:2], positions[1]["state"][0][:2])
        self.assertEqual(positions[2]["state"][0][:2], positions[3]["state"][0][:2])
        self.assertEqual(positions[0]["info"]["node_id"], "A")
        self.assertIsNone(positions[0]["info"]["edge_id"])
        self.assertIsNone(positions[0]["info"]["segment_index"])
        self.assertIsNone(positions[0]["info"]["pass_index"])
        self.assertEqual(positions[1]["info"]["segment_index"], 0)
        self.assertEqual(mission["route_meta"]["takeoff_landing_relative_z"], 10.0)
        self.assertTrue(mission["route_meta"]["takeoff_landing_enabled"])
        self.assertEqual(mission["route_meta"]["takeoff_landing_step_distance"], 1000.0)
        self.assertEqual(mission["route_meta"]["takeoff_start_z"], 195.0)
        self.assertEqual(mission["route_meta"]["landing_end_z"], 195.0)

    def test_takeoff_landing_step_distance_can_differ_from_route_step_distance(self) -> None:
        plan = self._mixed_z_plan()

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="follow_nodes",
            altitude_offset=5.0,
            takeoff_landing_relative_z=10.0,
            takeoff_landing_step_distance=5.0,
        )

        positions = mission["positions"]
        self.assertEqual(
            [position["info"]["mode"] for position in positions],
            [
                "graph_takeoff",
                "graph_takeoff",
                "graph_route",
                "graph_route",
                "graph_landing",
                "graph_landing",
            ],
        )
        self.assertEqual(
            [position["state"][0][2] for position in positions],
            [195.0, 200.0, 205.0, 205.0, 200.0, 195.0],
        )
        self.assertEqual(
            [position["state"][0][:2] for position in positions[2:4]],
            [[0.0, 0.0], [100.0, 0.0]],
        )
        self.assertEqual(mission["route_meta"]["step_distance"], 1000.0)
        self.assertEqual(mission["route_meta"]["takeoff_landing_step_distance"], 5.0)

    def test_landing_last_frame_keeps_incoming_route_yaw_when_node_hint_conflicts(self) -> None:
        plan = self._landing_yaw_plan(end_yaw_hint=-179.621)

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="fixed",
            fixed_z=100.0,
            takeoff_landing_relative_z=10.0,
        )

        positions = mission["positions"]
        self.assertEqual(
            [position["info"]["mode"] for position in positions],
            ["graph_takeoff", "graph_route", "graph_route", "graph_landing"],
        )
        self.assertEqual(positions[-1]["info"]["node_id"], "B")
        self.assertAlmostEqual(positions[-2]["state"][1][1], 90.0, places=6)
        self.assertAlmostEqual(positions[-1]["state"][1][1], 90.0, places=6)
        self.assertAlmostEqual(
            positions[-1]["state"][1][1],
            positions[-2]["state"][1][1],
            places=6,
        )

    def test_landing_last_frame_does_not_subtly_drift_to_close_node_yaw_hint(self) -> None:
        plan = self._landing_yaw_plan(end_yaw_hint=92.0)

        mission = build_mission_from_plan(
            plan,
            step_distance=1000.0,
            altitude_mode="fixed",
            fixed_z=100.0,
            takeoff_landing_relative_z=10.0,
        )

        last_yaw = mission["positions"][-1]["state"][1][1]
        prev_yaw = mission["positions"][-2]["state"][1][1]

        self.assertAlmostEqual(prev_yaw, 90.0, places=6)
        self.assertAlmostEqual(last_yaw, 90.0, places=6)
        self.assertAlmostEqual(last_yaw, prev_yaw, places=6)
        self.assertNotAlmostEqual(last_yaw, 92.0, places=6)

    def test_takeoff_landing_relative_z_rejects_negative_offset(self) -> None:
        plan = self._mixed_z_plan()

        with self.assertRaises(GraphSchemaError):
            build_mission_from_plan(
                plan,
                step_distance=1000.0,
                altitude_mode="follow_nodes",
                altitude_offset=5.0,
                takeoff_landing_relative_z=-10.0,
            )

    def test_batch_export_uses_selected_candidate_ids_by_default(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=3)
        for candidate in candidate_set.candidates:
            candidate.selected = candidate.candidate_id in {"C002", "C003"}
        candidate_set.sync_selected_ids()

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = export_candidate_set_missions(candidate_set, temp_dir)

            self.assertEqual(summary["requested_candidate_ids"], ["C002", "C003"])
            self.assertEqual(summary["succeeded"], ["C002", "C003"])
            self.assertEqual(summary["failed"], [])
            self.assertTrue((Path(temp_dir) / "test_square_graph_C002.json").exists())
            self.assertTrue((Path(temp_dir) / "test_square_graph_C003.json").exists())
            self.assertFalse((Path(temp_dir) / "test_square_graph_C001.json").exists())

    def test_batch_export_candidate_ids_override_selected_candidates(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=3)
        for candidate in candidate_set.candidates:
            candidate.selected = candidate.candidate_id == "C001"
        candidate_set.sync_selected_ids()

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = export_candidate_set_missions(
                candidate_set,
                temp_dir,
                candidate_ids=["C003"],
            )

            self.assertEqual(summary["requested_candidate_ids"], ["C003"])
            self.assertEqual(summary["succeeded"], ["C003"])
            self.assertEqual(summary["failed"], [])
            self.assertTrue((Path(temp_dir) / "test_square_graph_C003.json").exists())
            self.assertFalse((Path(temp_dir) / "test_square_graph_C001.json").exists())

    def test_batch_export_avoids_overwriting_existing_mission_files(self) -> None:
        graph = build_test_square_graph()
        first_candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=2)
        second_candidate_set = generate_route_candidates(graph, "N001", "N003", max_routes=2)

        with tempfile.TemporaryDirectory() as temp_dir:
            first_summary = export_candidate_set_missions(
                first_candidate_set,
                temp_dir,
                candidate_ids=["C001"],
            )
            second_summary = export_candidate_set_missions(
                second_candidate_set,
                temp_dir,
                candidate_ids=["C001"],
            )

            first_path = Path(first_summary["written_files"]["C001"])
            second_path = Path(second_summary["written_files"]["C001"])

            self.assertEqual(first_path.name, "test_square_graph_C001.json")
            self.assertEqual(second_path.name, "test_square_graph_C002.json")
            self.assertNotEqual(first_path, second_path)

            first_mission = json.loads(first_path.read_text(encoding="utf-8"))
            second_mission = json.loads(second_path.read_text(encoding="utf-8"))

            self.assertEqual(first_mission["route_meta"]["anchor_nodes"], ["N001", "N004"])
            self.assertEqual(second_mission["route_meta"]["anchor_nodes"], ["N001", "N003"])
            self.assertEqual(first_mission["route_meta"]["candidate_id"], "C001")
            self.assertEqual(second_mission["route_meta"]["candidate_id"], "C001")

    def test_batch_export_legacy_suffix_files_still_advance_plain_c_counter(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=1)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_json_file(output_dir / "test_square_graph_C001.json", {"positions": [], "route_meta": {}})
            write_json_file(output_dir / "test_square_graph_C001_001.json", {"positions": [], "route_meta": {}})

            summary = export_candidate_set_missions(
                candidate_set,
                output_dir,
                candidate_ids=["C001"],
            )

            written_path = Path(summary["written_files"]["C001"])
            self.assertEqual(written_path.name, "test_square_graph_C002.json")

    def test_batch_export_assigns_consecutive_new_c_numbers_within_one_batch(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=3)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            for index in range(1, 6):
                write_json_file(
                    output_dir / f"test_square_graph_C{index:03d}.json",
                    {"positions": [], "route_meta": {}},
                )

            summary = export_candidate_set_missions(
                candidate_set,
                output_dir,
                candidate_ids=["C002", "C003"],
            )

            self.assertEqual(
                {candidate_id: Path(path).name for candidate_id, path in summary["written_files"].items()},
                {
                    "C002": "test_square_graph_C006.json",
                    "C003": "test_square_graph_C007.json",
                },
            )

    def test_batch_export_rejects_empty_selected_candidates(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=2)
        for candidate in candidate_set.candidates:
            candidate.selected = False
        candidate_set.sync_selected_ids()

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(GraphSchemaError) as ctx:
                export_candidate_set_missions(candidate_set, temp_dir)

        self.assertIn("no selected candidates", str(ctx.exception).lower())

    def test_batch_export_reports_partial_success(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=2)
        for candidate in candidate_set.candidates:
            candidate.selected = False
        candidate_set.candidates[0].selected = True
        bad_candidate = RouteCandidate.from_mapping(candidate_set.candidates[0].to_dict())
        bad_candidate.candidate_id = "CBAD"
        bad_candidate.selected = True
        bad_candidate.planned_nodes = ["N001", "MISSING"]
        bad_candidate.segments[0].node_ids = ["N001", "MISSING"]
        candidate_set.candidates.append(bad_candidate)
        candidate_set.sync_selected_ids()

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = export_candidate_set_missions(candidate_set, temp_dir)

            self.assertIn("C001", summary["succeeded"])
            self.assertIn("CBAD", summary["failed"])
            self.assertIn("CBAD", summary["errors"])
            self.assertTrue((Path(temp_dir) / "test_square_graph_C001.json").exists())
            self.assertFalse((Path(temp_dir) / "test_square_graph_CBAD.json").exists())

    def test_batch_export_supports_auto_planned_candidates_with_empty_anchor_nodes(self) -> None:
        graph = build_test_square_graph()
        candidate_set = auto_plan_routes(
            graph,
            AutoPlanningConfig(
                max_output_routes=3,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=50.0,
                min_frame_count=2,
                max_frame_count=4,
            ),
        )
        self.assertEqual(candidate_set.anchor_nodes, [])
        for candidate in candidate_set.candidates[:2]:
            candidate.selected = True
        for candidate in candidate_set.candidates[2:]:
            candidate.selected = False
        candidate_set.sync_selected_ids()

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = export_candidate_set_missions(candidate_set, temp_dir)

            self.assertEqual(summary["failed"], [])
            self.assertEqual(len(summary["succeeded"]), 2)
            for candidate_id in summary["succeeded"]:
                mission = json.loads(Path(summary["written_files"][candidate_id]).read_text(encoding="utf-8"))
                candidate = candidate_set.get_candidate(candidate_id)
                self.assertEqual(
                    mission["route_meta"]["anchor_nodes"],
                    [
                        str(candidate.meta["auto_start_node"]),
                        str(candidate.meta["auto_end_node"]),
                    ],
                )

    def test_rejects_plan_with_missing_lookup_node(self) -> None:
        plan = RoutePlan(
            env_id="env",
            graph_name="graph",
            anchor_nodes=["A", "B"],
            planned_nodes=["A", "Z"],
            segments=[
                RouteSegment(
                    start_anchor="A",
                    end_anchor="B",
                    node_ids=["A", "Z"],
                    edge_ids=["E001"],
                    length=1.0,
                )
            ],
            total_length=1.0,
            node_lookup={
                "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
            },
        )

        with self.assertRaises(GraphSchemaError) as ctx:
            ensure_valid_plan(plan)

        self.assertIn("missing-plan-node", str(ctx.exception))

    def test_rejects_plan_with_anchor_segment_mismatch(self) -> None:
        plan = RoutePlan(
            env_id="env",
            graph_name="graph",
            anchor_nodes=["A", "B", "C"],
            planned_nodes=["A", "C"],
            segments=[
                RouteSegment(
                    start_anchor="A",
                    end_anchor="C",
                    node_ids=["A", "C"],
                    edge_ids=["E001"],
                    length=1.0,
                )
            ],
            total_length=1.0,
            node_lookup={
                "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
                "B": GraphNode(id="B", name="B", position=[1.0, 0.0, 0.0]),
                "C": GraphNode(id="C", name="C", position=[2.0, 0.0, 0.0]),
            },
        )

        with self.assertRaises(GraphSchemaError) as ctx:
            ensure_valid_plan(plan)

        self.assertIn("anchor-segment-count-mismatch", str(ctx.exception))
        self.assertIn("segment-anchor-mismatch", str(ctx.exception))


