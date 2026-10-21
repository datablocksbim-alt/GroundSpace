"""Administrator-to-worker bridge built on the existing persistent queue."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as WorkerTimeout
from pathlib import Path
from typing import Any
from uuid import uuid4

from .audit import AuditLog
from .legacy import load_task_queue
from .messages import message, utc_timestamp


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


class AdministratorAdapter:
    """Thin submission/status facade over the Administrator's queue contract."""

    def __init__(self, administrator_root: Path, queue_dir: Path, audit_path: Path, *,
                 max_attempts: int = 3, lease_seconds: int = 900, retry_delay_seconds: int = 0):
        queue_module = load_task_queue(administrator_root)
        self.queue = queue_module.PersistentQueue(
            queue_dir, _atomic_write, audit_path.parent / "worker_failures.jsonl",
            max_attempts=max_attempts, lease_seconds=lease_seconds,
            retry_delay_seconds=retry_delay_seconds,
        )
        self.audit = AuditLog(audit_path)

    def submit(self, payload: dict[str, Any], *, worker_id: str = "python-readonly-1",
               required_permissions: list[str] | None = None, task_id: str | None = None,
               correlation_id: str | None = None, approved: bool = True,
               execution_timeout_seconds: float = 5.0) -> dict[str, Any]:
        task_id = task_id or f"GS-{uuid4().hex}"
        correlation_id = correlation_id or uuid4().hex
        task = {
            "schema_version": 1,
            "task_id": task_id,
            "correlation_id": correlation_id,
            "created_at": utc_timestamp(),
            "status": "queued",
            "source": "ground_space",
            "requested_worker": worker_id,
            "required_permissions": required_permissions or ["read"],
            "approval": {"status": "approved" if approved else "pending", "owner": "Karl"},
            "execution_timeout_seconds": execution_timeout_seconds,
            "payload": payload,
        }
        self.queue.create(task)
        self.audit.append(message("submission", task_id=task_id, correlation_id=correlation_id,
                                  sender="administrator", recipient="orchestrator", payload={"worker_id": worker_id}))
        return self.queue.read(task_id)

    def status(self, task_id: str) -> dict[str, Any]:
        return self.queue.read(task_id)


class OrchestratorAdapter:
    def __init__(self, administrator: AdministratorAdapter, *, agent_id: str = "ground-space-orchestrator"):
        self.administrator = administrator
        self.agent_id = agent_id
        self.workers: dict[str, Any] = {}

    def register(self, worker: Any) -> None:
        self.workers[worker.descriptor.agent_id] = worker

    def _emit(self, event_type: str, task: dict[str, Any], recipient: str, payload: dict[str, Any]) -> None:
        self.administrator.audit.append(message(
            event_type, task_id=str(task["task_id"]), correlation_id=str(task["correlation_id"]),
            sender=self.agent_id, recipient=recipient, payload=payload,
        ))

    def process(self, task_id: str) -> dict[str, Any]:
        queue = self.administrator.queue
        current = queue.read(task_id)
        if current.get("status") in {"completed", "failed", "blocked", "cancelled"}:
            self.administrator.audit.append({
                "schema_version": 1, "event": "duplicate_ignored", "task_id": task_id,
                "correlation_id": current.get("correlation_id"), "timestamp": utc_timestamp(),
                "agent_id": self.agent_id,
            })
            return current
        if current.get("approval", {}).get("status") != "approved":
            self._emit("failure", current, "administrator", {"reason": "approval_required"})
            return current

        task = queue.claim(task_id, self.agent_id)
        if task is None:
            return queue.read(task_id)
        self._emit("acknowledgement", task, "administrator", {"status": "claimed"})
        worker_id = str(task.get("requested_worker", ""))
        worker = self.workers.get(worker_id)
        if worker is None or not worker.descriptor.active:
            result = queue.record_failure(task_id, self.agent_id, RuntimeError("Requested worker unavailable"),
                                          retryable=True, stage="dispatch")
            self._emit("failure", result, "administrator", {"reason": "worker_unavailable", "worker_id": worker_id})
            return result

        required = set(task.get("required_permissions", []))
        if required - worker.descriptor.permissions:
            result = queue.record_failure(task_id, self.agent_id, PermissionError("Worker permission boundary denied task"),
                                          retryable=False, stage="authorization")
            self._emit("failure", result, "administrator", {"reason": "permission_denied", "worker_id": worker_id})
            return result

        task = queue.start(task_id, self.agent_id)
        self._emit("progress", task, "administrator", {"stage": "assigned", "worker_id": worker_id})

        def progress(details: dict[str, Any]) -> None:
            queue.heartbeat(task_id, self.agent_id)
            self._emit("progress", queue.read(task_id), "administrator", {"worker_id": worker_id, **details})

        timeout = float(task.get("execution_timeout_seconds", 5.0))
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(worker.execute, task, progress)
        try:
            worker_result = future.result(timeout=timeout)
            task = queue.read(task_id)
            result = queue.finish(task, "completed", result=worker_result,
                                  completed_by=worker.descriptor.agent_id)
            self._emit("completion", result, "administrator", {"worker_id": worker_id, "result": worker_result})
            return result
        except WorkerTimeout as error:
            future.cancel()
            result = queue.record_failure(task_id, self.agent_id, error, retryable=True, stage="execution_timeout")
            self._emit("failure", result, "administrator", {"reason": "timeout", "worker_id": worker_id})
            return result
        except Exception as error:
            result = queue.record_failure(task_id, self.agent_id, error, retryable=True, stage="worker_execution")
            self._emit("failure", result, "administrator", {"reason": str(error), "worker_id": worker_id})
            return result
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def availability(self) -> list[dict[str, Any]]:
        return [
            {
                "agent_id": worker.descriptor.agent_id,
                "role": worker.descriptor.role,
                "active": worker.descriptor.active,
                "permissions": sorted(worker.descriptor.permissions),
                "provider": worker.descriptor.provider,
                "model": worker.descriptor.model,
                "qualified": worker.descriptor.qualified,
            }
            for worker in self.workers.values()
        ]
