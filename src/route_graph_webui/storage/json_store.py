from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping


def read_json(path: str | Path) -> Any:
    with Path(path).resolve().open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json_mapping_if_ready(path: str | Path) -> dict[str, Any] | None:
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json_atomic(
    path: str | Path,
    payload: Any,
    *,
    indent: int | None = 2,
) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=indent, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise
    return target


def append_jsonl(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), ensure_ascii=False))
        handle.write("\n")
    return target


def consume_jsonl_text(
    buffer: str,
    new_data: str,
) -> tuple[list[dict[str, Any]], str]:
    combined = f"{buffer}{new_data}"
    if not combined:
        return [], ""
    complete_lines, separator, remainder = combined.rpartition("\n")
    if not separator:
        return [], combined

    messages: list[dict[str, Any]] = []
    for raw_line in complete_lines.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            messages.append(payload)
    return messages, remainder


__all__ = [
    "append_jsonl",
    "consume_jsonl_text",
    "read_json",
    "read_json_mapping_if_ready",
    "write_json_atomic",
]
