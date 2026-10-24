"""Administrator-to-worker bridge built on the existing persistent queue."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from .audit import AuditLog
from .messages import message, utc_timestamp
from .task_queue import PersistentQueue


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class AdministratorAdapter:
    """Thin submission/status facade over the Administrator's queue contract."""

    def __init__(self, administrator_root: Path | None, queue_dir: Path, audit_path: Path, *,
                 max_attempts: int = 3, lease_seconds: int = 900, retry_delay_seconds: int = 0):
        # administrator_root remains as a compatibility-only argument for older
        # callers.  GS-031 never imports code or data from that location.
        self.queue = PersistentQueue(
            queue_dir, _atomic_write, audit_path.parent / "worker_failures.jsonl",
            max_attempts=max_attempts, lease_seconds=lease_seconds,
            retry_delay_seconds=retry_delay_seconds,
        )
        self.audit = AuditLog(audit_path)

    def submit(self, payload: dict[str, Any], *, worker_id: str = "python-readonly-1",
               required_permissions: list[str] | None = None, task_id: str | None = None,
               correlation_id: str | None = None, approved: bool = False,
               approval_source: str | None = None,
               priority: int = 0,
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
            "approval": {"status": "approved" if approved else "pending",
                         "owner": approval_source or "Karl",
                         "method": "automatic" if approved and approval_source else "manual"},
            "execution_timeout_seconds": execution_timeout_seconds,
            "priority": int(priority),
            "payload": payload,
        }
        self.queue.create(task)
        self.audit.append(message("submission", task_id=task_id, correlation_id=correlation_id,
                                  sender="administrator", recipient="orchestrator", payload={"worker_id": worker_id}))
        return self.queue.read(task_id)

    def status(self, task_id: str) -> dict[str, Any]:
        return self.queue.read(task_id)

    def approve(self, task_id: str, *, owner: str) -> dict[str, Any]:
        if not owner.strip():
            raise ValueError("Approval requires an owner identity")
        task = self.queue.read(task_id)
        if task.get("status") != "queued" or task.get("approval", {}).get("status") != "pending":
            raise ValueError("Only queued tasks awaiting approval can be approved")
        return self.queue.transition(
            task, "queued", approval={"status": "approved", "owner": owner, "approved_at": utc_timestamp()}
        )


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
        envelope = json.dumps({"worker": worker.execution_request(), "task": task})
        command = [sys.executable, "-m", "ground_space.worker_process"]
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", cwd=Path(__file__).resolve().parents[1],
        )
        try:
            stdout, stderr = process.communicate(envelope, timeout=timeout)
            response = json.loads(stdout or "{}")
            if process.returncode != 0 or "error" in response:
                raise RuntimeError(response.get("error") or stderr.strip() or f"Worker exited {process.returncode}")
            worker_result = response["result"]
            for details in response.get("progress", []):
                progress(details)
            task = queue.read(task_id)
            result = queue.finish(task, "completed", result=worker_result,
                                  completed_by=worker.descriptor.agent_id)
            self._emit("completion", result, "administrator", {"worker_id": worker_id, "result": worker_result})
            return result
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.communicate()
            result = queue.record_failure(task_id, self.agent_id, error, retryable=True, stage="execution_timeout")
            self._emit("failure", result, "administrator", {"reason": "timeout", "worker_id": worker_id})
            return result
        except Exception as error:
            result = queue.record_failure(task_id, self.agent_id, error, retryable=True, stage="worker_execution")
            self._emit("failure", result, "administrator", {"reason": str(error), "worker_id": worker_id})
            return result

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
