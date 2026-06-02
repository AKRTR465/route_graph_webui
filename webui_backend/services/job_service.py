from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Mapping

from json_store import consume_jsonl_text, read_json_mapping_if_ready, write_json_atomic


JOB_STATE_RUNNING = "running"
JOB_STATE_SUCCEEDED = "succeeded"
JOB_STATE_FAILED = "failed"
JOB_STATE_CANCELLED = "cancelled"
JOB_STATE_TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class WorkerRuntime:
    runtime_dir: Path
    payload_path: Path
    progress_path: Path
    result_path: Path
    error_path: Path
    stderr_path: Path
    process: subprocess.Popen[Any]


@dataclass(slots=True)
class BackgroundJobRecord:
    job_id: int
    graph: str
    runtime_dir: Path
    payload_path: Path
    progress_path: Path
    result_path: Path
    error_path: Path
    stderr_path: Path
    process: subprocess.Popen[Any] | None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    state: str = JOB_STATE_RUNNING
    progress_offset: int = 0
    progress_buffer: str = ""
    progress: dict[str, Any] | None = None
    candidate_set: dict[str, Any] | None = None
    error: str | None = None
    post_exit_polls: int = 0


def datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds")


def serialize_job_status(record: BackgroundJobRecord) -> dict[str, Any]:
    return {
        "job_id": record.job_id,
        "graph": record.graph,
        "state": record.state,
        "progress": dict(record.progress) if record.progress is not None else None,
        "candidate_set": dict(record.candidate_set) if record.candidate_set is not None else None,
        "error": record.error,
        "started_at": datetime_to_iso(record.started_at),
        "updated_at": datetime_to_iso(record.updated_at),
        "finished_at": datetime_to_iso(record.finished_at),
    }


def launch_worker_runtime(
    *,
    job_id: int,
    task_payload: Mapping[str, Any],
    worker_path: Path,
    runtime_root: Path,
    runtime_prefix: str,
    cwd: Path,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    python_executable: str | None = None,
    creationflags: int = 0,
) -> WorkerRuntime:
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(tempfile.mkdtemp(prefix=runtime_prefix, dir=runtime_root))
    payload_path = runtime_dir / "payload.json"
    progress_path = runtime_dir / "progress.jsonl"
    result_path = runtime_dir / "result.json"
    error_path = runtime_dir / "error.json"
    stderr_path = runtime_dir / "stderr.log"

    try:
        write_json_atomic(
            payload_path,
            {
                **dict(task_payload),
                "job_id": int(job_id),
            },
            indent=None,
        )
        with stderr_path.open("w", encoding="utf-8") as stderr_handle:
            process = popen_factory(
                [
                    python_executable or sys.executable,
                    str(worker_path),
                    "--payload",
                    str(payload_path),
                    "--output-dir",
                    str(runtime_dir),
                ],
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                creationflags=creationflags,
            )
    except Exception:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        raise

    return WorkerRuntime(
        runtime_dir=runtime_dir,
        payload_path=payload_path,
        progress_path=progress_path,
        result_path=result_path,
        error_path=error_path,
        stderr_path=stderr_path,
        process=process,
    )


