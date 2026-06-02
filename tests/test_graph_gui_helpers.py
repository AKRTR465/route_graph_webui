from __future__ import annotations

from tests.route_graph_test_helpers import *

class GraphGuiExportOptionTests(unittest.TestCase):
    def test_format_auto_allowed_route_groups_status_reports_selected_count(self) -> None:
        self.assertEqual(
            format_auto_allowed_route_groups_status(selected_count=2, available_count=8),
            "已选 2 个组；留空表示不限制。",
        )
        self.assertEqual(
            format_auto_allowed_route_groups_status(selected_count=3, available_count=0),
            "已选 0 个组；当前图没有可用于自动规划的颜色组。",
        )

    def test_format_auto_excluded_endpoint_groups_status_reports_selected_count(self) -> None:
        self.assertEqual(
            format_auto_excluded_endpoint_groups_status(selected_count=3, available_count=8),
            "已选 3 个组；已选中的颜色组不会作为自动规划的起点或终点。",
        )
        self.assertEqual(
            format_auto_excluded_endpoint_groups_status(selected_count=2, available_count=0),
            "已选 0 个组；当前图没有可排除的颜色组。",
        )

    def test_auto_group_selection_helpers_normalize_and_limit_endpoint_choices(self) -> None:
        self.assertEqual(
            normalize_auto_group_selection(
                ["#FF0000", "#00FF00", "#0000FF"],
                ["#ff0000", "#ABCDEF", "#0000ff", "#FF0000"],
            ),
            ["#FF0000", "#0000FF"],
        )
        self.assertEqual(
            resolve_auto_endpoint_group_choices(
                ["#FF0000", "#00FF00", "#0000FF"],
                ["#00ff00", "#0000ff"],
            ),
            ["#00FF00", "#0000FF"],
        )
        self.assertEqual(
            normalize_auto_group_selection(
                resolve_auto_endpoint_group_choices(
                    ["#FF0000", "#00FF00", "#0000FF"],
                    ["#0000FF"],
                ),
                ["#00FF00", "#0000ff"],
            ),
            ["#0000FF"],
        )

    def test_resolve_export_options_parses_valid_fixed_mode_values(self) -> None:
        options = resolve_export_options(
            step_distance_text="60",
            fps_text="4",
            altitude_mode="fixed",
            fixed_z_text="350",
            altitude_offset_text="10",
            takeoff_landing_relative_z_text="30",
            takeoff_landing_step_distance_text="15",
            node_sample_radius_text="25",
            random_seed_text="7",
            turn_smoothing_enabled=True,
            corner_radius_text="900",
            small_turn_yaw_blend_threshold_deg_text="25",
            corner_min_angle_deg_text="20",
            u_turn_threshold_deg_text="150",
            u_turn_transition_distance_text="240",
            corner_max_yaw_step_deg_text="2",
            u_turn_pivot_yaw_step_deg_text="2.5",
        )

        self.assertEqual(options["step_distance"], 60.0)
        self.assertEqual(options["fps"], 4.0)
        self.assertEqual(options["altitude_mode"], "fixed")
        self.assertEqual(options["fixed_z"], 350.0)
        self.assertEqual(options["altitude_offset"], 10.0)
        self.assertEqual(options["takeoff_landing_relative_z"], 30.0)
        self.assertEqual(options["takeoff_landing_step_distance"], 15.0)
        self.assertEqual(options["node_sample_radius"], 25.0)
        self.assertEqual(options["random_seed"], 7)
        self.assertTrue(options["turn_smoothing_enabled"])
        self.assertEqual(options["corner_radius"], 900.0)

    def test_resolve_export_options_rejects_invalid_numeric_values(self) -> None:
        with self.assertRaises(GraphSchemaError):
            resolve_export_options(
                step_distance_text="0",
                fps_text="4",
                altitude_mode="fixed",
                fixed_z_text="350",
                altitude_offset_text="0",
                takeoff_landing_relative_z_text="",
                takeoff_landing_step_distance_text="",
                node_sample_radius_text="0",
                random_seed_text="",
                turn_smoothing_enabled=True,
                corner_radius_text="900",
                small_turn_yaw_blend_threshold_deg_text="25",
                corner_min_angle_deg_text="20",
                u_turn_threshold_deg_text="150",
                u_turn_transition_distance_text="240",
                corner_max_yaw_step_deg_text="2",
                u_turn_pivot_yaw_step_deg_text="2.5",
            )
        with self.assertRaises(GraphSchemaError):
            resolve_export_options(
                step_distance_text="60",
                fps_text="-1",
                altitude_mode="fixed",
                fixed_z_text="350",
                altitude_offset_text="0",
                takeoff_landing_relative_z_text="",
                takeoff_landing_step_distance_text="",
                node_sample_radius_text="0",
                random_seed_text="",
                turn_smoothing_enabled=True,
                corner_radius_text="900",
                small_turn_yaw_blend_threshold_deg_text="25",
                corner_min_angle_deg_text="20",
                u_turn_threshold_deg_text="150",
                u_turn_transition_distance_text="240",
                corner_max_yaw_step_deg_text="2",
                u_turn_pivot_yaw_step_deg_text="2.5",
            )
        with self.assertRaises(GraphSchemaError):
            resolve_export_options(
                step_distance_text="60",
                fps_text="4",
                altitude_mode="fixed",
                fixed_z_text="350",
                altitude_offset_text="0",
                takeoff_landing_relative_z_text="",
                takeoff_landing_step_distance_text="",
                node_sample_radius_text="-1",
                random_seed_text="",
                turn_smoothing_enabled=True,
                corner_radius_text="900",
                small_turn_yaw_blend_threshold_deg_text="25",
                corner_min_angle_deg_text="20",
                u_turn_threshold_deg_text="150",
                u_turn_transition_distance_text="240",
                corner_max_yaw_step_deg_text="2",
                u_turn_pivot_yaw_step_deg_text="2.5",
            )
        with self.assertRaises(GraphSchemaError):
            resolve_export_options(
                step_distance_text="60",
                fps_text="4",
                altitude_mode="fixed",
                fixed_z_text="350",
                altitude_offset_text="0",
                takeoff_landing_relative_z_text="-1",
                takeoff_landing_step_distance_text="",
                node_sample_radius_text="0",
                random_seed_text="",
                turn_smoothing_enabled=True,
                corner_radius_text="900",
                small_turn_yaw_blend_threshold_deg_text="25",
                corner_min_angle_deg_text="20",
                u_turn_threshold_deg_text="150",
                u_turn_transition_distance_text="240",
                corner_max_yaw_step_deg_text="2",
                u_turn_pivot_yaw_step_deg_text="2.5",
            )
        with self.assertRaises(GraphSchemaError):
            resolve_export_options(
                step_distance_text="60",
                fps_text="4",
                altitude_mode="fixed",
                fixed_z_text="350",
                altitude_offset_text="0",
                takeoff_landing_relative_z_text="bad",
                takeoff_landing_step_distance_text="",
                node_sample_radius_text="0",
                random_seed_text="",
                turn_smoothing_enabled=True,
                corner_radius_text="900",
                small_turn_yaw_blend_threshold_deg_text="25",
                corner_min_angle_deg_text="20",
                u_turn_threshold_deg_text="150",
                u_turn_transition_distance_text="240",
                corner_max_yaw_step_deg_text="2",
                u_turn_pivot_yaw_step_deg_text="2.5",
            )
        with self.assertRaises(GraphSchemaError):
            resolve_export_options(
                step_distance_text="60",
                fps_text="4",
                altitude_mode="fixed",
                fixed_z_text="350",
                altitude_offset_text="0",
                takeoff_landing_relative_z_text="",
                takeoff_landing_step_distance_text="-1",
                node_sample_radius_text="0",
                random_seed_text="",
                turn_smoothing_enabled=True,
                corner_radius_text="900",
                small_turn_yaw_blend_threshold_deg_text="25",
                corner_min_angle_deg_text="20",
                u_turn_threshold_deg_text="150",
                u_turn_transition_distance_text="240",
                corner_max_yaw_step_deg_text="2",
                u_turn_pivot_yaw_step_deg_text="2.5",
            )
        with self.assertRaises(GraphSchemaError):
            resolve_export_options(
                step_distance_text="60",
                fps_text="4",
                altitude_mode="fixed",
                fixed_z_text="350",
                altitude_offset_text="0",
                takeoff_landing_relative_z_text="",
                takeoff_landing_step_distance_text="bad",
                node_sample_radius_text="0",
                random_seed_text="",
                turn_smoothing_enabled=True,
                corner_radius_text="900",
                small_turn_yaw_blend_threshold_deg_text="25",
                corner_min_angle_deg_text="20",
                u_turn_threshold_deg_text="150",
                u_turn_transition_distance_text="240",
                corner_max_yaw_step_deg_text="2",
                u_turn_pivot_yaw_step_deg_text="2.5",
            )

    def test_follow_nodes_mode_ignores_fixed_z_text(self) -> None:
        options = resolve_export_options(
            step_distance_text="60",
            fps_text="4",
            altitude_mode="follow_nodes",
            fixed_z_text="not-a-number",
            altitude_offset_text="5",
            takeoff_landing_relative_z_text="",
            takeoff_landing_step_distance_text="",
            node_sample_radius_text="0",
            random_seed_text="",
            turn_smoothing_enabled=False,
            corner_radius_text="bad",
            small_turn_yaw_blend_threshold_deg_text="bad",
            corner_min_angle_deg_text="bad",
            u_turn_threshold_deg_text="bad",
            u_turn_transition_distance_text="bad",
            corner_max_yaw_step_deg_text="bad",
            u_turn_pivot_yaw_step_deg_text="bad",
        )

        self.assertEqual(options["altitude_mode"], "follow_nodes")
        self.assertIsNone(options["fixed_z"])
        self.assertEqual(options["altitude_offset"], 5.0)
        self.assertIsNone(options["takeoff_landing_step_distance"])

    def test_is_fixed_z_enabled_tracks_altitude_mode(self) -> None:
        self.assertTrue(is_fixed_z_enabled("fixed"))
        self.assertFalse(is_fixed_z_enabled("follow_nodes"))

    def test_resolve_node_sample_radius_override_text_accepts_empty_zero_and_positive(self) -> None:
        self.assertIsNone(resolve_node_sample_radius_override_text(""))
        self.assertEqual(resolve_node_sample_radius_override_text("0"), 0.0)
        self.assertEqual(resolve_node_sample_radius_override_text("12.5"), 12.5)

    def test_resolve_node_sample_radius_override_text_rejects_invalid_values(self) -> None:
        with self.assertRaises(GraphSchemaError):
            resolve_node_sample_radius_override_text("-1")
        with self.assertRaises(GraphSchemaError):
            resolve_node_sample_radius_override_text("bad")

    def test_resolve_max_total_length_text_accepts_empty_and_positive(self) -> None:
        self.assertIsNone(resolve_max_total_length_text(""))
        self.assertEqual(resolve_max_total_length_text("123.5"), 123.5)

    def test_resolve_max_total_length_text_rejects_zero_negative_and_invalid(self) -> None:
        with self.assertRaises(GraphSchemaError):
            resolve_max_total_length_text("0")
        with self.assertRaises(GraphSchemaError):
            resolve_max_total_length_text("-1")
        with self.assertRaises(GraphSchemaError):
            resolve_max_total_length_text("bad")

    def test_resolve_min_total_length_text_accepts_empty_and_positive(self) -> None:
        self.assertIsNone(resolve_min_total_length_text(""))
        self.assertEqual(resolve_min_total_length_text("123.5"), 123.5)

    def test_resolve_min_total_length_text_rejects_zero_negative_and_invalid(self) -> None:
        with self.assertRaises(GraphSchemaError):
            resolve_min_total_length_text("0")
        with self.assertRaises(GraphSchemaError):
            resolve_min_total_length_text("-1")
        with self.assertRaises(GraphSchemaError):
            resolve_min_total_length_text("bad")

    def test_resolve_min_frame_count_text_accepts_empty_and_positive(self) -> None:
        self.assertIsNone(resolve_min_frame_count_text(""))
        self.assertEqual(resolve_min_frame_count_text("123"), 123)

    def test_resolve_min_frame_count_text_rejects_zero_negative_and_invalid(self) -> None:
        with self.assertRaises(GraphSchemaError):
            resolve_min_frame_count_text("0")
        with self.assertRaises(GraphSchemaError):
            resolve_min_frame_count_text("-1")
        with self.assertRaises(GraphSchemaError):
            resolve_min_frame_count_text("bad")

    def test_resolve_max_frame_count_text_accepts_empty_and_positive(self) -> None:
        self.assertIsNone(resolve_max_frame_count_text(""))
        self.assertEqual(resolve_max_frame_count_text("123"), 123)

    def test_resolve_max_frame_count_text_rejects_zero_negative_and_invalid(self) -> None:
        with self.assertRaises(GraphSchemaError):
            resolve_max_frame_count_text("0")
        with self.assertRaises(GraphSchemaError):
            resolve_max_frame_count_text("-1")
        with self.assertRaises(GraphSchemaError):
            resolve_max_frame_count_text("bad")



