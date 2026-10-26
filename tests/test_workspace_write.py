"""Project-scoped full-write policy and Qwen executor regression tests."""
from __future__ import annotations

import io
import json
import copy
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.webapp import GroundSpaceApp
from ground_space.worker_process import ollama_workspace
from ground_space.workspaces import WorkspaceRegistry


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _ollama_response(plan: dict) -> _Response:
    return _Response(json.dumps({"response": json.dumps(plan)}).encode("utf-8"))


class WorkspaceExecutorTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "project"
        self.project.mkdir()
        self.spec = {"model": "qwen2.5-coder:3b", "endpoint": "http://127.0.0.1:11434"}
        self.task = {"task_id": "GS-test", "correlation_id": "corr-test",
                     "payload": {"project_path": str(self.project), "prompt": "Make the change"}}

    def run_plan(self, operations):
        with patch("ground_space.worker_process.urllib.request.urlopen",
                   return_value=_ollama_response({"summary": "done", "operations": operations})):
            return ollama_workspace(self.spec, self.task)

    def test_create_edit_and_delete_file_are_confined_to_project(self):
        result = self.run_plan([{"op": "mkdir", "path": "src"},
                                {"op": "write", "path": "src/demo.py", "content": "print('one')\n"}])
        self.assertEqual("print('one')\n", (self.project / "src" / "demo.py").read_text())
        self.assertTrue(result["result"]["project_scoped"])
        self.run_plan([{"op": "write", "path": "src/demo.py", "content": "print('two')\n"}])
        self.assertEqual("print('two')\n", (self.project / "src" / "demo.py").read_text())
        self.run_plan([{"op": "delete", "path": "src/demo.py"}])
        self.assertFalse((self.project / "src" / "demo.py").exists())

    def test_traversal_sensitive_paths_and_nonempty_directory_delete_are_blocked(self):
        for path in ("../escape.txt", ".git/config", ".env", "secrets/key.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_plan([{"op": "write", "path": path, "content": "bad"}])
        directory = self.project / "kept"
        directory.mkdir()
        (directory / "file.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty directories"):
            self.run_plan([{"op": "delete", "path": "kept"}])

    def test_remote_ollama_endpoint_is_refused(self):
        self.spec["endpoint"] = "https://example.com"
        with self.assertRaisesRegex(ValueError, "non-local"):
            ollama_workspace(self.spec, self.task)


class WorkspacePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        project_dir = self.root / "demo"
        project_dir.mkdir()
        self.registry = WorkspaceRegistry(self.root / "private", [self.root])
        self.project = self.registry.add_project(str(project_dir), "Demo")

    def test_full_write_requires_selected_project_and_persists(self):
        with self.assertRaisesRegex(ValueError, "Select a registered project"):
            self.registry.create_group("Bad", ["qwen2.5-coder:3b"], None,
                                       ["qwen2.5-coder:3b"], access_modes={"qwen2.5-coder:3b": "full_write"})
        group = self.registry.create_group(
            "Good", ["qwen2.5-coder:3b"], self.project["id"], ["qwen2.5-coder:3b"],
            approval_modes={"qwen2.5-coder:3b": "manual"},
            access_modes={"qwen2.5-coder:3b": "full_write"},
        )
        restored = WorkspaceRegistry(self.root / "private", [self.root])
        self.assertEqual("full_write", restored.get_group(group["id"])["access_modes"]["qwen2.5-coder:3b"])

    def test_existing_groups_default_to_chat_only(self):
        group = self.registry.create_group("Legacy", ["qwen2.5-coder:3b"], self.project["id"],
                                           ["qwen2.5-coder:3b"])
        self.assertEqual("chat", group["access_modes"]["qwen2.5-coder:3b"])

    def test_group_workspace_task_uses_write_worker_and_manual_approval(self):
        class Admin:
            def __init__(self):
                self.tasks = {}
            def submit(inner, payload, *, worker_id, required_permissions,
                       execution_timeout_seconds, approved, approval_source):
                task = {"task_id": "GS-write", "source": "ground_space", "status": "queued",
                        "payload": dict(payload), "requested_worker": worker_id,
                        "required_permissions": list(required_permissions),
                        "approval": {"status": "approved" if approved else "pending"}}
                inner.tasks[task["task_id"]] = task
                return copy.deepcopy(task)
            def status(inner, task_id):
                return copy.deepcopy(inner.tasks[task_id])

        group = self.registry.create_group(
            "Workspace", ["qwen2.5-coder:3b"], self.project["id"], ["qwen2.5-coder:3b"],
            approval_modes={"qwen2.5-coder:3b": "manual"},
            access_modes={"qwen2.5-coder:3b": "full_write"},
        )
        app = GroundSpaceApp.__new__(GroundSpaceApp)
        app.workspaces = self.registry
        app.lock = threading.RLock()
        app.group_dispatch_lock = threading.Lock()
        app.ollama_endpoint = "http://127.0.0.1:1"
        app.registered_models = ["qwen2.5-coder:3b"]
        app.codex = SimpleNamespace(is_registered=Mock(return_value=False))
        app.administrator = Admin()
        app.conversations = {}
        app.history_path = self.root / "private" / "conversations.json"
        app._register_worker = Mock()
        with patch("ground_space.webapp.probe_ollama", return_value={"available": False, "models": []}), \
             patch("ground_space.webapp.threading.Thread") as worker:
            response = app.submit_group({"group_id": group["id"], "prompt": "Create notes.txt",
                                         "request_type": "workspace_change"})
        task = app.administrator.status(response["task_ids"][0])
        self.assertEqual("pending", task["approval"]["status"])
        self.assertEqual({"read", "propose", "workspace_write"}, set(task["required_permissions"]))
        self.assertEqual(GroundSpaceApp.workspace_worker_id("qwen2.5-coder:3b"), task["requested_worker"])
        self.assertEqual(str(Path(self.project["path"])), task["payload"]["project_path"])
        worker.assert_not_called()

    def test_chat_only_agent_cannot_receive_workspace_task(self):
        group = self.registry.create_group("Chat", ["qwen2.5-coder:3b"], self.project["id"],
                                           ["qwen2.5-coder:3b"])
        app = GroundSpaceApp.__new__(GroundSpaceApp)
        app.workspaces, app.lock = self.registry, threading.RLock()
        app.ollama_endpoint, app.registered_models = "http://127.0.0.1:1", ["qwen2.5-coder:3b"]
        app.codex = SimpleNamespace(is_registered=Mock(return_value=False))
        app._register_worker = Mock()
        app.conversations, app.history_path = {}, self.root / "history.json"
        with patch("ground_space.webapp.probe_ollama", return_value={"available": False, "models": []}):
            with self.assertRaisesRegex(ValueError, "Enable selected-project full write"):
                app.submit_group({"group_id": group["id"], "prompt": "Create notes.txt",
                                  "request_type": "workspace_change"})


if __name__ == "__main__":
    unittest.main()
