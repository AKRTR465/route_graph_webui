from __future__ import annotations

import argparse
import json
import math
import os
import sys
import unicodedata
from pathlib import Path
from typing import Iterable


DEFAULT_MISSIONS_DIR = Path(__file__).resolve().parent / "data" / "missions"


def configure_utf8_output() -> None:
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleCP(65001)
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def percentile_linear(sorted_values: list[int], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute percentiles for an empty value list")
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = (len(sorted_values) - 1) * float(percentile)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return float(sorted_values[lower_index])

    fraction = position - lower_index
    lower_value = float(sorted_values[lower_index])
    upper_value = float(sorted_values[upper_index])
    return lower_value + ((upper_value - lower_value) * fraction)


def resolve_mission_files(path: Path, *, recursive: bool) -> list[Path]:
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")
    if resolved.is_file():
        if resolved.suffix.lower() != ".json":
            raise ValueError(f"Expected a JSON file: {resolved}")
        return [resolved]

    pattern_iter: Iterable[Path]
    if recursive:
        pattern_iter = resolved.rglob("*.json")
    else:
        pattern_iter = resolved.glob("*.json")
    return sorted(file_path for file_path in pattern_iter if file_path.is_file())


def count_mission_frames(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    positions = payload.get("positions", [])
    if not isinstance(positions, list):
        raise ValueError(f"Mission `positions` must be a list: {path}")
    return len(positions)


def summarize_frame_counts(frame_counts: list[int]) -> dict[str, float | int]:
    if not frame_counts:
        raise ValueError("No mission JSON files were found")

    sorted_counts = sorted(frame_counts)
    total_frames = sum(sorted_counts)
    return {
        "file_count": len(sorted_counts),
        "total_frames": total_frames,
        "mean_frames": total_frames / len(sorted_counts),
        "p10_frames": percentile_linear(sorted_counts, 0.10),
        "p90_frames": percentile_linear(sorted_counts, 0.90),
        "min_frames": sorted_counts[0],
        "max_frames": sorted_counts[-1],
    }


def summarize_mission_path(path: Path, *, recursive: bool) -> dict[str, float | int]:
    mission_files = resolve_mission_files(path, recursive=recursive)
    frame_counts = [count_mission_frames(file_path) for file_path in mission_files]
    return summarize_frame_counts(frame_counts)


def display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in {"F", "W"}:
            width += 2
        else:
            width += 1
    return width


def pad_text(text: str, target_width: int) -> str:
    missing = max(0, target_width - display_width(text))
    return f"{text}{' ' * missing}"


def print_boxed_table(title: str, headers: list[str], rows: list[tuple[str, ...]]) -> None:
    column_widths = [
        max(display_width(header), *(display_width(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    inner_width = sum(column_widths) + (3 * (len(headers) - 1))
    table_width = inner_width + 4

    print("┌" + ("─" * (table_width - 2)) + "┐")
    print(f"│ {pad_text(title, table_width - 4)} │")
    print(
        "├"
        + "┬".join("─" * (width + 2) for width in column_widths)
        + "┤"
    )
    print(
        "│ "
        + " │ ".join(pad_text(header, width) for header, width in zip(headers, column_widths, strict=True))
        + " │"
    )
    print(
        "├"
        + "┼".join("─" * (width + 2) for width in column_widths)
        + "┤"
    )
    for row in rows:
        print(
            "│ "
            + " │ ".join(pad_text(value, width) for value, width in zip(row, column_widths, strict=True))
            + " │"
        )
    print(
        "└"
        + "┴".join("─" * (width + 2) for width in column_widths)
        + "┘"
    )


def collect_child_directory_summaries(target_path: Path) -> list[tuple[str, dict[str, float | int]]]:
    summaries: list[tuple[str, dict[str, float | int]]] = []
    for child in sorted(path for path in target_path.iterdir() if path.is_dir()):
        try:
            summary = summarize_mission_path(child, recursive=True)
        except ValueError:
            continue
        summaries.append((child.name, summary))
    return summaries


def _format_summary_row(label: str, summary: dict[str, float | int]) -> tuple[str, ...]:
    return (
        label,
        str(summary["file_count"]),
        str(summary["total_frames"]),
        f"{summary['mean_frames']:.2f}",
        f"{summary['p10_frames']:.2f}",
        f"{summary['p90_frames']:.2f}",
        str(summary["min_frames"]),
        str(summary["max_frames"]),
    )


def print_summary_table(
    target_path: Path,
    summary: dict[str, float | int],
    *,
    recursive: bool,
) -> None:
    resolved_target_path = target_path.resolve()
    child_summaries = (
        collect_child_directory_summaries(resolved_target_path)
        if resolved_target_path.is_dir() and recursive
        else []
    )

    rows: list[tuple[str, ...]]
    if child_summaries:
        rows = [_format_summary_row(folder_name, item_summary) for folder_name, item_summary in child_summaries]
        rows.append(_format_summary_row("总计", summary))
    else:
        label = resolved_target_path.stem if resolved_target_path.is_file() else resolved_target_path.name
        rows = [_format_summary_row(label or "总计", summary)]

    print_boxed_table(
        "分场景统计",
        ["文件夹", "文件数", "总帧数", "平均帧数", "10 分位", "90 分位", "最小", "最大"],
        rows,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute frame-count statistics for mission JSON files.")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_MISSIONS_DIR),
        help="Mission JSON file or directory. Defaults to data/missions.",
    )
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Only scan JSON files directly inside the target directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the statistics as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    target_path = Path(args.path)
    try:
        summary = summarize_mission_path(target_path, recursive=not args.non_recursive)
    except Exception as exc:
        print(exc)
        return 1

    if args.json:
        child_summaries = []
        resolved_target_path = target_path.resolve()
        if resolved_target_path.is_dir() and not args.non_recursive:
            child_summaries = [
                {
                    "folder": folder_name,
                    **folder_summary,
                }
                for folder_name, folder_summary in collect_child_directory_summaries(resolved_target_path)
            ]
        print(
            json.dumps(
                {
                    "path": str(resolved_target_path),
                    **summary,
                    "children": child_summaries,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print_summary_table(target_path, summary, recursive=not args.non_recursive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
