"""GS-031 standalone queue contract, compatibility, and portability tests."""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ground_space.bridge import AdministratorAdapter, _atomic_write
from ground_space.config import default_state_dir, executable_inventory, ollama_endpoint
from ground_space.task_queue import PersistentQueue, timestamp


def record(task_id: str, *, approval: str = "approved", priority: int = 0,
           created_at: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "schema_version": 1, "task_id": task_id, "correlation_id": "corr-" + task_id,
        "created_at": created_at, "status": "queued", "source": "ground_space",
        "requested_worker": "python-readonly-1", "required_permissions": ["read"],
        "approval": {"status": approval, "owner": "test"}, "priority": priority,
        "execution_timeout_seconds": 5, "payload": {"value": task_id},
    }


def queue(queue_class, root: Path, **options):
    return queue_class(root / "queue", _atomic_write, root / "failures.jsonl",
                       retry_delay_seconds=0, **options)


def stable(task: dict) -> dict:
    volatile = {"updated_at", "claimed_at", "heartbeat_at", "started_at",
                "finished_at", "lease_id", "retry_after", "history"}
    return {key: value for key, value in task.items() if key not in volatile}


class StandaloneQueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_adapter_never_needs_external_administrator_tree(self):
        adapter = AdministratorAdapter(
            self.root / "does-not-exist", self.root / "queue", self.root / "audit" / "messages.jsonl"
        )
        item = adapter.submit({"safe": True}, approved=True, task_id="GS-STANDALONE")
        self.assertEqual("queued", item["status"])
        self.assertEqual(0, item["priority"])

    def test_existing_gs030_record_is_read_without_migration(self):
        queue_dir = self.root / "queue"
        queue_dir.mkdir()
        legacy = record("GS-LEGACY")
        legacy.pop("priority")
        (queue_dir / "GS-LEGACY.json").write_text(json.dumps(legacy), encoding="utf-8")
        item = queue(PersistentQueue, self.root).read("GS-LEGACY")
        self.assertEqual(legacy, item)
        self.assertEqual("claimed", queue(PersistentQueue, self.root).claim("GS-LEGACY", "worker")["status"])

    def test_priority_then_fifo_ordering(self):
        work = queue(PersistentQueue, self.root)
        work.create(record("GS-LOW", priority=1, created_at="2026-01-01T00:00:00+00:00"))
        work.create(record("GS-HIGH-FIRST", priority=9, created_at="2026-01-01T00:00:01+00:00"))
        work.create(record("GS-HIGH-SECOND", priority=9, created_at="2026-01-01T00:00:02+00:00"))
        self.assertEqual("GS-HIGH-FIRST", work.claim_next("one")["task_id"])
        work.finish(work.start("GS-HIGH-FIRST", "one"), "completed")
        self.assertEqual("GS-HIGH-SECOND", work.claim_next("two")["task_id"])

    def test_pending_rejected_and_duplicate_ids_cannot_execute(self):
        work = queue(PersistentQueue, self.root)
        work.create(record("GS-PENDING", approval="pending"))
        self.assertIsNone(work.claim("GS-PENDING", "worker"))
        with self.assertRaises(FileExistsError):
            work.create(record("GS-PENDING", approval="approved"))
        rejected = record("GS-REJECTED", approval="rejected")
        work.create(rejected)
        self.assertIsNone(work.claim("GS-REJECTED", "worker"))

    def test_cross_thread_claim_allows_exactly_one_owner(self):
        work = queue(PersistentQueue, self.root)
        work.create(record("GS-ONCE"))
        barrier = threading.Barrier(8)
        def attempt(number: int):
            barrier.wait()
            return work.claim("GS-ONCE", f"worker-{number}")
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(1, sum(item is not None for item in outcomes))
        self.assertEqual(1, work.read("GS-ONCE")["attempt_count"])

    def test_retry_budget_and_stale_crash_recovery(self):
        work = queue(PersistentQueue, self.root, lease_seconds=30, max_attempts=2)
        work.create(record("GS-STALE"))
        claimed = work.claim("GS-STALE", "dead-worker")
        running = work.start("GS-STALE", "dead-worker")
        old = datetime.now(timezone.utc) - timedelta(minutes=2)
        running["heartbeat_at"] = timestamp(old)
        running["started_at"] = timestamp(old)
        work.write(running)
        recovered = work.recover_stale(datetime.now(timezone.utc))
        self.assertEqual(["retry_pending"], [item["status"] for item in recovered])
        self.assertFalse(work.claim_path("GS-STALE").exists())
        claimed_again = work.claim("GS-STALE", "replacement")
        self.assertEqual(2, claimed_again["attempt_count"])
        failed = work.record_failure("GS-STALE", "replacement", RuntimeError("still broken"))
        self.assertEqual("failed", failed["status"])

    def test_startup_recovers_interrupted_lease(self):
        work = queue(PersistentQueue, self.root)
        work.create(record("GS-INTERRUPTED"))
        self.assertIsNotNone(work.claim("GS-INTERRUPTED", "old-process"))
        work.start("GS-INTERRUPTED", "old-process")
        recovered = work.recover_interrupted()
        self.assertEqual(1, len(recovered))
        self.assertEqual("retry_pending", recovered[0]["status"])
        self.assertEqual("startup_recovery", recovered[0]["failed_stage"])
        self.assertFalse(work.claim_path("GS-INTERRUPTED").exists())

    def test_legacy_queue_contract_matches_on_asus(self):
        source = Path(os.environ.get(
            "DATABLOCKS_LEGACY_QUEUE",
            r"D:\000_AI Project\AI Agents Datablocks\orchestrator\task_queue.py",
        ))
        if not source.is_file():
            self.skipTest("Legacy Administrator queue is not installed on this machine")
        spec = importlib.util.spec_from_file_location("gs031_legacy_contract", source)
        assert spec and spec.loader
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        results = []
        for implementation in (legacy.PersistentQueue, PersistentQueue):
            with TemporaryDirectory() as folder:
                work = queue(implementation, Path(folder))
                work.create(record("GS-CONTRACT"))
                claimed = work.claim("GS-CONTRACT", "worker")
                running = work.start("GS-CONTRACT", "worker")
                completed = work.finish(running, "completed", result={"ok": True})
                results.append((stable(claimed), stable(completed)))
        self.assertEqual(results[0], results[1])


class PortableConfigurationTests(unittest.TestCase):
    def test_explicit_state_dir_and_ollama_endpoint_are_portable(self):
        with patch.dict(os.environ, {
            "GROUND_SPACE_STATE_DIR": str(self.root / "community-state"),
            "GROUND_SPACE_OLLAMA_ENDPOINT": "http://localhost:11434/",
        }, clear=False):
            self.assertEqual(self.root / "community-state", default_state_dir())
            self.assertEqual("http://localhost:11434", ollama_endpoint())

    def test_endpoint_rejects_embedded_credentials(self):
        with patch.dict(os.environ, {"GROUND_SPACE_OLLAMA_ENDPOINT": "http://user:secret@localhost:11434"}):
            with self.assertRaisesRegex(ValueError, "without credentials"):
                ollama_endpoint()

    def test_optional_tools_are_detected_from_path(self):
        inventory = executable_inventory()
        self.assertEqual({"ollama", "codex"}, set(inventory))
        self.assertTrue(all(value is None or Path(value).is_absolute() for value in inventory.values()))

    @property
    def root(self) -> Path:
        return Path(os.environ.get("TEMP", ".")).resolve()


if __name__ == "__main__":
    unittest.main()
