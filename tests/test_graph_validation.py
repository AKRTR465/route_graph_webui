from __future__ import annotations

from tests.route_graph_test_helpers import *

class GraphEditorInsertNodeTests(unittest.TestCase):
    def test_insert_node_on_group_edge_splits_edge_and_preserves_metadata(self) -> None:
        graph = build_group_bridge_graph()
        graph.get_edge("E_RED").enabled = False
        graph.get_node("A").yaw_hint = 170.0
        graph.get_node("B").yaw_hint = -170.0
        editor = GraphEditor(graph)

        inserted = editor.insert_node_on_edge("E_RED", 0.75)

        self.assertEqual(inserted.id, "N001")
        self.assertEqual(inserted.name, "N001")
        self.assertEqual(inserted.position, [75.0, 0.0, 0.0])
        self.assertAlmostEqual(inserted.yaw_hint, -175.0)
        self.assertEqual(inserted.meta[INSERTED_NODE_SOURCE_EDGE_ID_META_KEY], "E_RED")
        self.assertAlmostEqual(inserted.meta[INSERTED_NODE_SOURCE_EDGE_RATIO_META_KEY], 0.75)
        self.assertNotIn("E_RED", graph.edge_map)

        left_edge = next(edge for edge in graph.edges if edge.from_node == "A" and edge.to_node == "N001")
        right_edge = next(edge for edge in graph.edges if edge.from_node == "N001" and edge.to_node == "B")
        self.assertFalse(left_edge.enabled)
        self.assertFalse(right_edge.enabled)
        self.assertTrue(left_edge.bidirectional)
        self.assertTrue(right_edge.bidirectional)
        self.assertEqual(left_edge.meta[EDGE_KIND_META_KEY], EDGE_KIND_GROUP)
        self.assertEqual(right_edge.meta[EDGE_KIND_META_KEY], EDGE_KIND_GROUP)
        self.assertEqual(left_edge.meta[EDGE_GROUP_COLOR_META_KEY], "#FF0000")
        self.assertEqual(right_edge.meta[EDGE_GROUP_COLOR_META_KEY], "#FF0000")
        self.assertAlmostEqual(left_edge.weight, 75.0)
        self.assertAlmostEqual(right_edge.weight, 25.0)
        self.assertAlmostEqual(left_edge.weight + right_edge.weight, 100.0)

        report = validate_graph(graph)
        self.assertTrue(report.is_valid, report.format_text())
        ensure_valid_grouped_graph_for_routes(graph)

    def test_insert_node_on_edge_inherits_single_available_yaw_hint(self) -> None:
        graph = build_test_square_graph()
        graph.get_node("N001").yaw_hint = None
        graph.get_node("N004").yaw_hint = 42.0
        editor = GraphEditor(graph)

        inserted = editor.insert_node_on_edge("E001", 0.25)

        self.assertEqual(inserted.yaw_hint, 42.0)

    def test_insert_node_on_bridge_edge_is_rejected(self) -> None:
        graph = build_group_bridge_graph()
        editor = GraphEditor(graph)

        with self.assertRaises(GraphSchemaError) as context:
            editor.insert_node_on_edge("E_BRIDGE", 0.5)

        self.assertIn("Bridge edges do not support node insertion yet", str(context.exception))

    def test_insert_node_on_edge_rejects_ratios_near_endpoints(self) -> None:
        graph = build_test_square_graph()
        editor = GraphEditor(graph)

        with self.assertRaises(GraphSchemaError):
            editor.insert_node_on_edge("E001", 1e-6)
        with self.assertRaises(GraphSchemaError):
            editor.insert_node_on_edge("E001", 1.0 - 1e-6)

        self.assertEqual(len(graph.nodes), 4)
        self.assertEqual(len(graph.edges), 5)


