from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from route_graph_webui.shared.geometry import (
    distance_3d,
    distance_point_to_segment_2d,
    interpolate_segment_3d,
    normalize_angle_deg,
    project_point_to_segment_2d,
    segments_intersect_2d,
)
from route_graph_webui.shared.image_sequence import collect_image_files, find_image_directories


class GeometryUtilsTests(unittest.TestCase):
    def test_normalize_angle_preserves_positive_half_turn(self) -> None:
        self.assertEqual(normalize_angle_deg(-180.0), 180.0)
        self.assertEqual(normalize_angle_deg(540.0), 180.0)
        self.assertEqual(normalize_angle_deg(181.0), -179.0)

    def test_distance_and_interpolation_match_existing_sampling_semantics(self) -> None:
        self.assertAlmostEqual(distance_3d([0, 0, 0], [1, 2, 2]), 3.0)
        samples = interpolate_segment_3d([0.0, 0.0, 0.0], [0.0, 0.0, 10.0], 4.0)
        self.assertEqual(len(samples), 3)
        self.assertAlmostEqual(samples[0][2], 10.0 / 3.0)
        self.assertAlmostEqual(samples[1][2], 20.0 / 3.0)
        self.assertEqual(samples[2], [0.0, 0.0, 10.0])

    def test_projection_clamps_and_handles_degenerate_segment(self) -> None:
        ratio, closest = project_point_to_segment_2d((4.0, 3.0), (0.0, 0.0), (2.0, 0.0))
        self.assertEqual(ratio, 1.0)
        self.assertEqual(closest, (2.0, 0.0))
        self.assertAlmostEqual(distance_point_to_segment_2d((4.0, 3.0), (0.0, 0.0), (2.0, 0.0)), 3.6055512755)

        zero_ratio, zero_closest = project_point_to_segment_2d((4.0, 3.0), (1.0, 1.0), (1.0, 1.0))
        self.assertEqual(zero_ratio, 0.0)
        self.assertEqual(zero_closest, (1.0, 1.0))

    def test_segments_intersect_for_crossing_and_collinear_overlap(self) -> None:
        self.assertTrue(
            segments_intersect_2d((0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0))
        )
        self.assertTrue(
            segments_intersect_2d((0.0, 0.0), (3.0, 0.0), (1.0, 0.0), (2.0, 0.0))
        )
        self.assertFalse(
            segments_intersect_2d((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0))
        )


class ImageSequenceUtilsTests(unittest.TestCase):
    def test_collect_image_files_filters_extensions_and_natural_sorts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ["frame10.png", "frame2.jpg", "frame1.PNG", "notes.txt"]:
                (root / name).write_bytes(b"x")

            self.assertEqual(
                [path.name for path in collect_image_files(root)],
                ["frame1.PNG", "frame2.jpg", "frame10.png"],
            )

    def test_find_image_directories_returns_natural_relative_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for relative in ["scene10/seq", "scene2/seq", "scene1/empty"]:
                (root / relative).mkdir(parents=True)
            (root / "scene10" / "seq" / "000001.png").write_bytes(b"x")
            (root / "scene2" / "seq" / "000001.bmp").write_bytes(b"x")
            (root / "scene1" / "empty" / "notes.txt").write_text("skip", encoding="utf-8")

            self.assertEqual(
                [path.relative_to(root).as_posix() for path in find_image_directories(root)],
                ["scene2/seq", "scene10/seq"],
            )


if __name__ == "__main__":
    unittest.main()
