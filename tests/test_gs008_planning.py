"""GS-008: goal awareness without automatic file or command execution."""

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.webapp import GroundSpaceApp, parse_slash_note, planning_followup_prompt


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = GroundSpaceApp.__new__(GroundSpaceApp)
        self.app.lock = threading.RLock()
        self.app.conversations = {}
        self.app.history_path = Path(self.temp.name) / "conversations.json"
        self.app.ollama_endpoint = "http://127.0.0.1:11434"
        self.app.registered_models = ["qwen2.5-coder:3b", "qwen3.5:4b"]
        self.app._register_worker = Mock()
        self.app.codex = SimpleNamespace(is_registered=Mock(return_value=False))
        self.app.administrator = SimpleNamespace(submit=Mock(side_effect=[
            {"task_id": "T-001"}, {"task_id": "T-002"}, {"task_id": "T-003"}
        ]))
        group = {"id": "group-1", "conversation_id": "group-room",
                 "models": ["qwen2.5-coder:3b", "qwen3.5:4b"], "project_id": None}
        self.app.workspaces = SimpleNamespace(
            validate_project=lambda project_id: None,
            get_group=lambda group_id: group,
        )

    def test_slash_note_parser(self):
        self.assertEqual(parse_slash_note("/goal  Build the Codex"), ("goal", "Build the Codex"))
        self.assertEqual(parse_slash_note("/milestone Test the bridge"), ("milestone", "Test the bridge"))
        with self.assertRaises(ValueError):
            parse_slash_note("/goal")

    def test_planning_prompt_is_non_executable(self):
        text = planning_followup_prompt("goal", "Finish the third island")
        self.assertIn("Finish the third island", text)
        self.assertIn("planning only", text.lower())
        self.assertIn("Do not claim", text)

    def test_context_keeps_goal_after_chat_rolls_forward(self):
        self.app.add_history("room", "note", "Build Codex tablet", kind="goal")
        for i in range(30):
            self.app.add_history("room", "user", "Ordinary message " + str(i))
        context = self.app.conversation_context("room")
        self.assertIn("planning_goal: Build Codex tablet", context)
        self.assertIn("Ordinary message 29", context)

    @patch("ground_space.webapp.probe_ollama", return_value={"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]})
    @patch("ground_space.webapp.threading.Thread")
    def test_direct_goal_queues_review_not_a_project_write(self, thread, probe):
        answer = self.app.submit_chat({"agent": "qwen", "prompt": "/goal Build the third island",
                                      "conversation_id": "direct-room", "model": "qwen2.5-coder:3b"})
        self.assertEqual(answer["entry"]["role"], "note")
        self.assertEqual(answer["entry"]["task_id"], "T-001")
        self.assertEqual(len(self.app.conversations["direct-room"]), 1)
        self.assertEqual(self.app.conversations["direct-room"][0]["kind"], "goal")
        args, kwargs = self.app.administrator.submit.call_args
        self.assertEqual(kwargs["required_permissions"], ["read", "propose"])
        self.assertEqual(kwargs["worker_id"], self.app.worker_id("qwen2.5-coder:3b"))
        self.assertIn("Build the third island", args[0]["prompt"])
        thread.return_value.start.assert_called_once()

    @patch("ground_space.webapp.probe_ollama", return_value={"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]})
    @patch("ground_space.webapp.threading.Thread")
    def test_group_milestone_queues_coordinator_only_with_single_note(self, thread, probe):
        answer = self.app.submit_chat({"agent": "group", "group_id": "group-1",
                                      "prompt": "/milestone Complete Codex assembly",
                                      "performance": "fast"})
        self.assertEqual(answer["entry"]["role"], "note")
        self.assertEqual(answer["entry"]["task_ids"], ["T-001"])
        self.assertEqual(len(self.app.conversations["group-room"]), 1)
        self.assertEqual(self.app.administrator.submit.call_count, 1)
        args, kwargs = self.app.administrator.submit.call_args
        self.assertEqual(kwargs["required_permissions"], ["read", "propose"])
        self.assertEqual(args[0]["speaker"], "Coordinator")
        thread.return_value.start.assert_called_once()

    @patch("ground_space.webapp.probe_ollama", return_value={"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]})
    @patch("ground_space.webapp.threading.Thread")
    def test_ordinary_group_chat_uses_coordinator(self, thread, probe):
        answer = self.app.submit_group({"group_id": "group-1", "prompt": "What next?"})
        self.assertEqual(answer["task_ids"], ["T-001"])
        args, _ = self.app.administrator.submit.call_args
        self.assertEqual(args[0]["speaker"], "Coordinator")
        self.assertIn("You are Coordinator", args[0]["prompt"])
        thread.return_value.start.assert_called_once()

    @patch("ground_space.webapp.probe_ollama", return_value={"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]})
    @patch("ground_space.webapp.threading.Thread")
    def test_mention_routes_to_solo_specialist(self, thread, probe):
        answer = self.app.submit_group({"group_id": "group-1", "prompt": "@Qwen propose tests"})
        self.assertEqual(answer["task_ids"], ["T-001"])
        args, _ = self.app.administrator.submit.call_args
        self.assertEqual(args[0]["speaker"], "qwen2.5-coder:3b")
        self.assertNotIn("You are Coordinator", args[0]["prompt"])
        thread.return_value.start.assert_called_once()

    @patch("ground_space.webapp.probe_ollama", return_value={"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]})
    def test_cloud_mention_is_rejected_before_queue(self, probe):
        with self.assertRaisesRegex(ValueError, "not connected"):
            self.app.submit_group({"group_id": "group-1", "prompt": "@Claude help"})
        self.app.administrator.submit.assert_not_called()

    def test_admin_note_never_queues_work(self):
        answer = self.app.submit_chat({"agent": "administrator", "prompt": "/goal Improve the UI",
                                      "conversation_id": "admin-room"})
        self.assertEqual(answer["entry"]["planning_status"], "recorded")
        self.app.administrator.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
