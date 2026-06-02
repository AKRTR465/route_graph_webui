from __future__ import annotations

import argparse
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import composed_video
from spelling_compat import CANONICAL_PHOTOS_DIR_NAME, LEGACY_PHOTOS_DIR_NAME


class ComposedVideoTests(unittest.TestCase):
    def _create_sequence_dir(self, source_root: Path, *parts: str) -> Path:
        sequence_dir = source_root.joinpath(*parts)
        sequence_dir.mkdir(parents=True, exist_ok=True)
        for frame_name in ("000000.png", "000001.png", "000002.png"):
            sequence_dir.joinpath(frame_name).write_bytes(b"frame")
        return sequence_dir

    def _fake_compose_video(
        self,
        calls: list[tuple[Path, Path, float, Path, str]],
    ):
        def _impl(
            source_dir: Path,
            output_file: Path,
            fps: float,
            ffmpeg_path: Path,
            encoding_mode: str = composed_video.DEFAULT_ENCODING_MODE,
        ) -> dict[str, object]:
            calls.append((source_dir, output_file, fps, ffmpeg_path, encoding_mode))
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"video")
            return {
                "source_dir": source_dir,
                "output_file": output_file,
                "frames_written": 3,
                "fps": fps,
                "duration": 3.0 / fps,
                "encoding_mode": encoding_mode,
            }

        return _impl

    def test_compose_videos_deletes_source_directory_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / LEGACY_PHOTOS_DIR_NAME
            sequence_dir = self._create_sequence_dir(source_root, "SceneA", "SceneA_C001")
            output_dir = temp_path / "videos"
            ffmpeg_path = temp_path / "ffmpeg.exe"
            calls: list[tuple[Path, Path, float, Path, str]] = []

            with patch.object(
                composed_video,
                "compose_video",
                side_effect=self._fake_compose_video(calls),
            ):
                composed_video.compose_videos(
                    source_root,
                    output_dir,
                    12.0,
                    ffmpeg_path,
                )

            output_file = output_dir / "SceneA" / "SceneA_C001.mp4"
            self.assertTrue(output_file.exists())
            self.assertFalse(sequence_dir.exists())
            self.assertTrue((source_root / "SceneA").exists())
            self.assertEqual(1, len(calls))
            self.assertEqual(ffmpeg_path, calls[0][3])
            self.assertEqual(composed_video.DEFAULT_ENCODING_MODE, calls[0][4])

    def test_main_single_directory_mode_deletes_source_directory_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = self._create_sequence_dir(
                temp_path / LEGACY_PHOTOS_DIR_NAME,
                "SceneB",
                "SceneB_C001",
            )
            output_dir = temp_path / "videos"
            ffmpeg_path = temp_path / "ffmpeg.exe"
            calls: list[tuple[Path, Path, float, Path, str]] = []
            args = argparse.Namespace(
                source_root=temp_path / "unused",
                output_dir=output_dir,
                source_dir=source_dir,
                output_file=None,
                fps=24.0,
                ffmpeg_path=ffmpeg_path,
                encoding_mode="balanced",
                max_workers=0,
                keep_images=False,
                resume=False,
                resume_file=None,
                reset_resume=False,
            )

            with patch.object(composed_video, "parse_args", return_value=args):
                with patch.object(
                    composed_video,
                    "compose_video",
                    side_effect=self._fake_compose_video(calls),
                ):
                    composed_video.main()

            output_file = output_dir / "SceneB_C001.mp4"
            self.assertTrue(output_file.exists())
            self.assertFalse(source_dir.exists())
            self.assertEqual(1, len(calls))
            self.assertEqual("balanced", calls[0][4])

    def test_compose_videos_keeps_source_directory_when_keep_images_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / CANONICAL_PHOTOS_DIR_NAME
            sequence_dir = self._create_sequence_dir(source_root, "SceneKeep", "SceneKeep_C001")
            output_dir = temp_path / "videos"
            ffmpeg_path = temp_path / "ffmpeg.exe"

            with patch.object(
                composed_video,
                "compose_video",
                side_effect=self._fake_compose_video([]),
            ):
                composed_video.compose_videos(
                    source_root,
                    output_dir,
                    24.0,
                    ffmpeg_path,
                    keep_images=True,
                )

            self.assertTrue(sequence_dir.exists())
            self.assertTrue((output_dir / "SceneKeep" / "SceneKeep_C001.mp4").exists())

    def test_main_single_directory_mode_keeps_source_directory_when_keep_images_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = self._create_sequence_dir(
                temp_path / CANONICAL_PHOTOS_DIR_NAME,
                "SceneKeepSingle",
                "SceneKeepSingle_C001",
            )
            output_dir = temp_path / "videos"
            args = argparse.Namespace(
                source_root=temp_path / "unused",
                output_dir=output_dir,
                source_dir=source_dir,
                output_file=None,
                fps=24.0,
                ffmpeg_path=temp_path / "ffmpeg.exe",
                encoding_mode="balanced",
                max_workers=0,
                keep_images=True,
                resume=False,
                resume_file=None,
                reset_resume=False,
            )

            with patch.object(composed_video, "parse_args", return_value=args):
                with patch.object(
                    composed_video,
                    "compose_video",
                    side_effect=self._fake_compose_video([]),
                ):
                    composed_video.main()

            self.assertTrue(source_dir.exists())
            self.assertTrue((output_dir / "SceneKeepSingle_C001.mp4").exists())

    def test_resume_skip_keeps_source_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / CANONICAL_PHOTOS_DIR_NAME
            sequence_dir = self._create_sequence_dir(source_root, "SceneC", "SceneC_C001")
            output_dir = temp_path / "videos"
            output_file = output_dir / "SceneC" / "SceneC_C001.mp4"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"video")

            with patch.object(composed_video, "compose_video") as mock_compose_video:
                composed_video.compose_videos(
                    source_root,
                    output_dir,
                    24.0,
                    temp_path / "ffmpeg.exe",
                    max_workers=2,
                    resume=True,
                )

            mock_compose_video.assert_not_called()
            self.assertTrue(sequence_dir.exists())

    def test_resolve_batch_max_workers_auto_mode_is_bounded(self) -> None:
        with patch.object(composed_video.os, "cpu_count", return_value=8):
            self.assertEqual(1, composed_video.resolve_batch_max_workers(0, 0))
            self.assertEqual(1, composed_video.resolve_batch_max_workers(0, 1))
            self.assertEqual(3, composed_video.resolve_batch_max_workers(0, 3))
            self.assertEqual(4, composed_video.resolve_batch_max_workers(0, 10))

        with self.assertRaises(ValueError):
            composed_video.resolve_batch_max_workers(-1, 2)

    def test_compose_videos_with_max_workers_one_runs_serially(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / CANONICAL_PHOTOS_DIR_NAME
            first_dir = self._create_sequence_dir(source_root, "SceneSerial", "SceneSerial_C001")
            second_dir = self._create_sequence_dir(source_root, "SceneSerial", "SceneSerial_C002")
            output_dir = temp_path / "videos"
            ffmpeg_path = temp_path / "ffmpeg.exe"
            active_jobs = 0
            peak_jobs = 0
            lock = threading.Lock()

            def fake_compose_video(
                source_dir: Path,
                output_file: Path,
                fps: float,
                ffmpeg_path: Path,
                encoding_mode: str = composed_video.DEFAULT_ENCODING_MODE,
            ) -> dict[str, object]:
                nonlocal active_jobs, peak_jobs
                with lock:
                    active_jobs += 1
                    peak_jobs = max(peak_jobs, active_jobs)
                time.sleep(0.03)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_bytes(b"video")
                with lock:
                    active_jobs -= 1
                return {
                    "source_dir": source_dir,
                    "output_file": output_file,
                    "frames_written": 3,
                    "fps": fps,
                    "duration": 3.0 / fps,
                    "encoding_mode": encoding_mode,
                }

            with patch.object(composed_video, "compose_video", side_effect=fake_compose_video):
                composed_video.compose_videos(
                    source_root,
                    output_dir,
                    24.0,
                    ffmpeg_path,
                    max_workers=1,
                )

            self.assertEqual(1, peak_jobs)
            self.assertFalse(first_dir.exists())
            self.assertFalse(second_dir.exists())

    def test_compose_videos_with_max_workers_two_runs_in_parallel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / CANONICAL_PHOTOS_DIR_NAME
            self._create_sequence_dir(source_root, "SceneParallel", "SceneParallel_C001")
            self._create_sequence_dir(source_root, "SceneParallel", "SceneParallel_C002")
            output_dir = temp_path / "videos"
            ffmpeg_path = temp_path / "ffmpeg.exe"
            active_jobs = 0
            peak_jobs = 0
            gate = threading.Event()
            lock = threading.Lock()

            def fake_compose_video(
                source_dir: Path,
                output_file: Path,
                fps: float,
                ffmpeg_path: Path,
                encoding_mode: str = composed_video.DEFAULT_ENCODING_MODE,
            ) -> dict[str, object]:
                nonlocal active_jobs, peak_jobs
                with lock:
                    active_jobs += 1
                    peak_jobs = max(peak_jobs, active_jobs)
                    if active_jobs >= 2:
                        gate.set()
                gate.wait(timeout=0.3)
                time.sleep(0.02)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_bytes(b"video")
                with lock:
                    active_jobs -= 1
                return {
                    "source_dir": source_dir,
                    "output_file": output_file,
                    "frames_written": 3,
                    "fps": fps,
                    "duration": 3.0 / fps,
                    "encoding_mode": encoding_mode,
                }

            with patch.object(composed_video, "compose_video", side_effect=fake_compose_video):
                composed_video.compose_videos(
                    source_root,
                    output_dir,
                    24.0,
                    ffmpeg_path,
                    max_workers=2,
                )

            self.assertGreaterEqual(peak_jobs, 2)

    def test_parallel_batch_failure_does_not_block_success_and_collects_cleanup_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / CANONICAL_PHOTOS_DIR_NAME
            success_dir = self._create_sequence_dir(source_root, "SceneMixed", "SceneMixed_C001")
            fail_dir = self._create_sequence_dir(source_root, "SceneMixed", "SceneMixed_C002")
            output_dir = temp_path / "videos"
            ffmpeg_path = temp_path / "ffmpeg.exe"

            def fake_compose_video(
                source_dir: Path,
                output_file: Path,
                fps: float,
                ffmpeg_path: Path,
                encoding_mode: str = composed_video.DEFAULT_ENCODING_MODE,
            ) -> dict[str, object]:
                if source_dir == fail_dir:
                    raise RuntimeError("boom")
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_bytes(b"video")
                return {
                    "source_dir": source_dir,
                    "output_file": output_file,
                    "frames_written": 3,
                    "fps": fps,
                    "duration": 3.0 / fps,
                    "encoding_mode": encoding_mode,
                }

            with patch.object(composed_video, "compose_video", side_effect=fake_compose_video):
                with patch.object(
                    composed_video,
                    "cleanup_source_image_directory",
                    return_value="cleanup issue",
                ) as mock_cleanup:
                    with patch("builtins.print") as mock_print:
                        composed_video.compose_videos(
                            source_root,
                            output_dir,
                            24.0,
                            ffmpeg_path,
                            max_workers=2,
                        )

            printed_lines = [" ".join(str(arg) for arg in call.args) for call in mock_print.call_args_list]
            self.assertTrue((output_dir / "SceneMixed" / "SceneMixed_C001.mp4").exists())
            self.assertFalse((output_dir / "SceneMixed" / "SceneMixed_C002.mp4").exists())
            self.assertTrue(success_dir.exists())
            self.assertTrue(fail_dir.exists())
            mock_cleanup.assert_called_once_with(success_dir, output_dir / "SceneMixed" / "SceneMixed_C001.mp4")
            self.assertTrue(any("Failed directories:" in line for line in printed_lines))
            self.assertTrue(any("Directories not cleaned up:" in line for line in printed_lines))
            self.assertTrue(any("cleanup issue" in line for line in printed_lines))

    def test_create_ffmpeg_process_supports_lossless_and_balanced_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_file = temp_path / "video.mp4"
            ffmpeg_path = temp_path / "ffmpeg.exe"

            with patch.object(composed_video.subprocess, "Popen") as mock_popen:
                composed_video.create_ffmpeg_process(
                    output_file=output_file,
                    frame_size=(640, 480),
                    fps=24.0,
                    ffmpeg_path=ffmpeg_path,
                    encoding_mode="lossless",
                )

            lossless_command = mock_popen.call_args.args[0]
            self.assertIn("libx264rgb", lossless_command)
            self.assertIn("rgb24", lossless_command)
            self.assertIn("veryslow", lossless_command)
            self.assertIn("0", lossless_command)

            with patch.object(composed_video.subprocess, "Popen") as mock_popen_balanced:
                composed_video.create_ffmpeg_process(
                    output_file=output_file,
                    frame_size=(640, 480),
                    fps=24.0,
                    ffmpeg_path=ffmpeg_path,
                    encoding_mode="balanced",
                )

            balanced_command = mock_popen_balanced.call_args.args[0]
            self.assertIn("libx264", balanced_command)
            self.assertIn("yuv420p", balanced_command)
            self.assertIn("slow", balanced_command)
            self.assertIn("18", balanced_command)
            self.assertNotIn("libx264rgb", balanced_command)

    def test_resolve_encoding_profile_rejects_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            composed_video.resolve_encoding_profile("unknown")

    def test_cleanup_source_image_directory_skips_when_output_is_inside_source_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = self._create_sequence_dir(
                temp_path / CANONICAL_PHOTOS_DIR_NAME,
                "SceneD",
                "SceneD_C001",
            )
            output_file = source_dir / "SceneD_C001.mp4"
            output_file.write_bytes(b"video")

            warning = composed_video.cleanup_source_image_directory(source_dir, output_file)

            self.assertIsNotNone(warning)
            self.assertIn("inside the source image directory", warning)
            self.assertTrue(source_dir.exists())
            self.assertTrue(output_file.exists())

    def test_cleanup_source_image_directory_skips_non_image_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = self._create_sequence_dir(
                temp_path / CANONICAL_PHOTOS_DIR_NAME,
                "SceneE",
                "SceneE_C001",
            )
            source_dir.joinpath("notes.txt").write_text("keep me", encoding="utf-8")
            output_file = temp_path / "videos" / "SceneE_C001.mp4"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"video")

            warning = composed_video.cleanup_source_image_directory(source_dir, output_file)

            self.assertIsNotNone(warning)
            self.assertIn("non-image files", warning)
            self.assertTrue(source_dir.exists())

    def test_cleanup_source_image_directory_skips_nested_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = self._create_sequence_dir(
                temp_path / CANONICAL_PHOTOS_DIR_NAME,
                "SceneF",
                "SceneF_C001",
            )
            source_dir.joinpath("nested").mkdir()
            output_file = temp_path / "videos" / "SceneF_C001.mp4"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"video")

            warning = composed_video.cleanup_source_image_directory(source_dir, output_file)

            self.assertIsNotNone(warning)
            self.assertIn("nested directories", warning)
            self.assertTrue(source_dir.exists())

    def test_resolve_default_source_root_prefers_photos_then_falls_back_to_phtots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            phtots_dir = data_root / LEGACY_PHOTOS_DIR_NAME
            photos_dir = data_root / CANONICAL_PHOTOS_DIR_NAME
            phtots_dir.mkdir(parents=True)

            with self.assertWarns(DeprecationWarning):
                self.assertEqual(phtots_dir, composed_video.resolve_default_source_root(data_root))

            photos_dir.mkdir(parents=True)
            self.assertEqual(photos_dir, composed_video.resolve_default_source_root(data_root))

    def test_main_passes_max_workers_to_compose_videos(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            args = argparse.Namespace(
                source_root=temp_path / CANONICAL_PHOTOS_DIR_NAME,
                output_dir=temp_path / "videos",
                source_dir=None,
                output_file=None,
                fps=24.0,
                ffmpeg_path=temp_path / "ffmpeg.exe",
                encoding_mode="balanced",
                max_workers=3,
                keep_images=True,
                resume=True,
                resume_file=temp_path / "resume.json",
                reset_resume=False,
            )

            with patch.object(composed_video, "parse_args", return_value=args):
                with patch.object(composed_video, "compose_videos") as mock_compose_videos:
                    composed_video.main()

            mock_compose_videos.assert_called_once_with(
                args.source_root,
                args.output_dir,
                args.fps,
                args.ffmpeg_path,
                encoding_mode=args.encoding_mode,
                max_workers=args.max_workers,
                keep_images=args.keep_images,
                resume=args.resume,
                resume_file=args.resume_file,
                reset_resume=args.reset_resume,
            )


if __name__ == "__main__":
    unittest.main()
