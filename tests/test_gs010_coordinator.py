"""GS-010 routing, persistence, and explicit-approval safety tests."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.coordinator import ProposalStore, coordinator_prompt, select_participants
from ground_space.webapp import GroundSpaceApp


GROUP = {
    "id": "group-pyrene",
    "conversation_id": "conversation-pyrene",
    "project_id": "project-pyrene",
    "models": ["qwen2.5-coder:3b", "qwen3.5:4b"],
}


class CoordinatorTests(unittest.TestCase):
    def test_default_and_member_mentions(self):
        self.assertEqual([("qwen2.5-coder:3b", "Coordinator")],
                         select_participants("Help with Codex", GROUP["models"]))
        self.assertEqual([("qwen2.5-coder:3b", "qwen2.5-coder:3b")],
                         select_participants("@Qwen review", GROUP["models"]))
        self.assertEqual([("qwen3.5:4b", "qwen3.5:4b")],
                         select_participants("@qwen3.5:4b review", GROUP["models"]))
        self.assertEqual([("qwen2.5-coder:3b", "Coordinator"),
                          ("qwen3.5:4b", "qwen3.5:4b")],
                         select_participants("@Coordinator and @qwen3.5:4b", GROUP["models"]))
        self.assertEqual([("qwen2.5-coder:3b", "Coordinator")],
                         select_participants("email user@example.com", GROUP["models"]))

    def test_provider_and_nonmember_mentions_are_denied(self):
        for mention in ("@Claude", "@ChatGPT", "@unknown"):
            with self.subTest(mention=mention), self.assertRaises(ValueError):
                select_participants(mention + " help", GROUP["models"])

    def test_coordinator_prompt_never_claims_work_done(self):
        text = coordinator_prompt("Build a Codex tablet")
        self.assertIn("You are Coordinator", text)
        self.assertIn("Do not claim", text)
        self.assertIn("Only read/propose chat is enabled", text)

    def test_proposal_store_is_persistent_and_stays_pending(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "private" / "proposals.json"
            store = ProposalStore(path)
            cards = store.create_goal("Build tablet", GROUP)
            self.assertEqual(3, len(cards))
            self.assertTrue(all(x["approval"]["status"] == "pending" for x in cards))
            self.assertEqual([cards[0]["task_id"], cards[1]["task_id"]],
                             cards[2]["depends_on"])
            self.assertEqual(GROUP["project_id"], cards[0]["project_id"])
            self.assertNotIn("path", cards[0])
            restored = ProposalStore(path)
            self.assertEqual(3, len(restored.snapshot()))
            self.assertEqual(cards[0]["task_id"], restored.get(cards[0]["task_id"])["task_id"])

    @patch("ground_space.webapp.threading.Thread")
    @patch("ground_space.webapp.probe_ollama", return_value={
        "available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]
    })
    def test_owner_click_approves_only_selected_nonexecuting_task(self, probe, thread):
        with tempfile.TemporaryDirectory() as root:
            app = GroundSpaceApp.__new__(GroundSpaceApp)
            app.lock = threading.RLock()
            app.proposals = ProposalStore(Path(root) / "proposals.json")
            cards = app.proposals.create_goal("Build tablet", GROUP)
            app.workspaces = SimpleNamespace(get_group=lambda group_id: GROUP)
            app.registered_models = list(GROUP["models"])
            app.ollama_endpoint = "http://127.0.0.1:11434"
            app._register_worker = Mock()
            app.administrator = SimpleNamespace(
                submit=Mock(return_value={"task_id": cards[0]["task_id"]}),
                status=Mock(return_value={"status": "queued"}),
            )
            with self.assertRaises(ValueError):
                app.approve_proposal({"task_id": cards[0]["task_id"],
                                      "group_id": GROUP["id"]})
            app.administrator.submit.assert_not_called()
            with self.assertRaises(ValueError):
                app.approve_proposal({"task_id": cards[2]["task_id"],
                                      "group_id": GROUP["id"], "confirm": True})
            app.administrator.submit.assert_not_called()
            output = app.approve_proposal({"task_id": cards[0]["task_id"],
                                            "group_id": GROUP["id"], "confirm": True})
            self.assertEqual(cards[0]["task_id"], output["proposal_id"])
            self.assertEqual("queued", app.proposals.get(cards[0]["task_id"])["status"])
            kwargs = app.administrator.submit.call_args.kwargs
            self.assertEqual(cards[0]["task_id"], kwargs["task_id"])
            self.assertEqual(["read", "propose"], kwargs["required_permissions"])
            self.assertTrue(kwargs["approved"])
            self.assertEqual("ground-space-owner-click", kwargs["approval_source"])
            self.assertNotIn("path", app.administrator.submit.call_args.args[0])
            thread.return_value.start.assert_called_once()
            with self.assertRaises(ValueError):
                app.approve_proposal({"task_id": cards[0]["task_id"],
                                      "group_id": GROUP["id"], "confirm": True})
            self.assertEqual(1, app.administrator.submit.call_count)


if __name__ == "__main__":
    unittest.main()
