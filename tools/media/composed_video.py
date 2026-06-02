import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROUTE_GRAPH_WEBUI_DIR = Path(__file__).resolve().parents[2]
if str(ROUTE_GRAPH_WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTE_GRAPH_WEBUI_DIR))

from spelling_compat import (
    CANONICAL_PHOTOS_DIR_NAME,
    LEGACY_PHOTOS_DIR_NAME,
    resolve_photos_root,
)
from image_sequence_utils import (
    SUPPORTED_IMAGE_EXTENSIONS,
    collect_image_files,
    find_image_directories as find_sequence_directories,
    natural_sort_key as shared_natural_sort_key,
    natural_text_key as shared_natural_text_key,
)


THIS_DIR = ROUTE_GRAPH_WEBUI_DIR
DEFAULT_DATA_PHOTOS_VIDEOS_DIR = THIS_DIR / "data" / "data_photos_videos"
DEFAULT_RESUME_FILENAME = ".compose_video_resume.json"
DEFAULT_FPS = 24.0
FFMPEG_PATH_ENV = "ROUTE_GRAPH_WEBUI_FFMPEG"
DEFAULT_FFMPEG_PATH = Path(os.environ.get(FFMPEG_PATH_ENV) or "ffmpeg")
DEFAULT_ENCODING_MODE = "balanced"
DEFAULT_MAX_WORKERS = 2
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - Pillow compatibility
    RESAMPLE_LANCZOS = Image.LANCZOS


@dataclass(frozen=True, slots=True)
class VideoEncodingProfile:
    codec: str
    pixel_format: str
    preset: str
    crf: str


ENCODING_PROFILES: dict[str, VideoEncodingProfile] = {
    "lossless": VideoEncodingProfile(
        codec="libx264rgb",
        pixel_format="rgb24",
        preset="veryslow",
        crf="0",
    ),
    "balanced": VideoEncodingProfile(
        codec="libx264",
        pixel_format="yuv420p",
        preset="slow",
        crf="18",
    ),
}


def resolve_default_source_root(data_root: Path | None = None) -> Path:
    resolved_data_root = Path(data_root) if data_root is not None else DEFAULT_DATA_PHOTOS_VIDEOS_DIR
    return resolve_photos_root(resolved_data_root)


def resolve_default_output_dir(data_root: Path | None = None) -> Path:
    resolved_data_root = Path(data_root) if data_root is not None else DEFAULT_DATA_PHOTOS_VIDEOS_DIR
    return resolved_data_root / "videos"


DEFAULT_SOURCE_ROOT = resolve_default_source_root()
DEFAULT_OUTPUT_DIR = resolve_default_output_dir()


def natural_sort_key(path: Path) -> list[object]:
    return shared_natural_sort_key(path)


def natural_text_key(text: str) -> list[object]:
    return shared_natural_text_key(text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compose image sequences into mp4 videos. "
            "Defaults to batch mode, converting all image folders under "
            f"data/data_photos_videos/{CANONICAL_PHOTOS_DIR_NAME} "
            f"(or legacy data/data_photos_videos/{LEGACY_PHOTOS_DIR_NAME}) "
            "into data/data_photos_videos/videos."
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help=f"Root directory containing one or more image folders. Default: {DEFAULT_SOURCE_ROOT}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write generated videos. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Optional single image directory to compose. If set, batch mode is disabled.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Optional output file for single-directory mode. Defaults to <output-dir>/<source-dir>.mp4.",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=DEFAULT_FPS,
        help=f"Output video fps. Default: {DEFAULT_FPS}",
    )
    parser.add_argument(
        "--ffmpeg-path",
        type=Path,
        default=DEFAULT_FFMPEG_PATH,
        help=(
            "Path to ffmpeg executable. Default: ROUTE_GRAPH_WEBUI_FFMPEG "
            "if set, otherwise `ffmpeg` from PATH."
        ),
    )
    parser.add_argument(
        "--encoding-mode",
        choices=sorted(ENCODING_PROFILES.keys()),
        default=DEFAULT_ENCODING_MODE,
        help=(
            "Video encoding profile. Use `lossless` to preserve RGB frames as much as possible, "
            "or `balanced` for smaller files and wider player compatibility. "
            f"Default: {DEFAULT_ENCODING_MODE}"
        ),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=(
            "Batch-mode worker count. Use 0 for automatic parallelism, 1 for serial mode, "
            f"or >=2 to set an explicit worker count. Default: {DEFAULT_MAX_WORKERS}"
        ),
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Keep source image directories after video generation instead of deleting them.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Enable resumable batch compose via a persisted state file.",
    )
    parser.add_argument(
        "--resume-file",
        type=Path,
        default=None,
        help=(
            "Optional state file path for resume mode. "
            f"Default: <output-dir>/{DEFAULT_RESUME_FILENAME}"
        ),
    )
    parser.add_argument(
        "--reset-resume",
        action="store_true",
        help="Reset previous resume state before processing.",
    )
    return parser.parse_args()


