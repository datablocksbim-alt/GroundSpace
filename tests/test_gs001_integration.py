from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ground_space.bridge import AdministratorAdapter, OrchestratorAdapter
from ground_space.workers import DeterministicReadOnlyWorker, WorkerDescriptor


ADMIN_ROOT = Path(r"D:\000_AI Project\AI Agents Datablocks")


class SlowWorker:
    descriptor = WorkerDescriptor("slow", "test", frozenset({"read"}))

    def execute(self, task, progress):
        time.sleep(0.2)
        return {"late": True}


class GS001IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.admin = AdministratorAdapter(ADMIN_ROOT, root / "queue", root / "audit" / "messages.jsonl",
                                          max_attempts=3, retry_delay_seconds=0)
        self.orchestrator = OrchestratorAdapter(self.admin)
        self.orchestrator.register(DeterministicReadOnlyWorker())

    def tearDown(self):
        self.temporary.cleanup()

    def test_three_successful_round_trips_and_duplicate_idempotency(self):
        for number in range(3):
            task = self.admin.submit({"sequence": number, "text": "inspect only"}, task_id=f"GS-001-{number}")
            result = self.orchestrator.process(task["task_id"])
            self.assertEqual("completed", result["status"])
            self.assertTrue(result["result"]["read_only"])
            self.assertEqual(result, self.orchestrator.process(task["task_id"]))
        records = self.admin.audit.records()
        self.assertEqual(3, sum(item.get("message_type") == "submission" for item in records))
        self.assertEqual(3, sum(item.get("message_type") == "completion" for item in records))
        self.assertEqual(3, sum(item.get("event") == "duplicate_ignored" for item in records))

    def test_unavailable_worker_retries(self):
        task = self.admin.submit({}, worker_id="offline", task_id="GS-OFFLINE")
        result = self.orchestrator.process(task["task_id"])
        self.assertEqual("retry_pending", result["status"])
        self.assertEqual(1, result["attempt_count"])

    def test_timeout_retries(self):
        self.orchestrator.register(SlowWorker())
        task = self.admin.submit({}, worker_id="slow", task_id="GS-TIMEOUT", execution_timeout_seconds=0.01)
        result = self.orchestrator.process(task["task_id"])
        self.assertEqual("retry_pending", result["status"])
        self.assertEqual("execution_timeout", result["failed_stage"])

    def test_permission_boundary_is_terminal(self):
        task = self.admin.submit({}, required_permissions=["write"], task_id="GS-DENIED")
        result = self.orchestrator.process(task["task_id"])
        self.assertEqual("failed", result["status"])
        self.assertEqual("authorization", result["failed_stage"])

    def test_pending_approval_is_not_claimed(self):
        task = self.admin.submit({}, approved=False, task_id="GS-PENDING")
        result = self.orchestrator.process(task["task_id"])
        self.assertEqual("queued", result["status"])
        self.assertEqual(0, result["attempt_count"])

    def test_audit_messages_have_required_identity_fields(self):
        task = self.admin.submit({"value": 1}, task_id="GS-AUDIT")
        self.orchestrator.process(task["task_id"])
        for record in self.admin.audit.records():
            if "message_type" in record:
                self.assertTrue({"message_id", "task_id", "correlation_id", "timestamp", "sender", "recipient"} <= record.keys())


if __name__ == "__main__":
    unittest.main()