class GraphGuiExportInputPersistenceTests(unittest.TestCase):
    def test_read_graph_gui_export_inputs_returns_empty_when_meta_key_missing(self) -> None:
        self.assertEqual(read_graph_gui_export_inputs({}), {})

    def test_read_graph_gui_auto_plan_inputs_returns_empty_when_meta_key_missing(self) -> None:
        self.assertEqual(read_graph_gui_auto_plan_inputs({}), {})

    def test_read_graph_gui_webui_inputs_returns_empty_when_meta_key_missing(self) -> None:
        self.assertEqual(read_graph_gui_webui_inputs({}), {})

    def test_write_and_read_graph_gui_export_inputs_roundtrip(self) -> None:
        meta: dict[str, object] = {}
        payload = {
            "step_distance": "bad-value",
            "node_sample_radius": "12.5",
            "fps": "2.0",
            "altitude_mode": "fixed",
            "fixed_z": "",
            "altitude_offset": "3.5",
            "takeoff_landing_relative_z": "10",
            "takeoff_landing_step_distance": "15",
            "random_seed": "123",
            "turn_smoothing_enabled": False,
            "corner_radius": "900",
            "corner_min_angle_deg": "20",
            "u_turn_threshold_deg": "150",
            "u_turn_transition_distance": "240",
            "corner_max_yaw_step_deg": "2",
            "u_turn_pivot_yaw_step_deg": "2.5",
        }

        write_graph_gui_export_inputs(meta, payload)
        loaded = read_graph_gui_export_inputs(meta)

        self.assertIn(GRAPH_GUI_EXPORT_INPUTS_META_KEY, meta)
        self.assertEqual(loaded, payload)

    def test_write_and_read_graph_gui_auto_plan_inputs_roundtrip(self) -> None:
        meta: dict[str, object] = {}
        payload = {
            "planning_mode": "auto",
            "auto_max_output_routes": "8",
            "auto_enable_global_coverage": True,
            "auto_allowed_route_group_colors": ["#00ff00", "#ff0000", "#00FF00"],
            "auto_excluded_endpoint_group_colors": ["#ff0000", "#00aaff", "#FF0000"],
        }

        write_graph_gui_auto_plan_inputs(meta, payload)
        loaded = read_graph_gui_auto_plan_inputs(meta)

        self.assertIn(GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY, meta)
        self.assertEqual(
            loaded,
            {
                "planning_mode": "auto",
                "auto_max_output_routes": "8",
                "auto_enable_global_coverage": True,
                "auto_allowed_route_group_colors": ["#00FF00", "#FF0000"],
                "auto_excluded_endpoint_group_colors": ["#FF0000", "#00AAFF"],
            },
        )

    def test_read_graph_gui_export_inputs_ignores_dirty_payload(self) -> None:
        meta = {
            GRAPH_GUI_EXPORT_INPUTS_META_KEY: {
                "step_distance": {"bad": "shape"},
                "fps": "2.0",
                "turn_smoothing_enabled": "false",
                "altitude_mode": "invalid-mode",
            }
        }

        loaded = read_graph_gui_export_inputs(meta)

        self.assertEqual(loaded, {"fps": "2.0"})

    def test_read_graph_gui_auto_plan_inputs_ignores_invalid_color_entries(self) -> None:
        meta = {
            GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY: {
                "planning_mode": "auto",
                "auto_allowed_route_group_colors": ["#00ff00", "bad-color", "#00FF00", None, ""],
                "auto_excluded_endpoint_group_colors": ["#ff0000", "bad-color", "#FF0000", None, ""],
            }
        }

        loaded = read_graph_gui_auto_plan_inputs(meta)

        self.assertEqual(
            loaded,
            {
                "planning_mode": "auto",
                "auto_allowed_route_group_colors": ["#00FF00"],
                "auto_excluded_endpoint_group_colors": ["#FF0000"],
            },
        )

    def test_write_and_read_graph_gui_webui_inputs_roundtrip(self) -> None:
        meta: dict[str, object] = {}
        payload = {
            "planning_mode": "auto",
            "max_routes": 12,
            "max_edge_pass_factor": 3.5,
            "min_total_length": "",
            "max_total_length": "4500",
            "candidate_set_file_name": "demo.candidates.json",
            "missions_output_dir": "missions/demo",
            "ignored_field": "skip",
        }

        write_graph_gui_webui_inputs(meta, payload)
        loaded = read_graph_gui_webui_inputs(meta)

        self.assertIn(GRAPH_GUI_WEBUI_INPUTS_META_KEY, meta)
        self.assertEqual(
            loaded,
            {
                "planning_mode": "auto",
                "max_routes": "12",
                "max_edge_pass_factor": "3.5",
                "min_total_length": "",
                "max_total_length": "4500",
                "candidate_set_file_name": "demo.candidates.json",
                "missions_output_dir": "missions/demo",
            },
        )



