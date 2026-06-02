from __future__ import annotations

from tests.route_graph_test_helpers import *

class GraphRecordNormalizationTests(unittest.TestCase):
    def test_graph_record_defaults_to_no_periodic_status_logging(self) -> None:
        parser = build_graph_record_parser()
        args = parser.parse_args(["--env-id", "DowntownWest"])
        runtime_args = _resolve_runtime_args(args)

        self.assertTrue(args.enable_physics)
        self.assertEqual(tuple(float(v) for v in args.reset_location), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(float(v) for v in args.reset_rotation), DEFAULT_RESET_ROTATION)
        self.assertEqual(runtime_args.reset_location, DEFAULT_RESET_LOCATION)
        self.assertEqual(runtime_args.reset_rotation, DEFAULT_RESET_ROTATION)
        self.assertEqual(args.status_interval, 0.0)
        self.assertEqual(args.speed_step, 0.1)
        self.assertEqual(args.yaw_step, 0.1)

    def test_graph_record_disable_physics_flag_turns_off_runtime_physics(self) -> None:
        parser = build_graph_record_parser()
        args = parser.parse_args(["--env-id", "DowntownWest", "--disable-physics"])
        runtime_args = _resolve_runtime_args(args)

        self.assertFalse(args.enable_physics)
        self.assertFalse(runtime_args.enable_physics)

    def test_graph_record_reset_pose_flags_override_defaults(self) -> None:
        parser = build_graph_record_parser()
        args = parser.parse_args(
            [
                "--env-id",
                "DowntownWest",
                "--reset-location",
                "10",
                "20",
                "30",
                "--reset-rotation",
                "0",
                "180",
                "5",
            ]
        )
        runtime_args = _resolve_runtime_args(args)
        expected_reset_location = tuple(
            base + offset
            for base, offset in zip(DEFAULT_RESET_LOCATION, (10.0, 20.0, 30.0))
        )

        self.assertEqual(tuple(float(v) for v in args.reset_location), (10.0, 20.0, 30.0))
        self.assertEqual(tuple(float(v) for v in args.reset_rotation), (0.0, 180.0, 5.0))
        self.assertEqual(runtime_args.reset_location, expected_reset_location)
        self.assertEqual(runtime_args.reset_rotation, (0.0, 180.0, 5.0))

    def test_graph_record_speed_adjustment_controls_match_manual_recorder_behavior(self) -> None:
        controller = KeyboardController(tracked_keys=("1", "2", "3", "4"), move_speed=0.3, yaw_speed=1.0)
        controller.state["1"] = True
        controller.state["4"] = True

        messages = _consume_speed_adjustments(controller, move_step=0.1, yaw_step=0.1)

        self.assertEqual(messages, ["[-] Move Speed: 0.2", "[+] Yaw Speed: 1.1"])
        self.assertEqual(controller.move_speed, 0.2)
        self.assertEqual(controller.yaw_speed, 1.1)

        controller.state["1"] = True
        controller.state["3"] = True
        controller.move_speed = 0.1
        controller.yaw_speed = 0.1

        messages = _consume_speed_adjustments(controller, move_step=0.1, yaw_step=0.1)

        self.assertEqual(messages, ["[-] Move Speed: 0.1", "[-] Yaw Speed: 0.1"])
        self.assertEqual(controller.move_speed, 0.1)
        self.assertEqual(controller.yaw_speed, 0.1)

    def test_default_output_path_uses_local_data_graphs_directory(self) -> None:
        args = argparse.Namespace(
            env_id="DowntownWest",
            normalized_env_name="DowntownWest",
            normalized_env_id="UnrealTrack-DowntownWest-ContinuousColor-v0",
            graph_name=None,
            output=None,
        )

        output_path = _resolve_output_path(args)

        self.assertEqual(output_path.parent.name, "graphs")
        self.assertEqual(output_path.name, "DowntownWest.json")

    def test_existing_graph_accepts_normalized_env_id(self) -> None:
        args = argparse.Namespace(
            env_id="DowntownWest",
            normalized_env_name="DowntownWest",
            normalized_env_id="UnrealTrack-DowntownWest-ContinuousColor-v0",
            graph_name=None,
            default_altitude=None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = Path(temp_dir) / "existing_graph.json"
            write_json_file(
                graph_path,
                build_test_square_graph(
                    env_id="UnrealTrack-DowntownWest-ContinuousColor-v0",
                ).to_dict(),
            )
            graph = _load_or_create_graph(graph_path, args)

        self.assertEqual(graph.env_id, "UnrealTrack-DowntownWest-ContinuousColor-v0")

    def test_new_graph_persists_normalized_env_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "new_graph.json"
            args = argparse.Namespace(
                env_id="DowntownWest",
                normalized_env_name="DowntownWest",
                normalized_env_id="UnrealTrack-DowntownWest-ContinuousColor-v0",
                graph_name="new_graph",
                default_altitude=350.0,
            )

            graph = _load_or_create_graph(output_path, args)

            self.assertEqual(graph.env_id, "UnrealTrack-DowntownWest-ContinuousColor-v0")



class CliBehaviorTests(unittest.TestCase):
    def test_mission_export_candidate_set_requires_candidate_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph = build_test_square_graph()
            candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=3)
            candidate_set_path = write_json_file(
                Path(temp_dir) / "candidates.json",
                candidate_set.to_dict(),
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "mission_export.py"),
                    "--candidate-set",
                    str(candidate_set_path),
                    "--output",
                    str(Path(temp_dir) / "candidate_set_without_id.json"),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 1, combined)
        self.assertIn("`--candidate-id` is required", combined)
        self.assertNotIn("Traceback", combined)

    def test_graph_editor_invalid_mutation_has_no_traceback_or_false_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = Path(temp_dir) / "square_graph.json"
            output_path = Path(temp_dir) / "bad_cross_graph.json"
            write_json_file(graph_path, build_test_square_graph().to_dict())
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "graph_editor.py"),
                    "add-edge",
                    "--graph",
                    str(graph_path),
                    "--from-node",
                    "N002",
                    "--to-node",
                    "N004",
                    "--output",
                    str(output_path),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 1, combined)
        self.assertIn("edge-intersection", combined)
        self.assertNotIn("Traceback", combined)
        self.assertNotIn("Added edge", combined)

    def test_mission_export_invalid_plan_has_no_traceback(self) -> None:
        bad_plan = {
            "env_id": "env",
            "graph_name": "graph",
            "anchor_nodes": ["A", "B"],
            "planned_nodes": ["A", "Z"],
            "segments": [
                {
                    "start_anchor": "A",
                    "end_anchor": "B",
                    "node_ids": ["A", "Z"],
                    "edge_ids": ["E001"],
                    "length": 1.0,
                }
            ],
            "total_length": 1.0,
            "node_lookup": {
                "A": {
                    "id": "A",
                    "name": "A",
                    "position": [0.0, 0.0, 0.0],
                    "yaw_hint": 0.0,
                    "tags": [],
                    "meta": {},
                }
            },
            "meta": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "bad_plan.json"
            mission_path = Path(temp_dir) / "bad_mission.json"
            plan_path.write_text(json.dumps(bad_plan, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "mission_export.py"),
                    "--plan",
                    str(plan_path),
                    "--output",
                    str(mission_path),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 1, combined)
        self.assertIn("missing-plan-node", combined)
        self.assertNotIn("Traceback", combined)

    def test_mission_export_graph_uses_default_altitude_when_fixed_z_is_omitted(self) -> None:
        graph = RouteGraph(
            env_id="env",
            graph_name="default_altitude_graph",
            default_altitude=350.0,
            nodes=[
                GraphNode(id="A", name="A", position=[0.0, 0.0, 100.0], yaw_hint=0.0),
                GraphNode(id="B", name="B", position=[100.0, 0.0, 200.0], yaw_hint=0.0),
            ],
            edges=[GraphEdge(id="E001", from_node="A", to_node="B", weight=100.0, bidirectional=True)],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            graph_path = Path(temp_dir) / "graph.json"
            mission_path = Path(temp_dir) / "mission.json"
            graph_path.write_text(json.dumps(graph.to_dict(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "mission_export.py"),
                    "--graph",
                    str(graph_path),
                    "--start",
                    "A",
                    "--end",
                    "B",
                    "--output",
                    str(mission_path),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

            combined = f"{result.stdout}\n{result.stderr}"
            self.assertEqual(result.returncode, 0, combined)
            mission = json.loads(mission_path.read_text(encoding="utf-8"))
            self.assertEqual(mission["route_meta"]["fixed_z"], 350.0)

    def test_mission_export_batch_selected_candidates_writes_multiple_files(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=3)
        for candidate in candidate_set.candidates:
            candidate.selected = candidate.candidate_id in {"C002", "C003"}
        candidate_set.sync_selected_ids()

        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_set_path = Path(temp_dir) / "candidates.json"
            output_dir = Path(temp_dir) / "missions"
            candidate_set_path.write_text(
                json.dumps(candidate_set.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "mission_export.py"),
                    "--candidate-set",
                    str(candidate_set_path),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            combined = f"{result.stdout}\n{result.stderr}"
            self.assertEqual(result.returncode, 0, combined)
            self.assertTrue((output_dir / "test_square_graph_C002.json").exists())
            self.assertTrue((output_dir / "test_square_graph_C003.json").exists())
            self.assertFalse((output_dir / "test_square_graph_C001.json").exists())

    def test_mission_export_batch_requires_selected_candidates(self) -> None:
        graph = build_test_square_graph()
        candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=2)
        for candidate in candidate_set.candidates:
            candidate.selected = False
        candidate_set.sync_selected_ids()

        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_set_path = Path(temp_dir) / "candidates.json"
            output_dir = Path(temp_dir) / "missions"
            candidate_set_path.write_text(
                json.dumps(candidate_set.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "mission_export.py"),
                    "--candidate-set",
                    str(candidate_set_path),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 1, combined)
        self.assertIn("no selected candidates", combined.lower())
        self.assertNotIn("Traceback", combined)

    def test_mission_export_batch_rejects_mixed_single_and_batch_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph = build_test_square_graph()
            candidate_set = generate_route_candidates(graph, "N001", "N004", max_routes=3)
            candidate_set_path = write_json_file(
                Path(temp_dir) / "candidates.json",
                candidate_set.to_dict(),
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "mission_export.py"),
                    "--candidate-set",
                    str(candidate_set_path),
                    "--candidate-id",
                    "C001",
                    "--output-dir",
                    str(Path(temp_dir) / "missions"),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 1, combined)
        self.assertIn("`--candidate-id` is only valid for single-candidate export", combined)
        self.assertNotIn("Traceback", combined)

    def test_takeoff_landing_repair_cli_rejects_missing_start_name_without_traceback(self) -> None:
        mission = build_mission_from_plan(
            build_simple_repair_plan(),
            step_distance=1000.0,
            fps=2.0,
            altitude_mode="fixed",
            fixed_z=100.0,
            turn_smoothing_enabled=False,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            missions_root = temp_root / "missions" / "Venice"
            photos_root = temp_root / "photos" / "Venice"
            mission_name = "Venice_C001"
            missions_root.mkdir(parents=True, exist_ok=True)
            (photos_root / mission_name).mkdir(parents=True, exist_ok=True)
            write_json_file(missions_root / f"{mission_name}.json", mission)
            for index, position in enumerate(mission["positions"]):
                ((photos_root / mission_name) / position["image_path"]).write_bytes(
                    f"frame-{index}".encode("utf-8")
                )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "takeoff_landing_repair.py"),
                    "--missions-root",
                    str(missions_root),
                    "--photos-root",
                    str(photos_root),
                    "--start-name",
                    "Venice_C999",
                    "--dry-run",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 1, combined)
        self.assertIn("`--start-name` was not found", combined)
        self.assertNotIn("Traceback", combined)


if __name__ == "__main__":
    unittest.main()


