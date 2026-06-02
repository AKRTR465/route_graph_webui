from __future__ import annotations

from tests.route_graph_test_helpers import *

class MissionRepairTests(unittest.TestCase):
    def _sample_original_mission(self, *, env_id: str = "UnrealTrack-Venice-ContinuousColor-v0") -> dict[str, Any]:
        mission = build_mission_from_plan(
            build_simple_repair_plan(env_id=env_id),
            step_distance=1000.0,
            fps=2.0,
            altitude_mode="fixed",
            fixed_z=100.0,
            turn_smoothing_enabled=False,
        )
        mission["env_id"] = env_id
        return mission

    def _sample_turning_mission(self, *, env_id: str = "UnrealTrack-Venice-ContinuousColor-v0") -> dict[str, Any]:
        plan = RoutePlan(
            env_id=env_id,
            graph_name="turning_repair_graph",
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
                "A": GraphNode(id="A", name="A", position=[0.0, 0.0, 100.0], yaw_hint=0.0),
                "B": GraphNode(id="B", name="B", position=[1000.0, 0.0, 100.0], yaw_hint=180.0),
                "C": GraphNode(id="C", name="C", position=[0.0, 0.0, 100.0], yaw_hint=180.0),
            },
        )
        mission = build_mission_from_plan(
            plan,
            step_distance=100.0,
            fps=2.0,
            altitude_mode="fixed",
            fixed_z=100.0,
            u_turn_transition_distance=200.0,
            u_turn_pivot_yaw_step_deg=45.0,
        )
        mission["env_id"] = env_id
        return mission

    def _populate_image_dir(
        self,
        directory: Path,
        positions: list[dict[str, Any]],
        *,
        label: str,
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for index, position in enumerate(positions):
            (directory / position["image_path"]).write_bytes(f"{label}-{index}".encode("utf-8"))

    def test_repair_mission_payload_adds_takeoff_and_landing_and_reindexes(self) -> None:
        mission = self._sample_original_mission()

        bundle = repair_mission_payload(
            mission,
            relative_z=10.0,
            takeoff_landing_step_distance=5.0,
        )

        repaired_positions = bundle.repaired_mission["positions"]
        self.assertEqual(bundle.original_count, 2)
        self.assertEqual(bundle.takeoff_count, 2)
        self.assertEqual(bundle.landing_count, 2)
        self.assertEqual(
            [position["info"]["mode"] for position in repaired_positions],
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
            [position["state"][0][2] for position in repaired_positions],
            [90.0, 95.0, 100.0, 100.0, 95.0, 90.0],
        )
        self.assertEqual([position["frame"] for position in repaired_positions], list(range(6)))
        self.assertEqual(
            [position["image_path"] for position in repaired_positions],
            [f"{index:06d}.png" for index in range(6)],
        )
        self.assertTrue(bundle.repaired_mission["route_meta"]["takeoff_landing_enabled"])
        self.assertEqual(bundle.repaired_mission["route_meta"]["takeoff_start_z"], 90.0)
        self.assertEqual(bundle.repaired_mission["route_meta"]["landing_end_z"], 90.0)
        self.assertEqual(
            [position["info"]["mode"] for position in bundle.replay_mission["positions"]],
            [
                "graph_takeoff",
                "graph_takeoff",
                "graph_landing",
                "graph_landing",
            ],
        )

    def test_merge_repair_images_uses_replay_prefix_and_suffix_order(self) -> None:
        mission = self._sample_original_mission()
        bundle = repair_mission_payload(
            mission,
            relative_z=10.0,
            takeoff_landing_step_distance=5.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            original_dir = temp_root / "original"
            replay_dir = temp_root / "replay"
            output_dir = temp_root / "merged"
            self._populate_image_dir(original_dir, mission["positions"], label="original")
            self._populate_image_dir(replay_dir, bundle.replay_mission["positions"], label="repair")

            merge_repair_images(
                original_photo_dir=original_dir,
                replay_photo_dir=replay_dir,
                output_dir=output_dir,
                original_positions=mission["positions"],
                repaired_positions=bundle.repaired_mission["positions"],
                replay_positions=bundle.replay_mission["positions"],
                takeoff_count=bundle.takeoff_count,
                landing_count=bundle.landing_count,
            )

            output_names = sorted(path.name for path in output_dir.iterdir())
            self.assertEqual(
                output_names,
                [position["image_path"] for position in bundle.repaired_mission["positions"]],
            )
            output_payloads = [
                (output_dir / f"{index:06d}.png").read_bytes().decode("utf-8")
                for index in range(len(bundle.repaired_mission["positions"]))
            ]
            self.assertEqual(
                output_payloads,
                [
                    "repair-0",
                    "repair-1",
                    "original-0",
                    "original-1",
                    "repair-2",
                    "repair-3",
                ],
            )

    def test_merge_repair_images_rejects_original_count_mismatch(self) -> None:
        mission = self._sample_original_mission()
        bundle = repair_mission_payload(
            mission,
            relative_z=10.0,
            takeoff_landing_step_distance=5.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            original_dir = temp_root / "original"
            replay_dir = temp_root / "replay"
            original_dir.mkdir(parents=True, exist_ok=True)
            replay_dir.mkdir(parents=True, exist_ok=True)
            (original_dir / mission["positions"][0]["image_path"]).write_bytes(b"only-one-original")
            self._populate_image_dir(replay_dir, bundle.replay_mission["positions"], label="repair")

            with self.assertRaises(GraphSchemaError) as ctx:
                merge_repair_images(
                    original_photo_dir=original_dir,
                    replay_photo_dir=replay_dir,
                    output_dir=temp_root / "merged",
                    original_positions=mission["positions"],
                    repaired_positions=bundle.repaired_mission["positions"],
                    replay_positions=bundle.replay_mission["positions"],
                    takeoff_count=bundle.takeoff_count,
                    landing_count=bundle.landing_count,
                )

        self.assertIn("image count mismatch", str(ctx.exception))

    def test_repair_mission_payload_accepts_existing_graph_turn_frames(self) -> None:
        mission = self._sample_turning_mission()
        self.assertTrue(any(position["info"]["mode"] == "graph_turn" for position in mission["positions"]))

        bundle = repair_mission_payload(
            mission,
            relative_z=10.0,
            takeoff_landing_step_distance=5.0,
        )

        repaired_modes = [position["info"]["mode"] for position in bundle.repaired_mission["positions"]]
        self.assertEqual(repaired_modes[0], "graph_takeoff")
        self.assertEqual(repaired_modes[-1], "graph_landing")
        self.assertIn("graph_turn", repaired_modes)
        self.assertTrue(bundle.repaired_mission["route_meta"]["takeoff_landing_enabled"])

    def test_batch_repair_dry_run_respects_start_and_end_name_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            missions_root = temp_root / "missions" / "Venice"
            photos_root = temp_root / "photos" / "Venice"
            missions_root.mkdir(parents=True, exist_ok=True)
            photos_root.mkdir(parents=True, exist_ok=True)

            for mission_name in ("Venice_C001", "Venice_C002", "Venice_C003"):
                mission = self._sample_original_mission()
                mission["graph_name"] = mission_name
                write_json_file(missions_root / f"{mission_name}.json", mission)
                self._populate_image_dir(photos_root / mission_name, mission["positions"], label=mission_name)

            args = argparse.Namespace(
                missions_root=str(missions_root),
                photos_root=str(photos_root),
                start_name="Venice_C002",
                end_name="Venice_C003",
                relative_z=200.0,
                takeoff_landing_step_distance=20.0,
                dry_run=True,
                fail_fast=False,
            )

            summary = takeoff_landing_repair_module.run_batch_repair(args)

            self.assertEqual(summary["succeeded"], ["Venice_C002", "Venice_C003"])
            self.assertEqual(summary["failed"], [])
            report_records = [
                json.loads(line)
                for line in Path(summary["report_path"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(
                [record["mission_name"] for record in report_records],
                ["Venice_C002", "Venice_C003"],
            )
            self.assertTrue(all(record["status"] == "dry_run" for record in report_records))

    def test_process_task_with_cleanup_backups_deletes_per_task_backups(self) -> None:
        mission = self._sample_original_mission()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            mission_path = temp_root / "missions" / "Venice" / "Venice_C101.json"
            photo_dir = temp_root / "photos" / "Venice" / "Venice_C101"
            mission_path.parent.mkdir(parents=True, exist_ok=True)
            write_json_file(mission_path, mission)
            self._populate_image_dir(photo_dir, mission["positions"], label="original")

            task = takeoff_landing_repair_module.RepairTask(
                mission_path=mission_path,
                photo_dir=photo_dir,
                mission_name="Venice_C101",
                scene_name="Venice",
            )

            def fake_run_replay_capture(*, repair_json_path: Path, replay_output_root: Path, env_id: str) -> Path:
                del env_id
                replay_payload = json.loads(repair_json_path.read_text(encoding="utf-8"))
                replay_dir = replay_output_root / repair_json_path.stem
                replay_dir.mkdir(parents=True, exist_ok=True)
                self._populate_image_dir(replay_dir, replay_payload["positions"], label="repair")
                return replay_dir

            with mock.patch.object(
                takeoff_landing_repair_module,
                "_run_replay_capture",
                side_effect=fake_run_replay_capture,
            ):
                record = takeoff_landing_repair_module._process_task(
                    task,
                    relative_z=10.0,
                    takeoff_landing_step_distance=5.0,
                    dry_run=False,
                    cleanup_backups=True,
                )

            self.assertEqual(record["status"], "repaired")
            self.assertEqual(record["backup_cleanup_status"], "deleted")
            self.assertFalse(Path(record["backup_json_path"]).exists())
            self.assertFalse(Path(record["backup_photo_dir"]).exists())
            repaired_mission = json.loads(mission_path.read_text(encoding="utf-8"))
            self.assertTrue(repaired_mission["route_meta"]["takeoff_landing_enabled"])
            self.assertEqual(
                len(list(photo_dir.glob("*.png"))),
                len(repaired_mission["positions"]),
            )