class GraphGuiCanvasViewPersistenceTests(unittest.TestCase):
    def test_read_graph_gui_canvas_view_returns_defaults_when_meta_key_missing(self) -> None:
        self.assertEqual(resolve_graph_gui_canvas_view({}), {"rotation_quadrants": 0, "flip_horizontal": False, "flip_vertical": False})
        self.assertEqual(read_graph_gui_canvas_view({}), {})

    def test_write_and_read_graph_gui_canvas_view_roundtrip(self) -> None:
        meta: dict[str, object] = {}
        payload = {
            "rotation_quadrants": 3,
            "flip_horizontal": True,
            "flip_vertical": False,
        }

        write_graph_gui_canvas_view(meta, payload)
        loaded = read_graph_gui_canvas_view(meta)

        self.assertIn(GRAPH_GUI_CANVAS_VIEW_META_KEY, meta)
        self.assertEqual(loaded, payload)
        self.assertEqual(resolve_graph_gui_canvas_view(meta), payload)

    def test_read_graph_gui_canvas_view_ignores_dirty_payload(self) -> None:
        meta = {
            GRAPH_GUI_CANVAS_VIEW_META_KEY: {
                "rotation_quadrants": "1",
                "flip_horizontal": "true",
                "flip_vertical": 1,
            }
        }

        loaded = read_graph_gui_canvas_view(meta)

        self.assertEqual(loaded, {"flip_vertical": True})
        self.assertEqual(
            resolve_graph_gui_canvas_view(meta),
            {"rotation_quadrants": 0, "flip_horizontal": False, "flip_vertical": True},
        )

    def test_sync_graph_gui_canvas_view_removes_meta_key_when_reset_to_default(self) -> None:
        meta = {
            GRAPH_GUI_CANVAS_VIEW_META_KEY: {
                "rotation_quadrants": 2,
                "flip_horizontal": True,
                "flip_vertical": False,
            }
        }

        changed = sync_graph_gui_canvas_view(meta, GRAPH_GUI_CANVAS_VIEW_DEFAULTS)

        self.assertTrue(changed)
        self.assertNotIn(GRAPH_GUI_CANVAS_VIEW_META_KEY, meta)