def collect_images(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

    images = collect_image_files(source_dir, extensions=SUPPORTED_EXTENSIONS)
    if not images:
        raise FileNotFoundError(f"No supported images found in: {source_dir}")

    return images


def find_image_directories(source_root: Path) -> list[Path]:
    if not source_root.is_dir():
        raise FileNotFoundError(f"Source root does not exist: {source_root}")

    image_dirs = find_sequence_directories(source_root, extensions=SUPPORTED_EXTENSIONS)
    if not image_dirs:
        raise FileNotFoundError(f"No image directories found under: {source_root}")

    return image_dirs


def resolve_encoding_profile(encoding_mode: str) -> VideoEncodingProfile:
    profile = ENCODING_PROFILES.get(str(encoding_mode).lower())
    if profile is None:
        supported_modes = ", ".join(sorted(ENCODING_PROFILES))
        raise ValueError(
            f"Unsupported encoding mode `{encoding_mode}`. Supported modes: {supported_modes}"
        )
    return profile


def read_image(image_path: Path) -> Image.Image | None:
    try:
        with Image.open(image_path) as image:
            return image.convert("RGB")
    except (OSError, ValueError):
        return None


def load_first_valid_frame(image_paths: list[Path]) -> tuple[Path, Image.Image]:
    for image_path in image_paths:
        frame = read_image(image_path)
        if frame is not None:
            return image_path, frame
        print(f"[WARN] Skip unreadable image while probing size: {image_path}")

    raise RuntimeError("No readable frames found in the input directory.")


def create_ffmpeg_process(
    output_file: Path,
    frame_size: tuple[int, int],
    fps: float,
    ffmpeg_path: Path,
    encoding_mode: str = DEFAULT_ENCODING_MODE,
) -> subprocess.Popen[bytes]:
    width, height = frame_size
    profile = resolve_encoding_profile(encoding_mode)
    command = [
        str(ffmpeg_path),
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-vcodec",
        profile.codec,
        "-preset",
        profile.preset,
        "-crf",
        profile.crf,
        "-pix_fmt",
        profile.pixel_format,
        str(output_file),
    ]
    try:
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"ffmpeg executable not found: {ffmpeg_path}. "
            f"Install ffmpeg, add it to PATH, set {FFMPEG_PATH_ENV}, or pass --ffmpeg-path."
        ) from exc


def now_iso8601_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_resume_path(output_dir: Path) -> Path:
    return output_dir / DEFAULT_RESUME_FILENAME


def make_empty_resume_state(source_root: Path, output_dir: Path, fps: float) -> dict[str, object]:
    return {
        "version": 1,
        "source_root": str(source_root.resolve()),
        "output_dir": str(output_dir.resolve()),
        "fps": float(fps),
        "updated_at": now_iso8601_utc(),
        "completed": {},
        "failed": {},
    }


