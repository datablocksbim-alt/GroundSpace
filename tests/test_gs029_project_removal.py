"""Project removal is an owner-only metadata unlink, never a filesystem deletion."""
from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ground_space.webapp import GroundSpaceApp
from ground_space.workspaces import WorkspaceRegistry


class ProjectRemovalTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.allowed = self.root / "allowed"
        self.allowed.mkdir()
        self.folder = self.allowed / "My Project"
        self.folder.mkdir()
        (self.folder / "keep.txt").write_text("preserve this file", encoding="utf-8")
        self.registry = WorkspaceRegistry(self.root / "private", [self.allowed])
        self.project = self.registry.add_project(str(self.folder))
        self.group = self.registry.create_group(
            "Team chat", ["qwen2.5-coder:3b"], self.project["id"],
            ["qwen2.5-coder:3b"], {"qwen2.5-coder:3b": "manual"})
        self.app = GroundSpaceApp.__new__(GroundSpaceApp)
        self.app.lock = threading.RLock()
        self.app.workspaces = self.registry
        self.app.queue_dir = self.root / "private" / "queue"
        self.app.queue_dir.mkdir()
        self.app.codex = SimpleNamespace(snapshot=lambda: {"jobs": []})
        self.app.collaborations = SimpleNamespace(snapshot=lambda: [])

    def remove(self):
        return self.app.remove_project({"project_id": self.project["id"],
                                        "confirm_name": self.project["name"]})

    def test_unlink_preserves_folder_and_group_conversation_and_approvals(self):
        result = self.remove()
        self.assertEqual(result["unassigned_chats"], 1)
        self.assertFalse(result["folder_deleted"])
        self.assertEqual((self.folder / "keep.txt").read_text(encoding="utf-8"),
                         "preserve this file")
        reopened = WorkspaceRegistry(self.root / "private", [self.allowed])
        self.assertEqual(reopened.snapshot()["projects"], [])
        group = reopened.get_group(self.group["id"])
        self.assertIsNone(group["project_id"])
        self.assertEqual(group["conversation_id"], self.group["conversation_id"])
        self.assertEqual(group["approval_modes"], self.group["approval_modes"])

    def test_wrong_name_missing_id_and_duplicate_removal_fail(self):
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.app.remove_project({"project_id": self.project["id"],
                                     "confirm_name": "wrong"})
        with self.assertRaises(ValueError):
            self.app.remove_project({"project_id": "other", "confirm_name": "wrong"})
        self.assertEqual(len(self.registry.snapshot()["projects"]), 1)
        self.remove()
        with self.assertRaisesRegex(ValueError, "Unknown project"):
            self.remove()

    def test_pending_group_work_blocks_unlink(self):
        record = {"task_id": "GS-demo", "status": "queued",
                  "approval": {"status": "pending"},
                  "payload": {"group_id": self.group["id"], "project_id": self.project["id"]}}
        path = self.app.queue_dir / "GS-demo.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pending or active"):
            self.remove()
        self.assertEqual(self.registry.get_group(self.group["id"])["project_id"],
                         self.project["id"])
        record["approval"]["status"] = "rejected"
        path.write_text(json.dumps(record), encoding="utf-8")
        self.remove()

    def test_codex_job_and_collaboration_block_unlink(self):
        self.app.codex = SimpleNamespace(snapshot=lambda: {"jobs": [
            {"project_id": self.project["id"], "status": "pending_approval"}]})
        with self.assertRaisesRegex(ValueError, "Codex"):
            self.remove()
        self.app.codex = SimpleNamespace(snapshot=lambda: {"jobs": []})
        self.app.collaborations = SimpleNamespace(snapshot=lambda: [
            {"project_id": self.project["id"], "state": "proposal_pending"}])
        with self.assertRaisesRegex(ValueError, "Co-work"):
            self.remove()
        self.assertEqual(len(self.registry.snapshot()["projects"]), 1)

    def test_full_codex_ledger_blocks_unlink_even_if_snapshot_is_truncated(self):
        older = [{"project_id": self.project["id"], "status": "pending_approval"}]
        older.extend({"project_id": "other", "status": "completed"} for _ in range(60))
        self.app.codex = SimpleNamespace(
            jobs=older, snapshot=lambda: {"jobs": older[-50:]})
        with self.assertRaisesRegex(ValueError, "Codex"):
            self.remove()
        self.assertEqual(len(self.registry.snapshot()["projects"]), 1)

    def test_running_task_remains_blocked_even_with_inconsistent_rejection(self):
        task = {"status": "running", "approval": {"status": "rejected"},
                "payload": {"group_id": self.group["id"]}}
        (self.app.queue_dir / "running.json").write_text(json.dumps(task), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pending or active"):
            self.remove()

    def test_unreadable_queue_file_blocks_removal(self):
        (self.app.queue_dir / "bad.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cannot verify"):
            self.remove()
        self.assertEqual(len(self.registry.snapshot()["projects"]), 1)


if __name__ == "__main__":
    unittest.main()
