from __future__ import annotations

from tests.route_graph_test_helpers import *

class RoutePlannerProgressTests(unittest.TestCase):
    def test_generate_route_candidates_reports_search_progress_and_completion(self) -> None:
        graph = build_test_square_graph()
        events: list[RoutePlanningProgress] = []

        generate_route_candidates(
            graph,
            "N001",
            "N004",
            max_routes=3,
            progress_callback=events.append,
            progress_interval=1,
        )

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0].phase, "searching")
        self.assertFalse(events[0].done)
        self.assertTrue(events[-1].done)
        self.assertLessEqual(events[-1].expansions, events[-1].max_search_states)
        self.assertEqual(
            [event.expansions for event in events],
            sorted(event.expansions for event in events),
        )

    def test_generate_route_candidates_is_unchanged_without_progress_callback(self) -> None:
        graph = build_test_square_graph()
        baseline = generate_route_candidates(graph, "N001", "N004", max_routes=3)
        with_progress = generate_route_candidates(
            graph,
            "N001",
            "N004",
            max_routes=3,
            progress_callback=lambda _progress: None,
        )

        self.assertEqual(baseline.anchor_nodes, with_progress.anchor_nodes)
        self.assertEqual(baseline.selected_candidate_ids, with_progress.selected_candidate_ids)
        self.assertEqual(
            [candidate.to_dict() for candidate in baseline.candidates],
            [candidate.to_dict() for candidate in with_progress.candidates],
        )
        comparable_meta_keys = {
            "max_routes",
            "max_edge_pass_factor",
            "max_edge_passes",
            "max_search_states",
            "shortest_total_length",
            "shortest_edge_pass_count",
            "candidate_count",
            "truncated",
            "node_z_preprocess_mode",
            "uniform_node_z",
        }
        self.assertEqual(
            {key: baseline.meta[key] for key in comparable_meta_keys},
            {key: with_progress.meta[key] for key in comparable_meta_keys},
        )

    def test_generate_route_candidates_respects_max_total_length(self) -> None:
        graph = build_test_square_graph()

        limited = generate_route_candidates(
            graph,
            "N001",
            "N004",
            max_routes=3,
            max_total_length=150.0,
        )

        self.assertEqual(len(limited.candidates), 1)
        self.assertEqual(limited.candidates[0].candidate_id, "C001")
        self.assertLessEqual(limited.candidates[0].total_length, 150.0)
        self.assertEqual(limited.meta["max_total_length"], 150.0)

        with self.assertRaises(RoutePlanningError):
            generate_route_candidates(
                graph,
                "N001",
                "N004",
                max_routes=3,
                max_total_length=50.0,
            )

    def test_generate_route_candidates_respects_min_total_length(self) -> None:
        graph = build_test_square_graph()

        limited = generate_route_candidates(
            graph,
            "N001",
            "N004",
            max_routes=3,
            min_total_length=150.0,
        )

        self.assertEqual(len(limited.candidates), 2)
        self.assertTrue(all(candidate.total_length >= 150.0 for candidate in limited.candidates))
        self.assertEqual(limited.meta["min_total_length"], 150.0)

        unbounded = generate_route_candidates(
            graph,
            "N001",
            "N004",
            max_routes=3,
            min_total_length=90.0,
        )

        self.assertEqual(len(unbounded.candidates), 3)
        self.assertIsNone(unbounded.meta["min_total_length"])

        with self.assertRaises(RoutePlanningError):
            generate_route_candidates(
                graph,
                "N001",
                "N004",
                max_routes=3,
                min_total_length=160.0,
                max_total_length=150.0,
            )

    def test_generate_route_candidates_searches_detour_when_shortest_is_below_min_length(self) -> None:
        graph = build_test_square_graph()

        candidate_set = generate_route_candidates(
            graph,
            "N001",
            "N004",
            max_routes=1,
            min_total_length=150.0,
        )

        self.assertEqual(len(candidate_set.candidates), 1)
        self.assertEqual(candidate_set.candidates[0].planned_nodes, ["N001", "N003", "N004"])
        self.assertGreaterEqual(candidate_set.candidates[0].total_length, 150.0)
        self.assertEqual(candidate_set.meta["min_total_length"], 150.0)

    def test_generate_route_candidates_keeps_searching_past_short_filtered_detours(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="short_filtered_detours",
            default_altitude=0.0,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
                GraphNode(id="B", name="B", position=[5.0, 0.0, 0.0]),
                GraphNode(id="C", name="C", position=[0.0, 10.0, 0.0]),
                GraphNode(id="D", name="D", position=[0.0, -10.0, 0.0]),
            ],
            edges=[
                GraphEdge(id="E_AB_DIRECT", from_node="A", to_node="B", weight=5.0, bidirectional=True),
                GraphEdge(id="E_AC", from_node="A", to_node="C", weight=10.0, bidirectional=True),
                GraphEdge(id="E_CB", from_node="C", to_node="B", weight=10.0, bidirectional=True),
                GraphEdge(id="E_AD", from_node="A", to_node="D", weight=20.0, bidirectional=True),
                GraphEdge(id="E_DB", from_node="D", to_node="B", weight=20.0, bidirectional=True),
            ],
        )

        candidate_set = generate_route_candidates(
            graph,
            "A",
            "B",
            max_routes=1,
            min_total_length=30.0,
        )

        self.assertEqual(len(candidate_set.candidates), 1)
        self.assertEqual(candidate_set.candidates[0].planned_nodes, ["A", "D", "B"])
        self.assertEqual(candidate_set.candidates[0].total_length, 40.0)
        self.assertEqual(candidate_set.meta["max_routes"], 1)

    def test_manual_filter_auto_keep_requires_all_length_and_frame_filters(self) -> None:
        self.assertTrue(
            filters_require_auto_keep(
                min_total_length_text="100",
                max_total_length_text="250",
                min_frame_count_text="3",
                max_frame_count_text="5",
            )
        )
        self.assertFalse(
            filters_require_auto_keep(
                min_total_length_text="100",
                max_total_length_text="250",
                min_frame_count_text="3",
                max_frame_count_text="",
            )
        )

    def test_manual_filter_auto_keep_rejects_invalid_filter_text(self) -> None:
        with self.assertRaises(GraphSchemaError):
            filters_require_auto_keep(
                min_total_length_text="100",
                max_total_length_text="bad",
                min_frame_count_text="3",
                max_frame_count_text="5",
            )


