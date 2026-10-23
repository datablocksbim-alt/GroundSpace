"""GS-029 owner authorization gate — no filesystem writes or network during tests."""
from __future__ import annotations
import unittest
from copy import deepcopy

from tools.approve_two_qwen_greetings import greeting, target_pair, validate_target


def task(label: str, task_id: str = "GS-" + "a" * 32):
    prompt = ("Bounded conversation context:\nuser: hi qwen\n"
              "Current user request:\nare you there") if label == "are you there" else label
    return {
        "task_id": task_id,
        "status": "queued",
        "source": "ground_space",
        "requested_worker": "qwen-proposal",
        "required_permissions": ["read", "propose"],
        "approval": {"status": "pending"},
        "payload": {"prompt": prompt, "model": "qwen2.5-coder:3b",
                    "request_type": "explanation", "conversation_id": "local-chat"},
    }


class ApprovedGreetingsTest(unittest.TestCase):
    def setUp(self):
        self.left = task("hi qwen")
        self.right = task("are you there", "GS-" + "b" * 32)

    def test_exact_two_greetings(self):
        targets = target_pair([self.left, self.right])
        self.assertEqual({x[1] for x in targets}, {"hi qwen", "are you there"})
        self.assertEqual(greeting(self.right), "are you there")

    def test_accepts_legacy_missing_model_and_verified_project_chat(self):
        self.left["payload"].pop("model")
        self.left["payload"]["project_id"] = "project-1"
        history = {"local-chat": [{"task_id": self.left["task_id"], "agent": "qwen",
                                    "project_id": "project-1"},
                                  {"task_id": self.right["task_id"], "agent": "qwen"}]}
        result = target_pair([self.left, self.right], conversations=history,
                             project_ids={"project-1"}, group_conversations=set())
        self.assertEqual(2, len(result))

    def test_refuse_more_pending(self):
        extra = task("hi qwen", "GS-" + "c" * 32)
        with self.assertRaisesRegex(ValueError, "exactly 2"):
            target_pair([self.left, self.right, extra])

    def test_refuse_other_running_or_approved_work(self):
        for state, approval in [("running", "approved"), ("queued", "approved"),
                                ("retry_pending", "approved")]:
            unrelated = task("anything", "GS-" + "c" * 32)
            unrelated["status"] = state
            unrelated["approval"]["status"] = approval
            with self.assertRaisesRegex(ValueError, "Another task"):
                target_pair([self.left, self.right, unrelated])

    def test_refuse_any_different_prompt(self):
        other = deepcopy(self.right)
        other["payload"]["prompt"] = "delete files"
        with self.assertRaisesRegex(ValueError, "two owner-approved"):
            target_pair([self.left, other])

    def test_refuse_group_authority_or_unverified_project(self):
        other = deepcopy(self.left)
        other["payload"]["group_id"] = "not-direct"
        with self.assertRaisesRegex(ValueError, "direct Qwen"):
            validate_target(other)
        self.left["payload"]["project_id"] = "unknown"
        history = {"local-chat": [{"task_id": self.left["task_id"], "agent": "qwen",
                                    "project_id": "unknown"},
                                  {"task_id": self.right["task_id"], "agent": "qwen"}]}
        with self.assertRaisesRegex(ValueError, "origin is not verified"):
            target_pair([self.left, self.right], conversations=history,
                        project_ids=set(), group_conversations=set())

    def test_refuse_group_conversation_even_without_group_payload(self):
        history = {"local-chat": [{"task_id": self.left["task_id"], "agent": "qwen"},
                                  {"task_id": self.right["task_id"], "agent": "qwen"}]}
        with self.assertRaisesRegex(ValueError, "origin is not verified"):
            target_pair([self.left, self.right], conversations=history,
                        project_ids=set(), group_conversations={"local-chat"})

    def test_refuse_worker_or_permission_escalation(self):
        for field, value in [("requested_worker", "codex-cli"),
                             ("required_permissions", ["read", "propose", "write"])]:
            other = deepcopy(self.left)
            other[field] = value
            with self.assertRaises(ValueError):
                validate_target(other)

    def test_refuse_already_approved_or_finished(self):
        for status, approval in [("queued", "approved"), ("completed", "pending")]:
            other = deepcopy(self.left)
            other["status"] = status
            other["approval"]["status"] = approval
            with self.assertRaisesRegex(ValueError, "not a queued/pending"):
                validate_target(other)


if __name__ == "__main__":
    unittest.main()
