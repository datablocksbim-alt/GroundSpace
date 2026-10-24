"""Self-contained persistent queue for a single-owner Ground Space installation.

The JSON record and method contract intentionally match the Administrator queue
used through GS-030 so existing private queue files remain readable.  Claim
files provide cross-process duplicate-execution protection; task files remain
the durable source of truth and are replaced atomically by the caller-supplied
writer.
"""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

FINAL_STATES = frozenset({
    "sandbox_passed", "sandbox_failed", "completed", "blocked",
    "rolled_back", "failed", "cancelled",
})
CLAIMABLE_STATES = frozenset({"queued", "retry_pending"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


class PersistentQueue:
    """Filesystem queue compatible with existing Ground Space task records."""

    def __init__(self, queue_dir: Path, atomic_writer: Callable[[Path, bytes], None],
                 failure_log: Path, max_attempts: int = 3, lease_seconds: int = 900,
                 retry_delay_seconds: int = 60):
        self.queue_dir = Path(queue_dir)
        self.claim_dir = self.queue_dir / ".claims"
        self.atomic_write = atomic_writer
        self.failure_log = Path(failure_log)
        self.max_attempts = max(1, int(max_attempts))
        self.lease_seconds = max(30, int(lease_seconds))
        self.retry_delay_seconds = max(0, int(retry_delay_seconds))

    def task_path(self, task_id: str) -> Path:
        if not task_id or any(c not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_" for c in task_id):
            raise ValueError("Invalid task identifier")
        return self.queue_dir / f"{task_id}.json"

    def claim_path(self, task_id: str) -> Path:
        return self.claim_dir / f"{task_id}.claim"

    def read(self, task_id: str) -> dict[str, Any]:
        value = json.loads(self.task_path(task_id).read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("task_id") != task_id:
            raise ValueError("Task record does not match its identifier")
        return value

    def write(self, task: dict[str, Any]) -> None:
        task["updated_at"] = timestamp()
        self.atomic_write(self.task_path(str(task["task_id"])), json.dumps(task, indent=2).encode())

    def transition(self, task: dict[str, Any], status: str, **details: object) -> dict[str, Any]:
        event = {"at": timestamp(), "from": task.get("status"), "to": status}
        task.setdefault("history", []).append(event)
        task.update(details)
        task["status"] = status
        self.write(task)
        return task

    def create(self, task: dict[str, Any]) -> None:
        path = self.task_path(str(task.get("task_id", "")))
        if path.exists():
            raise FileExistsError(f"Task already exists: {task.get('task_id')}")
        task.setdefault("attempt_count", 0)
        task.setdefault("max_attempts", self.max_attempts)
        task.setdefault("priority", 0)
        task.setdefault("history", [{"at": task.get("created_at", timestamp()), "from": None, "to": "queued"}])
        task["updated_at"] = task.get("created_at", timestamp())
        self.atomic_write(path, json.dumps(task, indent=2).encode())

    def _exclusive_claim_file(self, task_id: str, worker_id: str) -> bool:
        self.claim_dir.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            descriptor = os.open(self.claim_path(task_id), flags, 0o600)
        except FileExistsError:
            return False
        try:
            os.write(descriptor, json.dumps({"task_id": task_id, "worker_id": worker_id,
                                             "claimed_at": timestamp()}, sort_keys=True).encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return True

    def claim(self, task_id: str, worker_id: str) -> dict[str, Any] | None:
        if not self._exclusive_claim_file(task_id, worker_id):
            return None
        try:
            task = self.read(task_id)
            if (task.get("status") not in CLAIMABLE_STATES or
                    (task.get("approval") or {}).get("status") != "approved"):
                return None
            retry_at = parse_timestamp(task.get("retry_after"))
            if retry_at and retry_at > utc_now():
                return None
            attempts = int(task.get("attempt_count", 0))
            limit = int(task.get("max_attempts", self.max_attempts))
            if attempts >= limit:
                self.transition(task, "failed", failure="Retry budget exhausted")
                return None
            claimed_at = timestamp()
            return self.transition(
                task, "claimed", claimed_by=worker_id, claimed_at=claimed_at,
                heartbeat_at=claimed_at, lease_id=uuid4().hex,
                attempt_count=attempts + 1, retry_after=None,
            )
        finally:
            try:
                current = self.read(task_id)
                if current.get("status") != "claimed" or current.get("claimed_by") != worker_id:
                    self.claim_path(task_id).unlink(missing_ok=True)
            except (OSError, ValueError, json.JSONDecodeError):
                self.claim_path(task_id).unlink(missing_ok=True)

    @staticmethod
    def _order(path: Path, task: dict[str, Any]) -> tuple[int, str, int, str]:
        try:
            priority = int(task.get("priority", 0))
        except (TypeError, ValueError):
            priority = 0
        created = task.get("created_at") if isinstance(task.get("created_at"), str) else ""
        return (-priority, created, path.stat().st_mtime_ns, path.name)

    def claim_next(self, worker_id: str) -> dict[str, Any] | None:
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        candidates: list[tuple[Path, dict[str, Any]]] = []
        for path in self.queue_dir.glob("*.json"):
            try:
                task = self.read(path.stem)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if (task.get("status") in CLAIMABLE_STATES and
                    (task.get("approval") or {}).get("status") == "approved"):
                candidates.append((path, task))
        for path, _ in sorted(candidates, key=lambda item: self._order(*item)):
            claimed = self.claim(path.stem, worker_id)
            if claimed is not None:
                return claimed
        return None

    def heartbeat(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task = self.read(task_id)
        if task.get("status") not in {"claimed", "running"} or task.get("claimed_by") != worker_id:
            raise ValueError("Worker does not own this task")
        task["heartbeat_at"] = timestamp()
        self.write(task)
        return task

    def start(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task = self.read(task_id)
        if task.get("status") != "claimed" or task.get("claimed_by") != worker_id:
            raise ValueError("Worker does not own this task")
        return self.transition(task, "running", started_at=timestamp(), heartbeat_at=timestamp())

    def finish(self, task: dict[str, Any], status: str, **details: object) -> dict[str, Any]:
        if status not in FINAL_STATES:
            raise ValueError("Finish requires a terminal task status")
        result = self.transition(task, status, finished_at=timestamp(), **details)
        self.claim_path(str(task["task_id"])).unlink(missing_ok=True)
        return result

    def _record_failure_event(self, event: dict[str, Any]) -> None:
        self.failure_log.parent.mkdir(parents=True, exist_ok=True)
        with self.failure_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def record_failure(self, task_id: str, worker_id: str | None, error: BaseException,
                       retryable: bool = True, stage: str = "processing") -> dict[str, Any]:
        task = self.read(task_id)
        if task.get("claimed_by") != worker_id:
            raise ValueError("Worker does not own this task")
        message = f"{type(error).__name__}: {error}"[:2000]
        self._record_failure_event({
            "at": timestamp(), "task_id": task_id, "worker_id": worker_id,
            "attempt": int(task.get("attempt_count", 0)), "stage": stage,
            "error_type": type(error).__name__, "message": str(error)[:1800],
        })
        limit = int(task.get("max_attempts", self.max_attempts))
        if retryable and int(task.get("attempt_count", 0)) < limit:
            result = self.transition(
                task, "retry_pending", failure=message, failed_stage=stage,
                retry_after=timestamp(utc_now() + timedelta(seconds=self.retry_delay_seconds)),
                claimed_by=None, claimed_at=None, heartbeat_at=None, lease_id=None,
            )
        else:
            result = self.transition(task, "failed", failure=message, failed_stage=stage,
                                     finished_at=timestamp(), lease_id=None)
        self.claim_path(task_id).unlink(missing_ok=True)
        return result

    def recover_stale(self, reference: datetime | None = None) -> list[dict[str, Any]]:
        current = reference or utc_now()
        recovered: list[dict[str, Any]] = []
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.queue_dir.glob("*.json")):
            try:
                task = self.read(path.stem)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if task.get("status") not in {"claimed", "running"}:
                continue
            heartbeat = parse_timestamp(task.get("heartbeat_at") or task.get("claimed_at"))
            started = parse_timestamp(task.get("started_at"))
            timeout = max(0, int(task.get("execution_timeout_seconds", 0) or 0))
            timed_out = bool(started and timeout and (current - started).total_seconds() > timeout)
            if not timed_out and heartbeat and (current - heartbeat).total_seconds() <= self.lease_seconds:
                continue
            result = self.record_failure(
                path.stem, task.get("claimed_by"),
                RuntimeError("Worker execution timeout expired" if timed_out else "Worker lease expired"),
                retryable=True, stage="execution_timeout" if timed_out else "recovery",
            )
            recovered.append(result)
        if self.claim_dir.exists():
            for claim in self.claim_dir.glob("*.claim"):
                if not self.task_path(claim.stem).exists():
                    claim.unlink(missing_ok=True)
        return recovered

    def recover_interrupted(self) -> list[dict[str, Any]]:
        """Recover leases left by a previous Ground Space process at startup."""
        recovered: list[dict[str, Any]] = []
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.queue_dir.glob("*.json")):
            try:
                task = self.read(path.stem)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if task.get("status") in {"claimed", "running"}:
                recovered.append(self.record_failure(
                    path.stem, task.get("claimed_by"),
                    RuntimeError("Ground Space restarted during task execution"),
                    retryable=True, stage="startup_recovery",
                ))
        return recovered
