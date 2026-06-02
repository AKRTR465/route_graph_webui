import unittest

from route_graph_webui.cli import graph_gui as _graph_gui
from route_graph_webui.graph.editor import GraphEditor
from route_graph_webui.graph.meta import (
    DEFAULT_GROUP_COLOR,
    EDGE_GROUP_COLOR_META_KEY,
    EDGE_KIND_BRIDGE,
    EDGE_KIND_GROUP,
    EDGE_KIND_META_KEY,
)
from route_graph_webui.graph.model import GraphEdge, GraphNode, RouteGraph

PENDING_GROUP_STATUS_PREFIX = _graph_gui.PENDING_GROUP_STATUS_PREFIX
build_group_control_state = _graph_gui.build_group_control_state
derive_used_group_colors = _graph_gui.derive_used_group_colors
derive_palette_colors = _graph_gui.derive_palette_colors
format_paint_mode_status = _graph_gui.format_paint_mode_status
format_insert_mode_status = _graph_gui.format_insert_mode_status
project_point_to_segment_ratio = _graph_gui.project_point_to_segment_ratio
reconcile_group_configs_for_used_colors = _graph_gui.reconcile_group_configs_for_used_colors
resolve_canvas_primary_click_action = _graph_gui.resolve_canvas_primary_click_action
resolve_canvas_secondary_release_action = _graph_gui.resolve_canvas_secondary_release_action
resolve_palette_brush_color = _graph_gui.resolve_palette_brush_color
sync_group_config_state = _graph_gui.sync_group_config_state


def build_test_square_graph() -> RouteGraph:
    return RouteGraph(
        env_id="env",
        graph_name="test_square_graph",
        default_altitude=None,
        nodes=[
            GraphNode(id="N001", name="N001", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="N002", name="N002", position=[0.0, 100.0, 0.0], yaw_hint=90.0),
            GraphNode(id="N003", name="N003", position=[100.0, 100.0, 0.0], yaw_hint=0.0),
            GraphNode(id="N004", name="N004", position=[100.0, 0.0, 0.0], yaw_hint=-90.0),
        ],
        edges=[
            GraphEdge(id="E001", from_node="N001", to_node="N004", weight=100.0, bidirectional=True),
            GraphEdge(id="E002", from_node="N001", to_node="N003", weight=141.421356, bidirectional=True),
        ],
    )


def build_group_bridge_graph() -> RouteGraph:
    return RouteGraph(
        env_id="env",
        graph_name="group_bridge_graph",
        default_altitude=None,
        nodes=[
            GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="B", name="B", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
            GraphNode(id="C", name="C", position=[200.0, 0.0, 100.0], yaw_hint=0.0),
            GraphNode(id="D", name="D", position=[300.0, 0.0, 100.0], yaw_hint=0.0),
        ],
        edges=[
            GraphEdge(
                id="E_RED",
                from_node="A",
                to_node="B",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#FF0000"},
            ),
            GraphEdge(
                id="E_BRIDGE",
                from_node="B",
                to_node="C",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_BRIDGE},
            ),
            GraphEdge(
                id="E_BLUE",
                from_node="C",
                to_node="D",
                weight=100.0,
                bidirectional=True,
                meta={EDGE_KIND_META_KEY: EDGE_KIND_GROUP, EDGE_GROUP_COLOR_META_KEY: "#00AAFF"},
            ),
        ],
    )


class GraphGuiColorGroupLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.default_payload = {
            "node_sample_radius": "0.0",
            "altitude_mode": "fixed",
            "fixed_z": "",
            "altitude_offset": "0.0",
            "takeoff_landing_relative_z": "",
            "takeoff_landing_step_distance": "",
        }

    def test_reconcile_group_configs_keeps_only_used_colors(self) -> None:
        graph = build_group_bridge_graph()

        reconciled = reconcile_group_configs_for_used_colors(
            {
                "#334155": {"altitude_mode": "fixed"},
                "#FF0000": {"altitude_mode": "follow_nodes"},
            },
            derive_used_group_colors(graph),
            default_payload=self.default_payload,
        )

        self.assertEqual(set(reconciled), {"#00AAFF", "#FF0000"})
        self.assertNotIn("#334155", reconciled)
        self.assertEqual(reconciled["#FF0000"]["altitude_mode"], "follow_nodes")
        self.assertEqual(reconciled["#00AAFF"], self.default_payload)

    def test_bridge_only_graph_has_no_used_group_colors(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="bridge_only_graph",
            default_altitude=None,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0], yaw_hint=0.0),
                GraphNode(id="B", name="B", position=[100.0, 0.0, 0.0], yaw_hint=0.0),
            ],
            edges=[
                GraphEdge(
                    id="E001",
                    from_node="A",
                    to_node="B",
                    weight=100.0,
                    bidirectional=True,
                    meta={EDGE_KIND_META_KEY: EDGE_KIND_BRIDGE},
                )
            ],
        )

        self.assertEqual(derive_used_group_colors(graph), [])
        self.assertEqual(
            reconcile_group_configs_for_used_colors(
                {"#334155": self.default_payload},
                derive_used_group_colors(graph),
                default_payload=self.default_payload,
            ),
            {},
        )

    def test_build_group_control_state_shows_staged_color_outside_combo(self) -> None:
        control_state = build_group_control_state(
            ["#0C7C0C", "#101578"],
            active_group_color="#0C7C0C",
            staged_group_color="#334155",
        )

        self.assertIsNone(control_state.selected_color)
        self.assertEqual(control_state.editor_color, "#334155")
        self.assertEqual(control_state.combo_value, "")
        self.assertEqual(
            control_state.staged_label,
            f"{PENDING_GROUP_STATUS_PREFIX}#334155",
        )

    def test_build_group_control_state_promotes_staged_color_once_used(self) -> None:
        control_state = build_group_control_state(
            ["#334155", "#0C7C0C"],
            active_group_color=None,
            staged_group_color="#334155",
        )

        self.assertEqual(control_state.selected_color, "#334155")
        self.assertEqual(control_state.editor_color, "#334155")
        self.assertEqual(control_state.combo_value, "#334155")
        self.assertEqual(control_state.staged_label, "")

    def test_sync_group_config_state_keeps_unused_staged_color_in_memory_only(self) -> None:
        result = sync_group_config_state(
            {"#0C7C0C": dict(self.default_payload)},
            ["#0C7C0C"],
            default_payload=self.default_payload,
            active_group_color=None,
            staged_group_color="#334155",
            staged_group_config=None,
            current_payload={
                **self.default_payload,
                "altitude_mode": "follow_nodes",
            },
        )

        self.assertEqual(set(result.configs), {"#0C7C0C"})
        self.assertEqual(result.staged_color, "#334155")
        self.assertEqual(result.staged_config["altitude_mode"], "follow_nodes")
        self.assertNotIn("#334155", result.configs)

    def test_sync_group_config_state_formalizes_staged_color_when_used(self) -> None:
        payload = {
            **self.default_payload,
            "altitude_mode": "follow_nodes",
            "fixed_z": "120",
        }

        result = sync_group_config_state(
            {},
            ["#334155"],
            default_payload=self.default_payload,
            active_group_color=None,
            staged_group_color="#334155",
            staged_group_config=self.default_payload,
            current_payload=payload,
        )

        self.assertIsNone(result.staged_color)
        self.assertIsNone(result.staged_config)
        self.assertEqual(result.configs["#334155"], payload)

    def test_sync_group_config_state_prunes_removed_active_group_without_restaging(self) -> None:
        result = sync_group_config_state(
            {
                "#FF0000": dict(self.default_payload),
                "#00AAFF": {"altitude_mode": "follow_nodes"},
            },
            ["#00AAFF"],
            default_payload=self.default_payload,
            active_group_color="#FF0000",
            staged_group_color=None,
            staged_group_config=None,
            current_payload={
                **self.default_payload,
                "fixed_z": "80",
            },
        )

        self.assertEqual(set(result.configs), {"#00AAFF"})
        self.assertIsNone(result.staged_color)
        self.assertIsNone(result.staged_config)

    def test_legacy_group_edges_still_use_default_group_color(self) -> None:
        graph = build_test_square_graph()

        self.assertEqual(derive_used_group_colors(graph), [DEFAULT_GROUP_COLOR])

    def test_derive_palette_colors_merges_used_and_session_colors(self) -> None:
        used_colors, session_colors = derive_palette_colors(
            ["#101578", "#0c7c0c"],
            ["#334155", "#101578", "#f97316"],
        )

        self.assertEqual(used_colors, ["#0C7C0C", "#101578"])
        self.assertEqual(session_colors, ["#334155", "#F97316"])

    def test_resolve_palette_brush_color_prefers_current_then_preferred_then_first(self) -> None:
        self.assertEqual(
            resolve_palette_brush_color(
                ["#101578"],
                ["#334155"],
                "#334155",
                preferred_color="#101578",
            ),
            "#334155",
        )
        self.assertEqual(
            resolve_palette_brush_color(
                ["#101578"],
                ["#334155"],
                "#F97316",
                preferred_color="#101578",
            ),
            "#101578",
        )
        self.assertEqual(
            resolve_palette_brush_color(
                ["#101578"],
                ["#334155"],
                None,
                preferred_color=None,
            ),
            "#101578",
        )

    def test_format_paint_mode_status_reflects_current_brush(self) -> None:
        self.assertEqual(format_paint_mode_status(False, None), "染色模式：关闭")
        self.assertEqual(
            format_paint_mode_status(True, "#334155"),
            "染色模式：开启（当前画笔 #334155）",
        )

    def test_format_insert_mode_status_reflects_toggle_state(self) -> None:
        self.assertEqual(format_insert_mode_status(False), "插点模式：关闭")
        self.assertEqual(
            format_insert_mode_status(True),
            "插点模式：开启（右键点击组内边插点）",
        )

    def test_project_point_to_segment_ratio_tracks_projected_position(self) -> None:
        self.assertAlmostEqual(
            project_point_to_segment_ratio(
                (25.0, 10.0),
                (0.0, 0.0),
                (100.0, 0.0),
            ),
            0.25,
        )
        self.assertAlmostEqual(
            project_point_to_segment_ratio(
                (-10.0, 10.0),
                (0.0, 0.0),
                (100.0, 0.0),
            ),
            0.0,
        )

    def test_resolve_canvas_primary_click_action_prefers_paint_branch(self) -> None:
        self.assertEqual(
            resolve_canvas_primary_click_action(
                paint_mode_enabled=True,
                nearest_node_id="N001",
                nearest_edge_id="E001",
                additive=False,
            ),
            "paint_edge",
        )
        self.assertEqual(
            resolve_canvas_primary_click_action(
                paint_mode_enabled=False,
                nearest_node_id=None,
                nearest_edge_id="E001",
                additive=False,
            ),
            "select_edge",
        )
        self.assertEqual(
            resolve_canvas_primary_click_action(
                paint_mode_enabled=False,
                nearest_node_id="N001",
                nearest_edge_id="E001",
                additive=True,
            ),
            "toggle_node",
        )

    def test_resolve_canvas_secondary_release_action_distinguishes_insert_and_pan(self) -> None:
        self.assertEqual(
            resolve_canvas_secondary_release_action(
                insert_mode_enabled=True,
                nearest_edge_id="E001",
                movement_distance_px=2.0,
                drag_threshold_px=6.0,
            ),
            "insert_edge",
        )
        self.assertEqual(
            resolve_canvas_secondary_release_action(
                insert_mode_enabled=True,
                nearest_edge_id="E001",
                movement_distance_px=8.0,
                drag_threshold_px=6.0,
            ),
            "pan",
        )
        self.assertEqual(
            resolve_canvas_secondary_release_action(
                insert_mode_enabled=False,
                nearest_edge_id="E001",
                movement_distance_px=2.0,
                drag_threshold_px=6.0,
            ),
            "noop",
        )

    def test_painting_bridge_edge_promotes_it_to_group(self) -> None:
        graph = build_group_bridge_graph()
        editor = GraphEditor(graph)

        editor.set_edge_group_color("E_BRIDGE", "#334155")

        bridge_edge = graph.get_edge("E_BRIDGE")
        self.assertEqual(bridge_edge.meta[EDGE_KIND_META_KEY], EDGE_KIND_GROUP)
        self.assertEqual(bridge_edge.meta[EDGE_GROUP_COLOR_META_KEY], "#334155")
        self.assertIn("#334155", derive_used_group_colors(graph))


if __name__ == "__main__":
    unittest.main()