class BackgroundJobService:
    def __init__(
        self,
        *,
        worker_path: Path,
        runtime_root: Path,
        project_root: Path,
        runtime_prefix: str,
        retention_seconds: int,
        post_exit_poll_limit: int,
        timeout_seconds: int | None = None,
    ) -> None:
        self.worker_path = worker_path
        self.runtime_root = runtime_root
        self.project_root = project_root
        self.runtime_prefix = runtime_prefix
        self.retention_seconds = int(retention_seconds)
        self.post_exit_poll_limit = int(post_exit_poll_limit)
        self.timeout_seconds = timeout_seconds
        self.lock = threading.Lock()
        self.sequence = 0
        self.jobs: dict[int, BackgroundJobRecord] = {}

    def next_job_id(self) -> int:
        self.sequence += 1
        return self.sequence

    def cleanup_runtime(self, record: BackgroundJobRecord) -> None:
        shutil.rmtree(record.runtime_dir, ignore_errors=True)

    def discard_job(self, job_id: int, *, terminate: bool = False) -> None:
        with self.lock:
            record = self.jobs.pop(job_id, None)
            if record is None:
                return
            if terminate and record.state == JOB_STATE_RUNNING:
                self.cancel_job_locked(record)
        self.cleanup_runtime(record)

    def cleanup_orphaned_runtimes(self) -> None:
        if not self.runtime_root.exists():
            return
        for candidate in self.runtime_root.iterdir():
            if not candidate.is_dir() or not candidate.name.startswith(self.runtime_prefix):
                continue
            shutil.rmtree(candidate, ignore_errors=True)

    def create_worker_job(
        self,
        *,
        graph_ref: str,
        task_payload: Mapping[str, Any],
        popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        python_executable: str | None = None,
        creationflags: int = 0,
    ) -> BackgroundJobRecord:
        if not self.worker_path.exists():
            raise FileNotFoundError(f"Route generation worker was not found: {self.worker_path}")

        with self.lock:
            job_id = self.next_job_id()

        runtime = launch_worker_runtime(
            job_id=job_id,
            task_payload=task_payload,
            worker_path=self.worker_path,
            runtime_root=self.runtime_root,
            runtime_prefix=self.runtime_prefix,
            cwd=self.project_root,
            popen_factory=popen_factory,
            python_executable=python_executable,
            creationflags=creationflags,
        )
        now = datetime.now()
        record = BackgroundJobRecord(
            job_id=job_id,
            graph=graph_ref,
            runtime_dir=runtime.runtime_dir,
            payload_path=runtime.payload_path,
            progress_path=runtime.progress_path,
            result_path=runtime.result_path,
            error_path=runtime.error_path,
            stderr_path=runtime.stderr_path,
            process=runtime.process,
            started_at=now,
            updated_at=now,
        )
        with self.lock:
            self.jobs[job_id] = record
        return record

    def finish_job(
        self,
        record: BackgroundJobRecord,
        *,
        state: str,
        candidate_set: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        finished_at = datetime.now()
        record.state = state
        record.updated_at = finished_at
        record.finished_at = finished_at
        record.candidate_set = candidate_set
        record.error = error
        record.process = None

    def read_stderr_summary(self, record: BackgroundJobRecord) -> str:
        try:
            stderr_lines = [
                line.strip()
                for line in record.stderr_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            return ""
        return " | ".join(stderr_lines[-3:])

    def update_job_locked(
        self,
        record: BackgroundJobRecord,
        *,
        resolve_candidate_set: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        if record.state != JOB_STATE_RUNNING:
            return

        now = datetime.now()
        if self.timeout_seconds is not None and (now - record.started_at).total_seconds() >= self.timeout_seconds:
            self.cancel_job_locked(record, state=JOB_STATE_TIMED_OUT, error="后台任务超时")
            return

        if record.progress_path.exists():
            with record.progress_path.open("r", encoding="utf-8") as handle:
                handle.seek(record.progress_offset)
                new_data = handle.read()
                record.progress_offset = handle.tell()
            if new_data:
                messages, record.progress_buffer = consume_jsonl_text(record.progress_buffer, new_data)
                for message in messages:
                    if int(message.get("job_id", -1)) != record.job_id:
                        continue
                    if message.get("type") == "progress" and isinstance(message.get("progress"), dict):
                        record.progress = dict(message["progress"])
                        record.updated_at = now

        if record.result_path.exists():
            message = read_json_mapping_if_ready(record.result_path)
            if message is not None and int(message.get("job_id", -1)) == record.job_id:
                candidate_payload = message.get("candidate_set")
                if not isinstance(candidate_payload, dict):
                    self.finish_job(record, state=JOB_STATE_FAILED, error="后台任务返回了无效的候选结果")
                    return
                self.finish_job(
                    record,
                    state=JOB_STATE_SUCCEEDED,
                    candidate_set=resolve_candidate_set(candidate_payload),
                )
                return

        if record.error_path.exists():
            message = read_json_mapping_if_ready(record.error_path)
            if message is not None and int(message.get("job_id", -1)) == record.job_id:
                self.finish_job(
                    record,
                    state=JOB_STATE_FAILED,
                    error=str(message.get("error", "后台进程执行失败")),
                )
                return

        if record.process is not None and record.process.poll() is not None:
            record.post_exit_polls += 1
            if record.post_exit_polls >= self.post_exit_poll_limit:
                exit_code = record.process.poll()
                stderr_text = self.read_stderr_summary(record)
                error_message = f"后台进程已退出，未返回结果。exitcode={exit_code}"
                if stderr_text:
                    error_message = f"{error_message} stderr={stderr_text}"
                self.finish_job(record, state=JOB_STATE_FAILED, error=error_message)
        else:
            record.post_exit_polls = 0

    def cancel_job_locked(
        self,
        record: BackgroundJobRecord,
        *,
        state: str = JOB_STATE_CANCELLED,
        error: str = "后台任务已取消",
    ) -> None:
        process = record.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
            except Exception:
                pass
        self.finish_job(record, state=state, error=error)

    def cleanup_expired_jobs(
        self,
        *,
        resolve_candidate_set: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        expired_records: list[BackgroundJobRecord] = []
        now = datetime.now()
        with self.lock:
            for job_id, record in list(self.jobs.items()):
                self.update_job_locked(record, resolve_candidate_set=resolve_candidate_set)
                if (
                    record.finished_at is not None
                    and (now - record.finished_at).total_seconds() >= self.retention_seconds
                ):
                    expired_records.append(self.jobs.pop(job_id))
        for record in expired_records:
            self.cleanup_runtime(record)

    def get_job_status(
        self,
        job_id: int,
        *,
        resolve_candidate_set: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, BackgroundJobRecord | None]:
        expired_record: BackgroundJobRecord | None = None
        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                return None, None
            self.update_job_locked(record, resolve_candidate_set=resolve_candidate_set)
            if (
                record.finished_at is not None
                and (datetime.now() - record.finished_at).total_seconds() >= self.retention_seconds
            ):
                expired_record = self.jobs.pop(job_id)
            else:
                return serialize_job_status(record), None
        return None, expired_record

    def cancel_job(
        self,
        job_id: int,
        *,
        resolve_candidate_set: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, BackgroundJobRecord | None]:
        expired_record: BackgroundJobRecord | None = None
        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                return None, None
            self.update_job_locked(record, resolve_candidate_set=resolve_candidate_set)
            if record.state == JOB_STATE_RUNNING:
                self.cancel_job_locked(record)
            if (
                record.finished_at is not None
                and (datetime.now() - record.finished_at).total_seconds() >= self.retention_seconds
            ):
                expired_record = self.jobs.pop(job_id)
            else:
                return serialize_job_status(record), None
        return None, expired_record


__all__ = [
    "BackgroundJobRecord",
    "BackgroundJobService",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_FAILED",
    "JOB_STATE_RUNNING",
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_TIMED_OUT",
    "WorkerRuntime",
    "datetime_to_iso",
    "launch_worker_runtime",
    "serialize_job_status",
]
