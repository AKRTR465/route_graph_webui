from __future__ import annotations

import contextlib
import io
import unittest

from route_graph_webui.cli import route_planner as _route_planner_cli
from route_graph_webui.mission_export import config as _mission_config
from route_graph_webui.mission_export import exporter as _mission_exporter
from route_graph_webui.planning import route_planner as _route_planner

DEFAULT_CORNER_MAX_YAW_STEP_DEG = _mission_config.DEFAULT_CORNER_MAX_YAW_STEP_DEG
DEFAULT_CORNER_MIN_ANGLE_DEG = _mission_config.DEFAULT_CORNER_MIN_ANGLE_DEG
DEFAULT_CORNER_RADIUS = _mission_config.DEFAULT_CORNER_RADIUS
DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG = _mission_config.DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG
DEFAULT_TURN_SMOOTHING_ENABLED = _mission_config.DEFAULT_TURN_SMOOTHING_ENABLED
DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG = _mission_config.DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG
DEFAULT_U_TURN_THRESHOLD_DEG = _mission_config.DEFAULT_U_TURN_THRESHOLD_DEG
DEFAULT_U_TURN_TRANSITION_DISTANCE = _mission_config.DEFAULT_U_TURN_TRANSITION_DISTANCE
build_mission_export_parser = _mission_exporter.build_parser
DEFAULT_MAX_EDGE_PASS_FACTOR = _route_planner.DEFAULT_MAX_EDGE_PASS_FACTOR
DEFAULT_MAX_ROUTES = _route_planner.DEFAULT_MAX_ROUTES
build_route_planner_parser = _route_planner_cli.build_parser


class CliArgumentHelperTests(unittest.TestCase):
    def test_route_planner_parser_keeps_graph_and_output_semantics(self) -> None:
        parser = build_route_planner_parser()

        args = parser.parse_args(
            [
                "--graph",
                "graph.json",
                "--start",
                "A",
                "--end",
                "B",
                "--output",
                "candidates.json",
            ]
        )

        self.assertEqual(args.graph, "graph.json")
        self.assertEqual(args.output, "candidates.json")
        self.assertEqual(args.via, [])
        self.assertEqual(args.max_routes, DEFAULT_MAX_ROUTES)
        self.assertEqual(args.max_edge_pass_factor, DEFAULT_MAX_EDGE_PASS_FACTOR)

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--graph", "graph.json", "--start", "A", "--end", "B"])

    def test_mission_export_parser_keeps_graph_output_and_smoothing_defaults(self) -> None:
        parser = build_mission_export_parser()

        args = parser.parse_args(
            [
                "--graph",
                "graph.json",
                "--start",
                "A",
                "--end",
                "B",
                "--output",
                "mission.json",
            ]
        )

        self.assertEqual(args.graph, "graph.json")
        self.assertEqual(args.output, "mission.json")
        self.assertEqual(args.via, [])
        self.assertEqual(args.turn_smoothing_enabled, DEFAULT_TURN_SMOOTHING_ENABLED)
        self.assertEqual(args.corner_radius, DEFAULT_CORNER_RADIUS)
        self.assertEqual(
            args.small_turn_yaw_blend_threshold_deg,
            DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
        )
        self.assertEqual(args.corner_min_angle_deg, DEFAULT_CORNER_MIN_ANGLE_DEG)
        self.assertEqual(args.u_turn_threshold_deg, DEFAULT_U_TURN_THRESHOLD_DEG)
        self.assertEqual(args.u_turn_transition_distance, DEFAULT_U_TURN_TRANSITION_DISTANCE)
        self.assertEqual(args.corner_max_yaw_step_deg, DEFAULT_CORNER_MAX_YAW_STEP_DEG)
        self.assertEqual(args.u_turn_pivot_yaw_step_deg, DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG)

    def test_mission_export_parser_keeps_smoothing_override_destinations(self) -> None:
        parser = build_mission_export_parser()

        args = parser.parse_args(
            [
                "--plan",
                "plan.json",
                "--output",
                "mission.json",
                "--no-turn-smoothing",
                "--corner-radius",
                "12.5",
                "--small-turn-yaw-blend-threshold-deg",
                "8.5",
                "--corner-min-angle-deg",
                "55.0",
                "--u-turn-threshold-deg",
                "150.0",
                "--u-turn-transition-distance",
                "75.0",
                "--corner-max-yaw-step-deg",
                "20.0",
                "--u-turn-pivot-yaw-step-deg",
                "35.0",
            ]
        )

        self.assertFalse(args.turn_smoothing_enabled)
        self.assertEqual(args.corner_radius, 12.5)
        self.assertEqual(args.small_turn_yaw_blend_threshold_deg, 8.5)
        self.assertEqual(args.corner_min_angle_deg, 55.0)
        self.assertEqual(args.u_turn_threshold_deg, 150.0)
        self.assertEqual(args.u_turn_transition_distance, 75.0)
        self.assertEqual(args.corner_max_yaw_step_deg, 20.0)
        self.assertEqual(args.u_turn_pivot_yaw_step_deg, 35.0)


if __name__ == "__main__":
    unittest.main()