def save_resume_state(resume_path: Path, state: dict[str, object]) -> None:
    state["updated_at"] = now_iso8601_utc()
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = resume_path.with_suffix(resume_path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as fp:
        json.dump(state, fp, indent=2, ensure_ascii=False)
    temp_path.replace(resume_path)


def load_resume_state(
    resume_path: Path,
    source_root: Path,
    output_dir: Path,
    fps: float,
) -> dict[str, object]:
    empty_state = make_empty_resume_state(source_root, output_dir, fps)
    if not resume_path.exists():
        return empty_state

    try:
        with resume_path.open("r", encoding="utf-8") as fp:
            loaded = json.load(fp)
    except (OSError, ValueError) as exc:
        print(f"[WARN] Failed to read resume file, starting fresh: {resume_path} ({exc})")
        return empty_state

    if not isinstance(loaded, dict):
        print(f"[WARN] Invalid resume file format, starting fresh: {resume_path}")
        return empty_state

    expected_source_root = str(source_root.resolve())
    expected_output_dir = str(output_dir.resolve())
    if loaded.get("source_root") != expected_source_root or loaded.get("output_dir") != expected_output_dir:
        print(
            "[WARN] Resume file does not match current source/output paths, "
            f"starting fresh: {resume_path}"
        )
        return empty_state

    loaded_fps = loaded.get("fps")
    if isinstance(loaded_fps, (int, float)) and float(loaded_fps) != float(fps):
        print(
            f"[WARN] Resume file fps={loaded_fps} differs from current fps={fps}. "
            "Completed entries will still be reused."
        )

    completed = loaded.get("completed", {})
    failed = loaded.get("failed", {})
    if not isinstance(completed, dict):
        completed = {}
    if not isinstance(failed, dict):
        failed = {}

    state = make_empty_resume_state(source_root, output_dir, fps)
    state["completed"] = completed
    state["failed"] = failed
    state["updated_at"] = loaded.get("updated_at", now_iso8601_utc())
    return state


def mark_resume_completed(
    state: dict[str, object],
    relative_key: str,
    result: dict[str, object],
) -> None:
    completed = state.setdefault("completed", {})
    failed = state.setdefault("failed", {})
    if isinstance(completed, dict):
        completed[relative_key] = {
            "output_file": str(result["output_file"]),
            "frames_written": int(result["frames_written"]),
            "fps": float(result["fps"]),
            "duration": float(result["duration"]),
            "completed_at": now_iso8601_utc(),
        }
    if isinstance(failed, dict):
        failed.pop(relative_key, None)


def mark_resume_failed(state: dict[str, object], relative_key: str, error: str) -> None:
    failed = state.setdefault("failed", {})
    if isinstance(failed, dict):
        failed[relative_key] = {
            "error": error,
            "failed_at": now_iso8601_utc(),
        }


@dataclass(frozen=True, slots=True)
class BatchComposeJob:
    source_dir: Path
    relative_key: str
    output_file: Path


@dataclass(slots=True)
class BatchComposeOutcome:
    job: BatchComposeJob
    result: dict[str, object]
    cleanup_warning: str | None


def resolve_batch_max_workers(max_workers: int, pending_jobs: int) -> int:
    if max_workers < 0:
        raise ValueError("max_workers must be greater than or equal to 0")

    if pending_jobs <= 1:
        return 1

    if max_workers == 0:
        return max(1, min(4, pending_jobs, os.cpu_count() or 1))

    return max(1, min(max_workers, pending_jobs))


def _compose_batch_job(
    job: BatchComposeJob,
    fps: float,
    ffmpeg_path: Path,
    encoding_mode: str,
    keep_images: bool,
) -> BatchComposeOutcome:
    result = compose_video(job.source_dir, job.output_file, fps, ffmpeg_path, encoding_mode)
    cleanup_warning = None if keep_images else cleanup_source_image_directory(job.source_dir, job.output_file)
    return BatchComposeOutcome(job=job, result=result, cleanup_warning=cleanup_warning)


def cleanup_source_image_directory(source_dir: Path, output_file: Path) -> str | None:
    if not source_dir.exists():
        warning = f"Source image directory is already missing, skip cleanup: {source_dir}"
        print(f"[WARN] {warning}")
        return warning
    if not source_dir.is_dir():
        warning = f"Source path is not a directory, skip cleanup: {source_dir}"
        print(f"[WARN] {warning}")
        return warning
    if not output_file.exists() or not output_file.is_file() or output_file.stat().st_size <= 0:
        warning = f"Output video is missing or empty, skip cleanup: {output_file}"
        print(f"[WARN] {warning}")
        return warning

    resolved_source_dir = source_dir.resolve()
    resolved_output_file = output_file.resolve()
    try:
        resolved_output_file.relative_to(resolved_source_dir)
    except ValueError:
        pass
    else:
        warning = (
            "Output video is inside the source image directory, skip cleanup to avoid "
            f"deleting the video: {output_file}"
        )
        print(f"[WARN] {warning}")
        return warning

    entries = list(source_dir.iterdir())
    nested_directories = [path for path in entries if path.is_dir()]
    if nested_directories:
        warning = (
            "Source image directory contains nested directories, skip cleanup: "
            f"{source_dir}"
        )
        print(f"[WARN] {warning}")
        return warning

    unexpected_files = [
        path
        for path in entries
        if (not path.is_file()) or path.suffix.lower() not in SUPPORTED_EXTENSIONS
    ]
    if unexpected_files:
        warning = (
            "Source image directory contains non-image files, skip cleanup: "
            f"{source_dir}"
        )
        print(f"[WARN] {warning}")
        return warning

    try:
        for path in entries:
            path.unlink()
        source_dir.rmdir()
    except OSError as exc:
        warning = f"Failed to remove source image directory {source_dir}: {exc}"
        print(f"[WARN] {warning}")
        return warning

    print(f"[CLEANUP] Removed source image directory: {source_dir}")
    return None


def compose_video(
    source_dir: Path,
    output_file: Path,
    fps: float,
    ffmpeg_path: Path,
    encoding_mode: str = DEFAULT_ENCODING_MODE,
) -> dict[str, object]:
    if fps <= 0:
        raise ValueError("fps must be greater than 0")

    resolve_encoding_profile(encoding_mode)

    image_paths = collect_images(source_dir)
    first_valid_path, first_frame = load_first_valid_frame(image_paths)

    width, height = first_frame.size
    frame_size = (width, height)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    # Keep `.mp4` as the final suffix so ffmpeg can infer the output container.
    temp_output_file = output_file.with_name(f"{output_file.stem}.part{output_file.suffix}")
    if temp_output_file.exists():
        temp_output_file.unlink()

    ffmpeg_process = create_ffmpeg_process(
        temp_output_file,
        frame_size,
        fps,
        ffmpeg_path,
        encoding_mode,
    )
    if ffmpeg_process.stdin is None:
        raise RuntimeError("Failed to open ffmpeg stdin.")

    written = 0
    try:
        for image_path in image_paths:
            frame = read_image(image_path)
            if frame is None:
                print(f"[WARN] Skip unreadable image: {image_path}")
                continue

            if frame.size != frame_size:
                frame = frame.resize(frame_size, RESAMPLE_LANCZOS)
                print(f"[WARN] Resized frame to match video size: {image_path}")

            try:
                ffmpeg_process.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
            except OSError as exc:
                ffmpeg_process.stdin.close()
                stderr_output = ffmpeg_process.stderr.read().decode("utf-8", errors="replace")
                ffmpeg_process.wait()
                if temp_output_file.exists():
                    temp_output_file.unlink()
                raise RuntimeError(
                    f"Failed while writing frame `{image_path}` to ffmpeg: {exc}. "
                    f"ffmpeg stderr: {stderr_output.strip() or 'unknown error'}"
                ) from exc
            written += 1
    finally:
        ffmpeg_process.stdin.close()
        stderr_output = ffmpeg_process.stderr.read().decode("utf-8", errors="replace")
        return_code = ffmpeg_process.wait()

    if return_code != 0:
        if temp_output_file.exists():
            temp_output_file.unlink()
        raise RuntimeError(
            f"ffmpeg failed for {temp_output_file}: {stderr_output.strip() or 'unknown error'}"
        )

    if written == 0:
        if temp_output_file.exists():
            temp_output_file.unlink()
        raise RuntimeError("No frames were written to the video.")

    temp_output_file.replace(output_file)

    duration = written / fps
    print(f"Source directory: {source_dir}")
    print(f"Reference frame: {first_valid_path}")
    print(f"Output video: {output_file}")
    print(f"Frames written: {written}")
    print(f"FPS: {fps}")
    print(f"Estimated duration: {duration:.2f} seconds")

    return {
        "source_dir": source_dir,
        "output_file": output_file,
        "frames_written": written,
        "fps": fps,
        "duration": duration,
        "encoding_mode": encoding_mode,
    }


def compose_videos(
    source_root: Path,
    output_dir: Path,
    fps: float,
    ffmpeg_path: Path,
    *,
    encoding_mode: str = DEFAULT_ENCODING_MODE,
    max_workers: int = 0,
    keep_images: bool = False,
    resume: bool = False,
    resume_file: Path | None = None,
    reset_resume: bool = False,
) -> None:
    resolve_encoding_profile(encoding_mode)
    image_dirs = find_image_directories(source_root)
    succeeded: list[dict[str, object]] = []
    failed: list[tuple[Path, str]] = []
    cleanup_warnings: list[tuple[Path, str]] = []
    pending_jobs: list[BatchComposeJob] = []
    skipped = 0

    resume_path = (resume_file or default_resume_path(output_dir)).resolve()
    resume_state: dict[str, object] | None = None
    completed_keys: set[str] = set()

    if resume:
        if reset_resume and resume_path.exists():
            resume_path.unlink()
            print(f"[RESUME] Cleared previous resume state: {resume_path}")

        resume_state = load_resume_state(resume_path, source_root, output_dir, fps)
        completed = resume_state.get("completed", {})
        if isinstance(completed, dict):
            completed_keys = set(completed.keys())

        print(f"[RESUME] Enabled, state file: {resume_path}")
        print(f"[RESUME] Completed entries in state: {len(completed_keys)}")

    print(f"Discovered {len(image_dirs)} image directories under: {source_root}")

    for image_dir in image_dirs:
        relative_dir = image_dir.relative_to(source_root)
        relative_key = relative_dir.as_posix()
        output_file = output_dir / relative_dir.with_suffix(".mp4")
        partial_output_file = output_file.with_name(f"{output_file.stem}.part{output_file.suffix}")
        print(f"\n[INFO] Composing: {image_dir} -> {output_file}")

        if resume and output_file.exists() and output_file.is_file() and output_file.stat().st_size > 0:
            skipped += 1
            print(f"[RESUME] Output exists, skip by filename: {output_file}")
            if partial_output_file.exists():
                try:
                    partial_output_file.unlink()
                    print(f"[RESUME] Removed stale partial file: {partial_output_file}")
                except OSError as exc:
                    print(f"[WARN] Failed to remove stale partial file: {partial_output_file} ({exc})")
            if resume_state is not None:
                mark_resume_completed(
                    resume_state,
                    relative_key,
                    {
                        "output_file": output_file,
                        "frames_written": 0,
                        "fps": fps,
                        "duration": 0.0,
                    },
                )
                save_resume_state(resume_path, resume_state)
                completed_keys.add(relative_key)
            continue

        if resume and partial_output_file.exists():
            try:
                partial_output_file.unlink()
                print(f"[RESUME] Removed stale partial file before retry: {partial_output_file}")
            except OSError as exc:
                print(f"[WARN] Failed to remove partial file before retry: {partial_output_file} ({exc})")

        pending_jobs.append(
            BatchComposeJob(
                source_dir=image_dir,
                relative_key=relative_key,
                output_file=output_file,
            )
        )

    worker_count = resolve_batch_max_workers(max_workers, len(pending_jobs))
    total_jobs = len(pending_jobs)
    if total_jobs > 0:
        print(f"[INFO] Queued {total_jobs} jobs with {worker_count} worker(s).")
    else:
        print("[INFO] No pending jobs queued after resume filtering.")
    if keep_images:
        print("[INFO] Source image cleanup disabled by --keep-images.")

    processed_jobs = 0

    def handle_success(outcome: BatchComposeOutcome) -> None:
        succeeded.append(outcome.result)
        if resume and resume_state is not None:
            mark_resume_completed(resume_state, outcome.job.relative_key, outcome.result)
            save_resume_state(resume_path, resume_state)
            completed_keys.add(outcome.job.relative_key)
        if outcome.cleanup_warning is not None:
            cleanup_warnings.append((outcome.job.source_dir, outcome.cleanup_warning))

    def handle_failure(job: BatchComposeJob, exc: Exception) -> None:
        failed.append((job.source_dir, str(exc)))
        print(f"[ERROR] Failed to compose {job.source_dir}: {exc}")
        if resume and resume_state is not None:
            mark_resume_failed(resume_state, job.relative_key, str(exc))
            save_resume_state(resume_path, resume_state)

    if worker_count == 1:
        for job in pending_jobs:
            try:
                outcome = _compose_batch_job(job, fps, ffmpeg_path, encoding_mode, keep_images)
            except Exception as exc:  # pragma: no cover - CLI batch fallback
                handle_failure(job, exc)
            else:
                handle_success(outcome)
            processed_jobs += 1
            print(f"[INFO] Completed {processed_jobs}/{total_jobs} jobs.")
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_job = {
                executor.submit(_compose_batch_job, job, fps, ffmpeg_path, encoding_mode, keep_images): job
                for job in pending_jobs
            }
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    outcome = future.result()
                except Exception as exc:  # pragma: no cover - CLI batch fallback
                    handle_failure(job, exc)
                else:
                    handle_success(outcome)
                processed_jobs += 1
                print(f"[INFO] Completed {processed_jobs}/{total_jobs} jobs.")

    print("\nBatch summary")
    print(f"Successful videos: {len(succeeded)}")
    print(f"Failed videos: {len(failed)}")
    print(f"Skipped videos: {skipped}")
    print(f"Cleanup warnings: {len(cleanup_warnings)}")

    if failed:
        print("Failed directories:")
        for image_dir, error in failed:
            print(f"  - {image_dir}: {error}")

    if cleanup_warnings:
        print("Directories not cleaned up:")
        for image_dir, warning in cleanup_warnings:
            print(f"  - {image_dir}: {warning}")

    if not succeeded and skipped == 0:
        raise RuntimeError("No videos were generated successfully.")


def main() -> int:
    args = parse_args()

    if args.source_dir is not None:
        output_file = args.output_file or (args.output_dir / f"{args.source_dir.name}.mp4")
        partial_output_file = output_file.with_name(f"{output_file.stem}.part{output_file.suffix}")
        if args.resume and output_file.exists() and output_file.is_file() and output_file.stat().st_size > 0:
            print(f"[RESUME] Output exists, skip by filename: {output_file}")
            if partial_output_file.exists():
                try:
                    partial_output_file.unlink()
                    print(f"[RESUME] Removed stale partial file: {partial_output_file}")
                except OSError as exc:
                    print(f"[WARN] Failed to remove stale partial file: {partial_output_file} ({exc})")
            return 0
        if args.resume and partial_output_file.exists():
            try:
                partial_output_file.unlink()
                print(f"[RESUME] Removed stale partial file before retry: {partial_output_file}")
            except OSError as exc:
                print(f"[WARN] Failed to remove partial file before retry: {partial_output_file} ({exc})")
        compose_video(
            args.source_dir,
            output_file,
            args.fps,
            args.ffmpeg_path,
            args.encoding_mode,
        )
        if args.keep_images:
            print("[INFO] Source image cleanup disabled by --keep-images.")
        else:
            cleanup_source_image_directory(args.source_dir, output_file)
        return 0

    compose_videos(
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
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
