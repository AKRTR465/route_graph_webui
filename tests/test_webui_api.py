from __future__ import annotations

from tests.route_graph_test_helpers import *
from route_graph_webui.graph.edge_intent import resolve_edge_creation_meta


resolve_graph_gui_edge_creation_meta = graph_gui_module.resolve_graph_gui_edge_creation_meta

class WebUiServerFrontendStaticTests(unittest.TestCase):
    def test_default_cors_is_local_only_unless_explicitly_opened(self) -> None:
        self.assertEqual(
            server_module._resolve_cors_allow_origins({}),
            ["http://127.0.0.1:8000", "http://127.0.0.1:5173"],
        )
        self.assertEqual(
            server_module._resolve_cors_allow_origins({"ROUTE_GRAPH_WEBUI_ALLOW_LAN": "1"}),
            ["*"],
        )
        self.assertEqual(
            server_module._resolve_cors_allow_origins(
                {"ROUTE_GRAPH_WEBUI_CORS_ORIGINS": "http://localhost:8000, http://127.0.0.1:9000"}
            ),
            ["http://localhost:8000", "http://127.0.0.1:9000"],
        )

    def test_frontend_dist_is_served_without_affecting_api_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_root = Path(temp_dir) / "dist"
            assets_root = dist_root / "assets"
            assets_root.mkdir(parents=True, exist_ok=True)
            (dist_root / "index.html").write_text("<html><body>standalone webui</body></html>", encoding="utf-8")
            (dist_root / "favicon.svg").write_text("<svg />", encoding="utf-8")
            (assets_root / "app.js").write_text("console.log('standalone');", encoding="utf-8")

            with mock.patch.object(server_module, "FRONTEND_DIST_ROOT", dist_root):
                client = TestClient(server_module.app)
                root_response = client.get("/")
                asset_response = client.get("/assets/app.js")
                spa_response = client.get("/planner/view")
                ping_response = client.get("/api/ping")

            self.assertEqual(root_response.status_code, 200, root_response.text)
            self.assertIn("standalone webui", root_response.text)
            self.assertEqual(asset_response.status_code, 200, asset_response.text)
            self.assertIn("standalone", asset_response.text)
            self.assertEqual(spa_response.status_code, 200, spa_response.text)
            self.assertIn("standalone webui", spa_response.text)
            self.assertEqual(ping_response.status_code, 200, ping_response.text)
            self.assertEqual(ping_response.json(), {"status": "ok"})

    def test_health_reports_runtime_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            graph_root = data_root / "graphs"
            dist_root = temp_root / "dist"
            graph_root.mkdir(parents=True, exist_ok=True)
            dist_root.mkdir(parents=True, exist_ok=True)
            (dist_root / "index.html").write_text("<html></html>", encoding="utf-8")
            write_json_file(graph_root / "health_graph.json", build_test_square_graph().to_dict())

            with (
                mock.patch.object(server_module, "DATA_ROOT", data_root),
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "FRONTEND_DIST_ROOT", dist_root),
            ):
                client = TestClient(server_module.app)
                response = client.get("/api/health")

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["version"], server_module.WEBUI_VERSION)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["frontend_dist"]["exists"])
            self.assertTrue(payload["frontend_dist"]["index_exists"])
            self.assertEqual(payload["graphs"]["count"], 1)
            self.assertTrue(payload["data_dir"]["writable"])
            self.assertIn("auto_plan", payload["workers"])
            self.assertTrue(payload["workers"]["auto_plan"]["worker_exists"])