class GraphGuiPreviewStateTests(unittest.TestCase):
    def test_candidate_selection_marks_preview_stale_without_auto_preview(self) -> None:
        state = PreviewStateModel()

        state.select_candidate()

        self.assertTrue(state.has_plan)
        self.assertIsNone(state.mission)
        self.assertTrue(state.is_stale)
        self.assertEqual(state.status_text(), PREVIEW_STATUS_STALE)

    def test_parameter_change_keeps_existing_preview_and_marks_it_stale(self) -> None:
        state = PreviewStateModel()
        state.select_candidate()
        state.set_preview({"positions": [{}, {}]})

        changed = state.invalidate()

        self.assertTrue(changed)
        self.assertIsNotNone(state.mission)
        self.assertTrue(state.is_stale)
        self.assertIn(PREVIEW_STATUS_STALE, state.status_text())
        self.assertIn("cached preview", state.status_text())

    def test_generation_completion_with_default_candidate_keeps_preview_empty(self) -> None:
        state = PreviewStateModel()

        state.select_candidate()

        self.assertIsNone(state.mission)
        self.assertTrue(state.is_stale)
        self.assertEqual(state.status_text(), PREVIEW_STATUS_STALE)

    def test_mark_stale_keeps_existing_preview_visible(self) -> None:
        state = PreviewStateModel()
        state.select_candidate()
        state.set_preview({"positions": [{}, {}, {}]})

        state.mark_stale()

        self.assertEqual(len(state.mission["positions"]), 3)
        self.assertTrue(state.is_stale)
        self.assertIn("cached preview", state.status_text())



