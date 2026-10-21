from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ground_space.bridge import AdministratorAdapter, OrchestratorAdapter
from ground_space.workers import OllamaProposalWorker


ADMIN_ROOT = Path(r"D:\000_AI Project\AI Agents Datablocks")


class GS002SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.admin = AdministratorAdapter(ADMIN_ROOT, root / "queue", root / "audit.jsonl", retry_delay_seconds=0)
        self.orchestrator = OrchestratorAdapter(self.admin)

    def tearDown(self):
        self.temporary.cleanup()

    def test_user_task_requires_explicit_approval(self):
        task = self.admin.submit(
            {"request_type": "explanation", "prompt": "Explain a queue."},
            worker_id="qwen-proposal", required_permissions=["read", "propose"], task_id="GS2-PENDING",
        )
        self.assertEqual("pending", task["approval"]["status"])
        self.assertEqual("queued", self.orchestrator.process(task["task_id"])["status"])
        approved = self.admin.approve(task["task_id"], owner="Karl")
        self.assertEqual("approved", approved["approval"]["status"])

    def test_offline_ollama_is_reported_as_retryable_failure(self):
        self.orchestrator.register(OllamaProposalWorker(endpoint="http://127.0.0.1:1", request_timeout_seconds=0.2))
        task = self.admin.submit(
            {"request_type": "assessment", "prompt": "Assess this safely."},
            worker_id="qwen-proposal", required_permissions=["read", "propose"], task_id="GS2-OFFLINE",
        )
        self.admin.approve(task["task_id"], owner="Karl")
        result = self.orchestrator.process(task["task_id"])
        self.assertEqual("retry_pending", result["status"])
        self.assertEqual("worker_execution", result["failed_stage"])

    def test_qwen_cannot_accept_write_permission(self):
        self.orchestrator.register(OllamaProposalWorker())
        task = self.admin.submit(
            {"request_type": "code_proposal", "prompt": "Propose a harmless function."},
            worker_id="qwen-proposal", required_permissions=["write"], task_id="GS2-WRITE-DENIED",
        )
        self.admin.approve(task["task_id"], owner="Karl")
        result = self.orchestrator.process(task["task_id"])
        self.assertEqual("failed", result["status"])
        self.assertEqual("authorization", result["failed_stage"])


if __name__ == "__main__":
    unittest.main()