class WebUiServerCanvasViewApiTests(unittest.TestCase):
    def test_update_canvas_view_persists_non_default_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "canvas_view_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/graph/canvas-view",
                    json={
                        "graph": graph_path.name,
                        "rotation_quadrants": 1,
                        "flip_horizontal": True,
                        "flip_vertical": False,
                    },
                )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(
                payload["graph"]["meta"][GRAPH_GUI_CANVAS_VIEW_META_KEY],
                {
                    "rotation_quadrants": 1,
                    "flip_horizontal": True,
                    "flip_vertical": False,
                },
            )

            saved = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["meta"][GRAPH_GUI_CANVAS_VIEW_META_KEY],
                {
                    "rotation_quadrants": 1,
                    "flip_horizontal": True,
                    "flip_vertical": False,
                },
            )

    def test_update_canvas_view_reset_removes_meta_key(self) -> None:
        graph = build_test_square_graph()
        write_graph_gui_canvas_view(
            graph.meta,
            {
                "rotation_quadrants": 3,
                "flip_horizontal": False,
                "flip_vertical": True,
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "canvas_view_graph.json",
                graph.to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/graph/canvas-view",
                    json={
                        "graph": graph_path.name,
                        "rotation_quadrants": 0,
                        "flip_horizontal": False,
                        "flip_vertical": False,
                    },
                )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertNotIn(GRAPH_GUI_CANVAS_VIEW_META_KEY, payload["graph"]["meta"])

            saved = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertNotIn(GRAPH_GUI_CANVAS_VIEW_META_KEY, saved["meta"])



class WebUiServerUiStateApiTests(unittest.TestCase):
    def test_last_graph_state_changes_default_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            state_path = Path(temp_dir) / "webui_state.json"
            default_graph_path = write_json_file(
                graph_root / "DowntownWest.json",
                build_test_square_graph(graph_name="default_graph").to_dict(),
            )
            remembered_graph_path = write_json_file(
                graph_root / "remembered_graph.json",
                build_test_square_graph(graph_name="remembered_graph").to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "WEBUI_APP_STATE_PATH", state_path),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (default_graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                update_response = client.post(
                    "/api/app/last-graph",
                    json={"graph": remembered_graph_path.name},
                )
                catalog_response = client.get("/api/graphs")

            self.assertEqual(update_response.status_code, 200, update_response.text)
            self.assertEqual(update_response.json()["last_graph"], remembered_graph_path.name)
            self.assertEqual(catalog_response.status_code, 200, catalog_response.text)
            self.assertEqual(catalog_response.json()["default_graph"], remembered_graph_path.name)

    def test_update_graph_ui_state_persists_graph_specific_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            state_path = Path(temp_dir) / "webui_state.json"
            graph = build_test_square_graph()
            write_graph_gui_export_inputs(
                graph.meta,
                {
                    "step_distance": "60",
                    "fps": "2",
                    "corner_radius": "900",
                    "turn_smoothing_enabled": False,
                },
            )
            write_graph_gui_auto_plan_inputs(
                graph.meta,
                {
                    "planning_mode": "manual",
                    "auto_enable_global_coverage": True,
                },
            )
            graph_path = write_json_file(
                graph_root / "stateful_graph.json",
                graph.to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "WEBUI_APP_STATE_PATH", state_path),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                update_response = client.post(
                    "/api/graph/ui-state",
                    json={
                        "graph": graph_path.name,
                        "planner_inputs": {
                            "planning_mode": "auto",
                            "max_routes": "11",
                            "max_edge_pass_factor": "3.25",
                            "min_total_length": "",
                            "max_total_length": "8800",
                            "min_frame_count": "24",
                            "max_frame_count": "240",
                        },
                        "group_inputs": {
                            "active_group_color": "#00ff00",
                        },
                        "auto_plan_inputs": {
                            "auto_max_output_routes": "8",
                            "auto_allowed_route_group_colors": ["#00ff00", "#ff0000"],
                        },
                        "export_inputs": {
                            "step_distance": "55",
                            "fps": "4",
                            "altitude_mode": "fixed",
                            "fixed_z": "120",
                            "altitude_offset": "0",
                            "node_sample_radius": "15",
                            "turn_smoothing_enabled": True,
                            "candidate_set_file_name": "stateful.candidates.json",
                            "missions_output_dir": "missions/stateful",
                        },
                    },
                )
                fetch_response = client.get("/api/graph", params={"graph": graph_path.name})

            self.assertEqual(update_response.status_code, 200, update_response.text)
            payload = update_response.json()
            self.assertEqual(payload["ui_state"]["planner_inputs"]["planning_mode"], "auto")
            self.assertEqual(payload["ui_state"]["planner_inputs"]["max_routes"], "11")
            self.assertEqual(payload["ui_state"]["planner_inputs"]["min_frame_count"], "24")
            self.assertEqual(payload["ui_state"]["group_inputs"]["active_group_color"], "#00FF00")
            self.assertEqual(
                payload["ui_state"]["auto_plan_inputs"]["auto_allowed_route_group_colors"],
                ["#00FF00", "#FF0000"],
            )
            self.assertEqual(
                payload["ui_state"]["export_inputs"]["candidate_set_file_name"],
                "stateful.candidates.json",
            )
            self.assertEqual(
                payload["ui_state"]["export_inputs"]["missions_output_dir"],
                "missions/stateful",
            )

            self.assertEqual(fetch_response.status_code, 200, fetch_response.text)
            fetched_ui_state = fetch_response.json()["ui_state"]
            self.assertEqual(fetched_ui_state["planner_inputs"]["max_edge_pass_factor"], "3.25")
            self.assertEqual(fetched_ui_state["planner_inputs"]["max_frame_count"], "240")
            self.assertEqual(fetched_ui_state["group_inputs"]["active_group_color"], "#00FF00")
            self.assertEqual(fetched_ui_state["export_inputs"]["step_distance"], "55")

            saved = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["meta"][GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY]["planning_mode"], "auto")
            self.assertEqual(saved["meta"][GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY]["auto_max_output_routes"], "8")
            self.assertTrue(saved["meta"][GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY]["auto_enable_global_coverage"])
            self.assertEqual(saved["meta"][GRAPH_GUI_WEBUI_INPUTS_META_KEY]["min_frame_count"], "24")
            self.assertEqual(saved["meta"][GRAPH_GUI_WEBUI_INPUTS_META_KEY]["max_frame_count"], "240")
            self.assertEqual(saved["meta"][GRAPH_GUI_EXPORT_INPUTS_META_KEY]["node_sample_radius"], "15")
            self.assertEqual(saved["meta"][GRAPH_GUI_EXPORT_INPUTS_META_KEY]["corner_radius"], "900")
            self.assertEqual(saved["meta"][GRAPH_GUI_WEBUI_INPUTS_META_KEY]["active_group_color"], "#00FF00")
            self.assertEqual(
                saved["meta"][GRAPH_GUI_WEBUI_INPUTS_META_KEY]["candidate_set_file_name"],
                "stateful.candidates.json",
            )

    def test_update_graph_group_config_persists_bridge_color_and_group_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            graph = build_group_bridge_graph()
            graph_path = write_json_file(graph_root / "group_editor_graph.json", graph.to_dict())

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/graph/group-config",
                    json={
                        "graph": graph_path.name,
                        "group_color": "#ff0000",
                        "group_config": {
                            "altitude_mode": "follow_nodes",
                            "fixed_z": "120",
                            "node_sample_radius": "15",
                        },
                        "bridge_color": "#123456",
                    },
                )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["group_editor_state"]["bridge_color"], "#123456")
            self.assertEqual(
                payload["group_editor_state"]["group_configs"]["#FF0000"]["altitude_mode"],
                "follow_nodes",
            )

            saved = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["meta"][GRAPH_BRIDGE_STYLE_META_KEY]["color"], "#123456")
            self.assertEqual(
                saved["meta"][GRAPH_GROUP_CONFIGS_META_KEY]["#FF0000"]["node_sample_radius"],
                "15",
            )

    def test_last_graph_invalid_entry_falls_back_to_default_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            state_path = Path(temp_dir) / "webui_state.json"
            default_graph_path = write_json_file(
                graph_root / "DowntownWest.json",
                build_test_square_graph(graph_name="default_graph").to_dict(),
            )
            state_path.write_text(
                json.dumps({"last_graph": "missing.json"}, ensure_ascii=False),
                encoding="utf-8",
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "WEBUI_APP_STATE_PATH", state_path),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (default_graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                catalog_response = client.get("/api/graphs")

            self.assertEqual(catalog_response.status_code, 200, catalog_response.text)
            self.assertEqual(catalog_response.json()["default_graph"], default_graph_path.name)



class WebUiServerMissionPreviewApiTests(unittest.TestCase):
    @staticmethod
    def _build_mission_request(candidate_set) -> dict[str, Any]:
        return {
            "candidate_set": candidate_set.to_dict(),
            "candidate_id": "C001",
            "step_distance": 50.0,
            "fps": 4.0,
            "altitude_mode": "fixed",
            "fixed_z": 120.0,
            "altitude_offset": 0.0,
            "takeoff_landing_relative_z": None,
            "takeoff_landing_step_distance": None,
            "node_sample_radius": 0.0,
            "random_seed": 11,
            "turn_smoothing_enabled": True,
            "corner_radius": 450.0,
            "small_turn_yaw_blend_threshold_deg": 12.0,
            "corner_min_angle_deg": 20.0,
            "u_turn_threshold_deg": 150.0,
            "u_turn_transition_distance": 180.0,
            "corner_max_yaw_step_deg": 2.0,
            "u_turn_pivot_yaw_step_deg": 2.5,
        }

    def test_preview_mission_returns_route_meta_for_candidate(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=1)

        client = TestClient(server_module.app)
        response = client.post(
            "/api/missions/preview",
            json=self._build_mission_request(candidate_set),
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["candidate_id"], "C001")
        self.assertGreater(len(payload["mission"]["positions"]), 0)
        self.assertEqual(payload["mission"]["route_meta"]["candidate_id"], "C001")
        self.assertEqual(payload["mission"]["route_meta"]["corner_radius"], 450.0)
        self.assertEqual(
            payload["mission"]["route_meta"]["small_turn_yaw_blend_threshold_deg"],
            12.0,
        )

    def test_preview_mission_rejects_unknown_candidate(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=1)
        payload = self._build_mission_request(candidate_set)
        payload["candidate_id"] = "missing"

        client = TestClient(server_module.app)
        response = client.post("/api/missions/preview", json=payload)

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("candidate", response.text.lower())

    def test_export_missions_passes_advanced_smoothing_parameters(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=1)

        with tempfile.TemporaryDirectory() as temp_dir:
            mission_output_dir = Path(temp_dir) / "preview_test"
            mocked_summary = {
                "requested_candidate_ids": ["C001"],
                "succeeded": ["C001"],
                "failed": [],
                "written_files": {"C001": str(mission_output_dir / "C001.json")},
                "errors": {},
            }
            with mock.patch.object(
                server_module,
                "_resolve_mission_output_dir",
                return_value=mission_output_dir,
            ), mock.patch.object(
                server_module,
                "_project_relative_path",
                side_effect=lambda path: Path(path).as_posix(),
            ), mock.patch.object(
                server_module,
                "export_candidate_missions",
                return_value=mocked_summary,
            ) as mocked_export:
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/missions/export",
                    json={
                        **self._build_mission_request(candidate_set),
                        "output_dir": "preview_test",
                        "candidate_ids": ["C001"],
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["requested_candidate_ids"], ["C001"])
        self.assertTrue(mocked_export.called)
        _, kwargs = mocked_export.call_args
        export_config = kwargs["export_config"]
        self.assertEqual(export_config["corner_radius"], 450.0)
        self.assertEqual(export_config["small_turn_yaw_blend_threshold_deg"], 12.0)
        self.assertEqual(export_config["u_turn_transition_distance"], 180.0)
        self.assertEqual(export_config["u_turn_pivot_yaw_step_deg"], 2.5)



class WebUiServerManualPlanApiTests(unittest.TestCase):
    @staticmethod
    def _build_manual_export_config() -> dict[str, Any]:
        return {
            "step_distance": 100.0,
            "fps": 4.0,
            "altitude_mode": "fixed",
            "fixed_z": 0.0,
            "altitude_offset": 0.0,
            "takeoff_landing_relative_z": None,
            "takeoff_landing_step_distance": None,
            "node_sample_radius": 0.0,
            "random_seed": None,
            "turn_smoothing_enabled": False,
            "corner_radius": 900.0,
            "small_turn_yaw_blend_threshold_deg": 15.0,
            "corner_min_angle_deg": 20.0,
            "u_turn_threshold_deg": 150.0,
            "u_turn_transition_distance": 240.0,
            "corner_max_yaw_step_deg": 2.0,
            "u_turn_pivot_yaw_step_deg": 2.5,
        }

    def test_manual_plan_with_length_filter_auto_keeps_all_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            graph_path = write_json_file(
                graph_root / "manual_filter_graph.json",
                build_manual_filter_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/plan",
                    json={
                        "graph": graph_path.name,
                        "start_node": "A",
                        "end_node": "C",
                        "via_nodes": [],
                        "max_routes": 3,
                        "max_edge_pass_factor": 2.5,
                        "min_total_length": 150.0,
                        "export_config": self._build_manual_export_config(),
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["meta"]["auto_keep_candidates"])
        self.assertEqual(
            payload["selected_candidate_ids"],
            [candidate["candidate_id"] for candidate in payload["candidates"]],
        )
        self.assertTrue(all(candidate["selected"] for candidate in payload["candidates"]))
        self.assertTrue(
            all(
                isinstance(candidate["meta"].get("frame_count"), int)
                for candidate in payload["candidates"]
            )
        )

    def test_manual_plan_applies_frame_filter_with_export_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            graph_path = write_json_file(
                graph_root / "manual_filter_graph.json",
                build_manual_filter_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/plan",
                    json={
                        "graph": graph_path.name,
                        "start_node": "A",
                        "end_node": "C",
                        "via_nodes": [],
                        "max_routes": 3,
                        "max_edge_pass_factor": 2.5,
                        "min_frame_count": 4,
                        "export_config": self._build_manual_export_config(),
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["meta"]["min_frame_count"], 4)
        self.assertTrue(payload["meta"]["auto_keep_candidates"])
        self.assertEqual(len(payload["candidates"]), 1)
        self.assertGreaterEqual(payload["candidates"][0]["meta"]["frame_count"], 4)
        self.assertEqual(payload["selected_candidate_ids"], [payload["candidates"][0]["candidate_id"]])



class WebUiServerEdgeApiTests(unittest.TestCase):
    def test_add_edge_infers_bridge_between_different_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            graph_path = write_json_file(
                graph_root / "group_bridge_graph.json",
                build_group_bridge_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/edge/add",
                    json={
                        "graph": graph_path.name,
                        "from_node": "A",
                        "to_node": "D",
                        "bidirectional": True,
                    },
                )

            self.assertEqual(response.status_code, 200, response.text)
            created_edge = response.json()["graph"]["edges"][-1]
            self.assertEqual(created_edge["meta"]["edge_kind"], EDGE_KIND_BRIDGE)
            self.assertNotIn(EDGE_GROUP_COLOR_META_KEY, created_edge["meta"])

    def test_edge_intent_matches_shared_service_gui_and_api(self) -> None:
        expected_meta = resolve_edge_creation_meta(
            build_group_bridge_graph(),
            from_node="A",
            to_node="D",
        )
        gui_graph = build_group_bridge_graph()
        gui_meta = resolve_graph_gui_edge_creation_meta(
            gui_graph,
            "A",
            "D",
            fallback_group_color="#334155",
        )
        GraphEditor(gui_graph).add_edge("A", "D", meta=gui_meta)

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            graph_path = write_json_file(
                graph_root / "group_bridge_graph.json",
                build_group_bridge_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/edge/add",
                    json={
                        "graph": graph_path.name,
                        "from_node": "A",
                        "to_node": "D",
                        "bidirectional": True,
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        api_meta = response.json()["graph"]["edges"][-1]["meta"]
        self.assertEqual(gui_graph.edges[-1].meta, expected_meta)
        self.assertEqual(api_meta, expected_meta)

    def test_remove_edge_between_deletes_pair_without_explicit_edge_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir) / "graphs"
            graph_root.mkdir(parents=True, exist_ok=True)
            graph_path = write_json_file(
                graph_root / "square_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
            ):
                client = TestClient(server_module.app)
                response = client.post(
                    "/api/edge/remove-between",
                    json={
                        "graph": graph_path.name,
                        "from_node": "N001",
                        "to_node": "N004",
                    },
                )

            self.assertEqual(response.status_code, 200, response.text)
            remaining_pairs = {
                frozenset((edge["from"], edge["to"]))
                for edge in response.json()["graph"]["edges"]
            }
            self.assertNotIn(frozenset(("N001", "N004")), remaining_pairs)



class _FakeBackgroundProcess:
    _next_pid = 5000

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.returncode: int | None = None
        self.pid = _FakeBackgroundProcess._next_pid
        _FakeBackgroundProcess._next_pid += 1

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int | None:
        return self.returncode



class WebUiServerAutoPlanJobApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._reset_auto_plan_jobs()

    def tearDown(self) -> None:
        self._reset_auto_plan_jobs()

    def _reset_auto_plan_jobs(self) -> None:
        with server_module._AUTO_PLAN_JOB_LOCK:
            records = list(server_module._AUTO_PLAN_JOBS.values())
            server_module._AUTO_PLAN_JOBS.clear()
            server_module.auto_plan_job_service.sequence = 0
        for record in records:
            server_module._cleanup_auto_plan_runtime(record)

    def _create_job_response(
        self,
        client: TestClient,
        graph_name: str,
    ):
        return client.post(
            "/api/plan/auto/jobs",
            json={
                "graph": graph_name,
                "max_output_routes": 3,
                "max_routes_per_pair": 1,
                "max_anchor_pairs_to_evaluate": 12,
                "distance_per_frame": 50.0,
                "min_frame_count": 2,
                "max_frame_count": 4,
            },
        )

    def test_create_auto_plan_job_returns_running_job_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "auto_plan_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
                mock.patch.object(server_module.subprocess, "Popen", _FakeBackgroundProcess),
            ):
                client = TestClient(server_module.app)
                response = self._create_job_response(client, graph_path.name)

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertGreater(payload["job_id"], 0)
            self.assertEqual(payload["graph"], graph_path.name)
            self.assertEqual(payload["state"], "running")
            self.assertIsNone(payload["progress"])
            self.assertIsNone(payload["candidate_set"])

    def test_create_auto_plan_job_runtime_paths_stay_under_progress_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            graph_root = temp_root / "graphs"
            graph_root.mkdir()
            progress_root = temp_root / "progress"
            graph_path = write_json_file(
                graph_root / "auto_plan_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "PROGRESS_ROOT", progress_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
                mock.patch.object(server_module.subprocess, "Popen", _FakeBackgroundProcess),
            ):
                client = TestClient(server_module.app)
                response = self._create_job_response(client, graph_path.name)
                self.assertEqual(response.status_code, 200, response.text)
                record = server_module._AUTO_PLAN_JOBS[response.json()["job_id"]]

                for path in (
                    record.runtime_dir,
                    record.payload_path,
                    record.progress_path,
                    record.result_path,
                    record.error_path,
                    record.stderr_path,
                ):
                    path.resolve().relative_to(progress_root.resolve())

                self.assertNotEqual(record.runtime_dir.parent, Path(tempfile.gettempdir()).resolve())

    def test_startup_cleanup_removes_orphaned_auto_plan_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            progress_root = Path(temp_dir) / "progress"
            orphan = progress_root / "route_graph_webui_auto_plan_orphan"
            unrelated = progress_root / "other-runtime"
            orphan.mkdir(parents=True)
            unrelated.mkdir(parents=True)
            (orphan / "payload.json").write_text("{}", encoding="utf-8")

            with mock.patch.object(server_module, "PROGRESS_ROOT", progress_root):
                server_module._ensure_server_directories()

            self.assertFalse(orphan.exists())
            self.assertTrue(unrelated.exists())

    def test_cancel_auto_plan_job_terminates_process_and_reports_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "auto_plan_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
                mock.patch.object(server_module.subprocess, "Popen", _FakeBackgroundProcess),
            ):
                client = TestClient(server_module.app)
                create_response = self._create_job_response(client, graph_path.name)
                self.assertEqual(create_response.status_code, 200, create_response.text)
                job_id = create_response.json()["job_id"]
                record = server_module._AUTO_PLAN_JOBS[job_id]
                process = record.process

                cancel_response = client.post(f"/api/plan/auto/jobs/{job_id}/cancel")

            self.assertEqual(cancel_response.status_code, 200, cancel_response.text)
            payload = cancel_response.json()
            self.assertEqual(payload["state"], "cancelled")
            self.assertIn("取消", payload["error"])
            self.assertIsNotNone(process)
            self.assertEqual(process.returncode, -15)

    def test_get_auto_plan_job_returns_running_progress(self) -> None:
        progress_payload = {
            "phase": "planning_routes",
            "pairs_considered": 4,
            "max_pairs_to_evaluate": 12,
            "valid_pairs_found": 4,
            "candidate_pool_size": 7,
            "selected_routes": 0,
            "max_output_routes": 3,
            "done": False,
            "progress_kind": "auto",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "auto_plan_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
                mock.patch.object(server_module.subprocess, "Popen", _FakeBackgroundProcess),
            ):
                client = TestClient(server_module.app)
                create_response = self._create_job_response(client, graph_path.name)
                self.assertEqual(create_response.status_code, 200, create_response.text)
                job_id = create_response.json()["job_id"]
                record = server_module._AUTO_PLAN_JOBS[job_id]
                record.progress_path.write_text(
                    json.dumps(
                        {
                            "type": "progress",
                            "job_id": job_id,
                            "progress": progress_payload,
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                status_response = client.get(f"/api/plan/auto/jobs/{job_id}")

            self.assertEqual(status_response.status_code, 200, status_response.text)
            payload = status_response.json()
            self.assertEqual(payload["state"], "running")
            self.assertEqual(payload["progress"]["progress_kind"], "auto")
            self.assertEqual(payload["progress"]["pairs_considered"], 4)
            self.assertEqual(payload["progress"]["candidate_pool_size"], 7)

    def test_get_auto_plan_job_returns_succeeded_result(self) -> None:
        candidate_set = auto_plan_routes(
            build_test_square_graph(),
            AutoPlanningConfig(
                max_output_routes=3,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=50.0,
                min_frame_count=2,
                max_frame_count=4,
            ),
        ).to_dict()

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "auto_plan_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
                mock.patch.object(server_module.subprocess, "Popen", _FakeBackgroundProcess),
            ):
                client = TestClient(server_module.app)
                create_response = self._create_job_response(client, graph_path.name)
                self.assertEqual(create_response.status_code, 200, create_response.text)
                job_id = create_response.json()["job_id"]
                record = server_module._AUTO_PLAN_JOBS[job_id]
                record.result_path.write_text(
                    json.dumps(
                        {
                            "type": "success",
                            "job_id": job_id,
                            "candidate_set": candidate_set,
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                status_response = client.get(f"/api/plan/auto/jobs/{job_id}")

            self.assertEqual(status_response.status_code, 200, status_response.text)
            payload = status_response.json()
            self.assertEqual(payload["state"], "succeeded")
            self.assertEqual(payload["candidate_set"]["meta"]["planning_mode"], "auto")
            self.assertGreater(len(payload["candidate_set"]["candidates"]), 0)

    def test_get_auto_plan_job_returns_failed_worker_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "auto_plan_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
                mock.patch.object(server_module.subprocess, "Popen", _FakeBackgroundProcess),
            ):
                client = TestClient(server_module.app)
                create_response = self._create_job_response(client, graph_path.name)
                self.assertEqual(create_response.status_code, 200, create_response.text)
                job_id = create_response.json()["job_id"]
                record = server_module._AUTO_PLAN_JOBS[job_id]
                record.error_path.write_text(
                    json.dumps(
                        {
                            "type": "error",
                            "job_id": job_id,
                            "error": "`max_output_routes` must be at least 1",
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                status_response = client.get(f"/api/plan/auto/jobs/{job_id}")

            self.assertEqual(status_response.status_code, 200, status_response.text)
            payload = status_response.json()
            self.assertEqual(payload["state"], "failed")
            self.assertIn("max_output_routes", payload["error"])

    def test_get_auto_plan_job_returns_404_after_retention_window(self) -> None:
        candidate_set = auto_plan_routes(
            build_test_square_graph(),
            AutoPlanningConfig(
                max_output_routes=3,
                max_routes_per_pair=1,
                max_anchor_pairs_to_evaluate=12,
                distance_per_frame=50.0,
                min_frame_count=2,
                max_frame_count=4,
            ),
        ).to_dict()

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_root = Path(temp_dir)
            graph_path = write_json_file(
                graph_root / "auto_plan_graph.json",
                build_test_square_graph().to_dict(),
            )

            with (
                mock.patch.object(server_module, "GRAPH_ROOT", graph_root),
                mock.patch.object(server_module, "DEFAULT_GRAPH_CANDIDATES", (graph_path.name,)),
                mock.patch.object(server_module.subprocess, "Popen", _FakeBackgroundProcess),
            ):
                client = TestClient(server_module.app)
                create_response = self._create_job_response(client, graph_path.name)
                self.assertEqual(create_response.status_code, 200, create_response.text)
                job_id = create_response.json()["job_id"]
                record = server_module._AUTO_PLAN_JOBS[job_id]
                record.result_path.write_text(
                    json.dumps(
                        {
                            "type": "success",
                            "job_id": job_id,
                            "candidate_set": candidate_set,
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                status_response = client.get(f"/api/plan/auto/jobs/{job_id}")
                self.assertEqual(status_response.status_code, 200, status_response.text)

                with mock.patch.object(server_module, "AUTO_PLAN_JOB_RETENTION_SECONDS", 0):
                    expired_response = client.get(f"/api/plan/auto/jobs/{job_id}")

            self.assertEqual(expired_response.status_code, 404, expired_response.text)
            self.assertIn("not found", expired_response.json()["detail"].lower())