class GraphGuiIoHelperTests(unittest.TestCase):
    def test_consume_progress_messages_keeps_partial_jsonl_record_for_next_poll(self) -> None:
        messages, remainder = _consume_progress_messages(
            "",
            '{"job_id": 1, "type": "progress"}\n{"job_id": 2',
        )

        self.assertEqual(messages, [{"job_id": 1, "type": "progress"}])
        self.assertEqual(remainder, '{"job_id": 2')

        messages, remainder = _consume_progress_messages(remainder, ', "type": "progress"}\n')

        self.assertEqual(messages, [{"job_id": 2, "type": "progress"}])
        self.assertEqual(remainder, "")

    def test_read_json_mapping_if_ready_ignores_partial_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            path.write_text('{"job_id": 1', encoding="utf-8")
            self.assertIsNone(_read_json_mapping_if_ready(path))

            path.write_text('{"job_id": 1, "type": "success"}\n', encoding="utf-8")
            self.assertEqual(
                _read_json_mapping_if_ready(path),
                {"job_id": 1, "type": "success"},
            )

    def test_load_validated_graph_rejects_invalid_graph_file(self) -> None:
        bad_graph = {
            "env_id": "env",
            "graph_name": "bad_graph",
            "default_altitude": None,
            "nodes": [
                {
                    "id": "A",
                    "name": "A",
                    "position": [0.0, 0.0, 0.0],
                    "yaw_hint": 0.0,
                    "tags": [],
                    "meta": {},
                }
            ],
            "edges": [
                {
                    "id": "E001",
                    "from": "A",
                    "to": "MISSING",
                    "weight": 1.0,
                    "enabled": True,
                    "bidirectional": True,
                    "meta": {},
                }
            ],
            "meta": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = write_json_file(Path(temp_dir) / "bad_graph.json", bad_graph)

            with self.assertRaises(GraphSchemaError) as context:
                _load_validated_graph(graph_path)

            self.assertIn("missing-node-reference", str(context.exception))



class GraphGuiRouteGenerationHelperTests(unittest.TestCase):
    @staticmethod
    def _graph_gui_app_method_lookup() -> dict[str, ast.FunctionDef]:
        source = inspect.getsource(graph_gui_module.launch_gui)
        tree = ast.parse(source)
        launch_gui_def = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "launch_gui"
        )
        graph_gui_app_def = next(
            node for node in launch_gui_def.body if isinstance(node, ast.ClassDef) and node.name == "GraphGuiApp"
        )
        return {
            node.name: node
            for node in graph_gui_app_def.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_graph_gui_app_defines_filters_require_auto_keep_method(self) -> None:
        self.assertIn("_filters_require_auto_keep", self._graph_gui_app_method_lookup())

    def test_graph_gui_app_defines_auto_excluded_endpoint_group_handler(self) -> None:
        self.assertIn("on_auto_excluded_endpoint_groups_changed", self._graph_gui_app_method_lookup())

    def test_graph_gui_app_defines_auto_allowed_route_group_handler(self) -> None:
        self.assertIn("on_auto_allowed_route_groups_changed", self._graph_gui_app_method_lookup())

    def test_graph_gui_app_defines_auto_allowed_route_group_mouse_wheel_handler(self) -> None:
        self.assertIn("_on_auto_allowed_route_groups_mouse_wheel", self._graph_gui_app_method_lookup())

    def test_graph_gui_app_defines_auto_excluded_endpoint_group_mouse_wheel_handler(self) -> None:
        self.assertIn("_on_auto_excluded_endpoint_groups_mouse_wheel", self._graph_gui_app_method_lookup())

    def test_graph_gui_error_handler_has_no_explicit_boolean_return(self) -> None:
        error_handler = self._graph_gui_app_method_lookup()["_handle_route_generation_error"]
        returns = [node for node in ast.walk(error_handler) if isinstance(node, ast.Return)]
        self.assertTrue(all(node.value is None for node in returns))

    def test_graph_gui_auto_generation_payload_includes_excluded_endpoint_groups(self) -> None:
        begin_auto = self._graph_gui_app_method_lookup()["_begin_auto_route_generation"]
        string_constants = {
            node.value
            for node in ast.walk(begin_auto)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("excluded_endpoint_group_colors", string_constants)

    def test_graph_gui_auto_generation_payload_includes_allowed_route_groups(self) -> None:
        begin_auto = self._graph_gui_app_method_lookup()["_begin_auto_route_generation"]
        string_constants = {
            node.value
            for node in ast.walk(begin_auto)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("allowed_route_group_colors", string_constants)

    def test_graph_gui_auto_generation_payload_includes_export_config(self) -> None:
        begin_auto = self._graph_gui_app_method_lookup()["_begin_auto_route_generation"]
        string_constants = {
            node.value
            for node in ast.walk(begin_auto)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("export_config", string_constants)



class GraphGuiCanvasHitTests(unittest.TestCase):
    def test_distance_point_to_segment_is_zero_for_point_on_segment(self) -> None:
        self.assertAlmostEqual(
            distance_point_to_segment((5.0, 0.0), (0.0, 0.0), (10.0, 0.0)),
            0.0,
        )

    def test_distance_point_to_segment_clamps_to_nearest_endpoint(self) -> None:
        self.assertAlmostEqual(
            distance_point_to_segment((15.0, 0.0), (0.0, 0.0), (10.0, 0.0)),
            5.0,
        )
        self.assertAlmostEqual(
            distance_point_to_segment((0.0, 4.0), (0.0, 0.0), (0.0, 0.0)),
            4.0,
        )

    def test_blend_hex_color_lightens_toward_white(self) -> None:
        self.assertEqual(_blend_hex_color("#000000", ratio=0.5), "#808080")
        self.assertEqual(_blend_hex_color("#FF0000", ratio=0.0), "#FF0000")

    def test_resolve_canvas_edge_draw_style_highlights_active_group(self) -> None:
        highlighted = resolve_canvas_edge_draw_style(
            base_color="#101578",
            enabled=True,
            selected=False,
            active_group_selected=True,
            belongs_to_active_group=True,
        )
        dimmed = resolve_canvas_edge_draw_style(
            base_color="#101578",
            enabled=True,
            selected=False,
            active_group_selected=True,
            belongs_to_active_group=False,
        )

        self.assertEqual(highlighted, ("#101578", 4, ()))
        self.assertEqual(dimmed[1], 1)
        self.assertNotEqual(dimmed[0], "#101578")
        self.assertEqual(dimmed[2], ())



class EdgePassLabelLayoutTests(unittest.TestCase):
    def test_layout_avoids_overlap_for_short_collinear_edges(self) -> None:
        node_lookup = {
            "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0]),
            "B": GraphNode(id="B", name="B", position=[0.0, 8.0, 0.0]),
            "C": GraphNode(id="C", name="C", position=[0.0, 16.0, 0.0]),
            "D": GraphNode(id="D", name="D", position=[0.0, 24.0, 0.0]),
            "E": GraphNode(id="E", name="E", position=[0.0, 32.0, 0.0]),
        }
        edge_passes = [
            RouteEdgePass(pass_index=1, edge_id="E001", from_node="A", to_node="B", segment_index=0, local_index=1),
            RouteEdgePass(pass_index=2, edge_id="E002", from_node="B", to_node="C", segment_index=0, local_index=2),
            RouteEdgePass(pass_index=3, edge_id="E003", from_node="C", to_node="D", segment_index=0, local_index=3),
            RouteEdgePass(pass_index=4, edge_id="E004", from_node="D", to_node="E", segment_index=0, local_index=4),
        ]

        layouts = compute_edge_pass_label_layout(
            node_lookup,
            edge_passes,
            lambda position: (float(position[0]), float(position[1])),
        )

        self.assertEqual([layout.pass_index for layout in layouts], [1, 2, 3, 4])

        def overlaps(ax: float, ay: float, bx: float, by: float) -> bool:
            label_width = 17.0
            label_height = 14.0
            padding = 4.0
            return (
                abs(ax - bx) < label_width + padding
                and abs(ay - by) < label_height + padding
            )

        for index, left in enumerate(layouts):
            for right in layouts[index + 1 :]:
                self.assertFalse(
                    overlaps(left.x, left.y, right.x, right.y),
                    f"labels {left.pass_index} and {right.pass_index} overlap: {left} vs {right}",
                )



class GraphPreviewRenderingTests(unittest.TestCase):
    def test_render_graph_preview_skips_edges_with_missing_nodes(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="render_invalid_edge",
            default_altitude=None,
            nodes=[GraphNode(id="A", name="A", position=[0.0, 0.0, 0.0])],
            edges=[GraphEdge(id="E001", from_node="A", to_node="MISSING", weight=1.0)],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "preview.png"
            render_graph_preview(graph, output_path)

            self.assertTrue(output_path.exists())

    def test_render_graph_preview_supports_canvas_view_state(self) -> None:
        graph = build_test_square_graph()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "preview_rotated.png"
            render_graph_preview(
                graph,
                output_path,
                view_state=CanvasViewState(
                    rotation_quadrants=1,
                    flip_horizontal=True,
                    flip_vertical=True,
                ),
            )

            self.assertTrue(output_path.exists())



class GraphCanvasViewTransformTests(unittest.TestCase):
    def test_canvas_view_transform_roundtrip_recovers_original_coordinates(self) -> None:
        positions = [
            (-20.0, 15.0, 0.0),
            (10.0, 35.0, 0.0),
            (55.0, -25.0, 0.0),
        ]
        center_xy = compute_canvas_view_center(positions)

        for rotation_quadrants in range(4):
            for flip_horizontal in (False, True):
                for flip_vertical in (False, True):
                    state = CanvasViewState(
                        rotation_quadrants=rotation_quadrants,
                        flip_horizontal=flip_horizontal,
                        flip_vertical=flip_vertical,
                    )
                    for position in positions:
                        transformed = transform_canvas_view_position(
                            position,
                            center_xy=center_xy,
                            view_state=state,
                        )
                        recovered = inverse_canvas_view_position(
                            transformed,
                            center_xy=center_xy,
                            view_state=state,
                        )
                        self.assertAlmostEqual(recovered[0], position[0])
                        self.assertAlmostEqual(recovered[1], position[1])

    def test_projection_roundtrip_with_canvas_view_state_recovers_original_coordinates(self) -> None:
        graph = build_test_square_graph()
        state = CanvasViewState(rotation_quadrants=1, flip_horizontal=True, flip_vertical=False)
        center_xy = compute_canvas_view_center(node.position for node in graph.nodes)
        transformed_positions = [
            transform_canvas_view_position(
                node.position,
                center_xy=center_xy,
                view_state=state,
            )
            for node in graph.nodes
        ]
        projection = build_canvas_projection(transformed_positions, width=800, height=600)

        for node in graph.nodes:
            transformed = transform_canvas_view_position(
                node.position,
                center_xy=center_xy,
                view_state=state,
            )
            canvas_point = project_point(transformed, projection)
            projected_world = unproject_point(canvas_point[0], canvas_point[1], projection)
            recovered = inverse_canvas_view_position(
                projected_world,
                center_xy=center_xy,
                view_state=state,
            )
            self.assertAlmostEqual(recovered[0], node.position[0])
            self.assertAlmostEqual(recovered[1], node.position[1])



