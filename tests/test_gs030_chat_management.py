"""GS-030: project and multi-agent chat rename/delete preserve identity and audit."""
from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from ground_space.webapp import GroundSpaceApp
from ground_space.workspaces import WorkspaceRegistry


class ChatManagementTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.allowed = self.dir / "allowed"
        self.allowed.mkdir()
        self.folder = self.allowed / "example"
        self.folder.mkdir()
        (self.folder / "keep.txt").write_text("original file", encoding="utf-8")
        self.registry = WorkspaceRegistry(self.dir / "private", [self.allowed])
        self.project = self.registry.add_project(str(self.folder))
        self.group = self.registry.create_group(
            "Old name", ["qwen2.5-coder:3b"], self.project["id"],
            ["qwen2.5-coder:3b"], {"qwen2.5-coder:3b": "manual"})
        self.app = GroundSpaceApp.__new__(GroundSpaceApp)
        self.app.lock = threading.RLock()
        self.app.workspaces = self.registry
        self.app.queue_dir = self.dir / "private" / "queue"
        self.app.queue_dir.mkdir(parents=True)
        self.app.codex = SimpleNamespace(jobs=[], snapshot=lambda: {"jobs": []})
        self.app.collaborations = SimpleNamespace(runs=[], snapshot=lambda: [])
        self.app.conversations = {
            self.group["conversation_id"]: [{"role": "user", "content": "Saved transcript"}]
        }

    def rename_project(self, name="New project"):
        return self.app.rename_project({"project_id": self.project["id"],
                                        "confirm_name": self.project["name"], "name": name})

    def rename_group(self, name="Renamed chat"):
        return self.app.rename_group({"group_id": self.group["id"],
                                      "confirm_name": self.group["name"], "name": name})

    def remove_group(self):
        return self.app.remove_group({"group_id": self.group["id"],
                                      "confirm_name": self.group["name"]})

    def test_project_rename_changes_only_label(self):
        new = self.rename_project()
        self.assertEqual(new["name"], "New project")
        self.assertEqual(new["id"], self.project["id"])
        self.assertEqual(new["path"], str(self.folder))
        self.assertEqual((self.folder / "keep.txt").read_text(), "original file")
        registry = WorkspaceRegistry(self.dir / "private", [self.allowed])
        self.assertEqual(registry.get_project(self.project["id"])["name"], "New project")
        self.assertEqual(registry.get_group(self.group["id"]), self.group)

    def test_group_rename_preserves_members_history_and_approvals(self):
        renamed = self.rename_group()
        for field in ("id", "conversation_id", "project_id", "models", "approval_modes"):
            self.assertEqual(renamed[field], self.group[field])
        self.assertEqual(renamed["name"], "Renamed chat")
        self.assertEqual(WorkspaceRegistry(self.dir / "private", [self.allowed])
                         .get_group(self.group["id"])["name"], "Renamed chat")
        self.assertEqual(len(self.app.conversations[self.group["conversation_id"]]), 1)

    def test_bad_names_and_stale_confirmations_fail_closed(self):
        for value in ("", " ", "X" * 81, None):
            with self.assertRaises(ValueError):
                self.rename_project(value)
        for value in ("", " ", "Y" * 71, None):
            with self.assertRaises(ValueError):
                self.rename_group(value)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.app.rename_group({"group_id": self.group["id"], "confirm_name": "stale", "name": "Other"})
        with self.assertRaisesRegex(ValueError, "changed"):
            self.app.rename_project({"project_id": self.project["id"],
                                     "confirm_name": "stale", "name": "Other"})

    def test_chat_removal_preserves_transcript_and_project(self):
        result = self.remove_group()
        self.assertTrue(result["transcript_retained"])
        self.assertEqual(result["conversation_id"], self.group["conversation_id"])
        self.assertEqual(len(self.registry.snapshot()["groups"]), 0)
        self.assertEqual(len(self.registry.snapshot()["projects"]), 1)
        self.assertEqual(self.app.conversations[self.group["conversation_id"]][0]["content"],
                         "Saved transcript")
        with self.assertRaisesRegex(ValueError, "Unknown group"):
            self.remove_group()
        self.assertEqual((self.folder / "keep.txt").read_text(), "original file")

    def test_pending_and_running_queue_tasks_block_chat_removal(self):
        task = {"status": "queued", "approval": {"status": "pending"},
                "payload": {"group_id": self.group["id"]}}
        file = self.app.queue_dir / "GS-a.json"
        file.write_text(json.dumps(task), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "queued or active"):
            self.remove_group()
        task["status"] = "running"
        task["approval"]["status"] = "rejected"
        file.write_text(json.dumps(task), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "queued or active"):
            self.remove_group()
        task["status"] = "queued"
        file.write_text(json.dumps(task), encoding="utf-8")
        self.remove_group()

    def test_codex_and_cowork_blocks(self):
        jobs = [{"group_id": self.group["id"], "status": "pending_approval"}]
        jobs.extend({"group_id": "other", "status": "completed"} for _ in range(60))
        self.app.codex = SimpleNamespace(jobs=jobs,
                                          snapshot=lambda: {"jobs": jobs[-50:]})
        with self.assertRaisesRegex(ValueError, "Codex"):
            self.remove_group()
        self.app.codex = SimpleNamespace(jobs=[], snapshot=lambda: {"jobs": []})
        self.app.collaborations = SimpleNamespace(
            runs=[{"group_id": self.group["id"], "state": "proposal_pending"}],
            snapshot=lambda: [])
        with self.assertRaisesRegex(ValueError, "Co-work"):
            self.remove_group()

    def test_unreadable_task_file_blocks_chat_removal(self):
        (self.app.queue_dir / "bad.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cannot verify"):
            self.remove_group()

    def test_api_requires_existing_csrf_guard(self):
        source = (Path(__file__).parents[1] / "ground_space" / "webapp.py").read_text(encoding="utf-8")
        for route in ('/api/projects/rename', '/api/groups/rename', '/api/groups/remove'):
            self.assertIn('if path == "' + route + '":', source)
        self.assertIn('if not self._csrf_valid():', source)


if __name__ == "__main__":
    unittest.main()
