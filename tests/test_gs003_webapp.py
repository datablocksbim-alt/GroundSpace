from __future__ import annotations

import http.cookiejar
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from ground_space.webapp import GroundSpaceApp, create_server


class GS003WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.app = GroundSpaceApp(self.state_dir, ollama_endpoint="http://127.0.0.1:1")
        self.server = create_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        cookie_jar = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        self.bootstrap = self.get_json("/api/bootstrap")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def get_json(self, path):
        with self.client.open(self.origin + path, timeout=3) as response:
            return json.load(response)

    def post_json(self, path, body, *, token=None, csrf=True):
        headers = {"Content-Type": "application/json", "Origin": self.origin}
        if csrf:
            headers["X-Ground-Space-CSRF"] = self.bootstrap["csrf_token"]
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.origin + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        with self.client.open(request, timeout=3) as response:
            return json.load(response)

    def test_cross_site_submission_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post_json("/api/chat", {"agent": "administrator", "prompt": "help"}, csrf=False)
        self.assertEqual(403, caught.exception.code)

    def test_chat_auto_approves_and_dispatches_async(self):
        created = self.post_json("/api/chat", {"agent": "administrator", "prompt": "help",
                                                "conversation_id": "web-test"})
        task_id = created["task"]["task_id"]
        self.assertEqual("approved", created["task"]["approval"]["status"])
        self.assertEqual("automatic", created["task"]["approval"]["method"])
        self.assertEqual("ground-space-local-chat", created["task"]["approval"]["owner"])
        deadline = time.monotonic() + 4
        task = {}
        while time.monotonic() < deadline:
            task = self.get_json(f"/api/tasks/{task_id}")
            if task.get("status") == "completed":
                break
            time.sleep(0.05)
        self.assertEqual("completed", task.get("status"))
        self.assertTrue(task["result"]["read_only"])

    def test_manual_approval_endpoint_is_removed(self):
        created = self.post_json("/api/chat", {"agent": "administrator", "prompt": "help",
                                                "conversation_id": "legacy-approval"})
        task_id = created["task"]["task_id"]
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post_json(f"/api/tasks/{task_id}/approve", {})
        self.assertEqual(404, caught.exception.code)

    def test_qwen_stays_proposal_only_when_auto_approved(self):
        created = self.post_json("/api/chat", {"agent": "qwen", "prompt": "Explain a queue",
                                                "request_type": "explanation",
                                                "required_permissions": ["write"],
                                                "conversation_id": "qwen-security"})
        task = created["task"]
        self.assertEqual("approved", task["approval"]["status"])
        self.assertEqual(["read", "propose"], task["required_permissions"])
        self.assertEqual("qwen-proposal", task["requested_worker"])

    def test_offline_qwen_failure_appears_in_chat_history(self):
        created = self.post_json('/api/chat', {'agent': 'qwen', 'prompt': 'Are you there?',
                                                'request_type': 'explanation',
                                                'conversation_id': 'offline-visibility'})
        self.assertEqual('approved', created['task']['approval']['status'])
        deadline = time.monotonic() + 5
        history = []
        while time.monotonic() < deadline:
            history = self.get_json('/api/bootstrap')['conversations'].get('offline-visibility', [])
            if any(item['role'] == 'system' for item in history):
                break
            time.sleep(0.05)
        system_messages = [item for item in history if item['role'] == 'system']
        self.assertTrue(system_messages, 'Offline inference must not fail silently')
        self.assertEqual('qwen', system_messages[-1]['agent'])


    def test_goal_and_milestone_notes_are_persisted_without_worker_tasks(self):
        before = len(self.app.tasks())
        for kind, description in (
            ("goal", "Deliver a clear Pyrene learning journey"),
            ("milestone", "Finish the Ground Space communication prototype"),
        ):
            response = self.post_json("/api/chat", {
                "agent": "qwen", "prompt": f"/{kind} {description}",
                "conversation_id": "planning-notes",
            })
            self.assertNotIn("task", response, "Notes must not create or dispatch tasks")
            self.assertEqual("note", response["entry"]["role"])
            self.assertEqual(kind, response["entry"]["kind"])
            self.assertEqual(description, response["entry"]["content"])
            self.assertTrue(response["entry"]["note_id"].startswith("NOTE-"))
        self.assertEqual(before, len(self.app.tasks()))
        restored = GroundSpaceApp(self.state_dir, ollama_endpoint="http://127.0.0.1:1")
        records = restored.conversations["planning-notes"]
        self.assertEqual(["goal", "milestone"], [note["kind"] for note in records])
        self.assertTrue(all(note["source"] == "slash_command" for note in records))

    def test_planning_notes_survive_normal_chat_history_pruning(self):
        self.app.add_history("retain-notes", "note", "Deliver playable tutorial",
                             agent="qwen", kind="goal", note_id="NOTE-stable")
        for index in range(40):
            self.app.add_history("retain-notes", "user", f"chat message {index}", agent="qwen")
        records = self.app.conversations["retain-notes"]
        notes = [entry for entry in records if entry["role"] == "note"]
        ordinary = [entry for entry in records if entry["role"] == "user"]
        self.assertEqual(1, len(notes))
        self.assertEqual("Deliver playable tutorial", notes[0]["content"])
        self.assertEqual(24, len(ordinary))
        restored = GroundSpaceApp(self.state_dir, ollama_endpoint="http://127.0.0.1:1")
        self.assertEqual("NOTE-stable",
                         next(entry["note_id"] for entry in restored.conversations["retain-notes"]
                              if entry["role"] == "note"))

    def test_slash_messages_validate_type_and_nonempty_body(self):
        for prompt in ("/goal", "/milestone   ", "/delete everything", "/go test"):
            with self.subTest(prompt=prompt):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.post_json("/api/chat", {
                        "agent": "qwen", "prompt": prompt,
                        "conversation_id": "bad-planning-notes",
                    })
                self.assertEqual(400, caught.exception.code)
        self.assertNotIn("bad-planning-notes", self.app.conversations)

    def test_slash_notes_do_not_require_live_ollama_or_approval(self):
        response = self.post_json("/api/chat", {
            "agent": "administrator", "prompt": "/goal Create a safe local workflow",
            "conversation_id": "admin-note",
        })
        self.assertEqual("administrator", response["entry"]["agent"])
        self.assertNotIn("task", response)
        self.assertIn("Create a safe local workflow", self.app.conversation_context("admin-note"))

    def test_add_and_remove_multiple_installed_models(self):
        fake = {"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b", "granite4:3b"]}
        with patch("ground_space.webapp.probe_ollama", return_value=fake):
            catalog = self.post_json("/api/models/add", {"model": "qwen3.5:4b"})
            catalog = self.post_json("/api/models/add", {"model": "granite4:3b"})
            self.assertEqual(3, len(catalog["registered"]))
            self.assertEqual(3, len({entry["worker_id"] for entry in catalog["registered"]}))
            self.assertEqual(3, len(self.app.registered_models))
            restored = GroundSpaceApp(self.state_dir, ollama_endpoint="http://127.0.0.1:1")
            self.assertEqual(3, len(restored.registered_models))
            catalog = self.post_json("/api/models/remove", {"model": "granite4:3b"})
            self.assertEqual(2, len(catalog["registered"]))
            self.assertNotIn("granite4:3b", self.app.registered_models)

    def test_cannot_register_uninstalled_or_duplicate_models(self):
        fake = {"available": True, "models": ["qwen2.5-coder:3b"]}
        with patch("ground_space.webapp.probe_ollama", return_value=fake):
            for name in ("unknown:1b", "qwen2.5-coder:3b"):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.post_json("/api/models/add", {"model": name})
                self.assertEqual(400, caught.exception.code)

    def test_model_selection_and_performance_remain_scoped(self):
        fake = {"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]}
        with patch("ground_space.webapp.probe_ollama", return_value=fake):
            self.post_json("/api/models/add", {"model": "qwen3.5:4b"})
            result = self.post_json("/api/chat", {
                "agent": "qwen", "prompt": "Provide a short explanation",
                "model": "qwen3.5:4b", "performance": "fast",
                "request_type": "explanation", "conversation_id": "multi-model"})
            task = result["task"]
            self.assertEqual(self.app.worker_id("qwen3.5:4b"), task["requested_worker"])
            self.assertEqual(["read", "propose"], task["required_permissions"])
            self.assertEqual("qwen3.5:4b", task["payload"]["model"])
            self.assertEqual("fast", task["payload"]["performance"])
            self.assertLess(task["execution_timeout_seconds"], 100)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.post_json("/api/chat", {"agent": "qwen", "prompt": "test",
                                            "model": "qwen3.5:4b", "performance": "unlimited"})
            self.assertEqual(400, caught.exception.code)

    def test_external_model_providers_are_not_connected(self):
        catalog = self.get_json("/api/bootstrap")["models"]
        self.assertEqual({"openai", "anthropic"}, {p["id"] for p in catalog["future_providers"]})
        self.assertTrue(all(p["status"] == "not_connected" for p in catalog["future_providers"]))


    def test_local_project_folder_picker_and_registration(self):
        import urllib.parse
        project_dir = self.state_dir / "My Demo Project"
        project_dir.mkdir()
        self.app.workspaces.allowed_roots = [self.state_dir.resolve()]
        roots = self.get_json("/api/projects/browse")
        self.assertEqual(1, len(roots["folders"]))
        browsing = self.get_json("/api/projects/browse?path=" +
                                 urllib.parse.quote(str(self.state_dir), safe=""))
        self.assertIn(str(project_dir), [item["path"] for item in browsing["folders"]])
        result = self.post_json("/api/projects/add", {
            "name": "Demo", "path": str(project_dir),
        })
        self.assertEqual("Demo", result["name"])
        self.assertEqual("metadata_only", result["scope"])
        self.assertEqual(str(project_dir.resolve()), result["path"])
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.post_json("/api/projects/add", {
                "name": "Root", "path": str(self.state_dir),
            })
        self.assertEqual(400, denied.exception.code)
        restored = GroundSpaceApp(self.state_dir, ollama_endpoint="http://127.0.0.1:1")
        self.assertIn(result["id"],
                      [p["id"] for p in restored.workspaces.snapshot()["projects"]])

    def test_group_creation_membership_and_project_are_persistent(self):
        project_dir = self.state_dir / "Pyrene Project"
        project_dir.mkdir()
        self.app.workspaces.allowed_roots = [self.state_dir.resolve()]
        project = self.post_json("/api/projects/add", {
            "name": "Pyrene", "path": str(project_dir),
        })
        fake = {"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]}
        with patch("ground_space.webapp.probe_ollama", return_value=fake):
            self.post_json("/api/models/add", {"model": "qwen3.5:4b"})
            group = self.post_json("/api/groups/create", {
                "name": "Pyrene Coding",
                "models": ["qwen2.5-coder:3b", "qwen3.5:4b"],
                "project_id": project["id"],
            })
            self.assertEqual("sequential", group["execution"])
            self.assertEqual(project["id"], group["project_id"])
            self.assertEqual(2, len(group["models"]))
            restored = GroundSpaceApp(self.state_dir, ollama_endpoint="http://127.0.0.1:1")
            self.assertEqual(group["conversation_id"],
                             restored.workspaces.get_group(group["id"])["conversation_id"])
            updated = self.post_json("/api/groups/update", {
                "group_id": group["id"], "project_id": project["id"],
                "models": ["qwen3.5:4b"],
            })
            self.assertEqual(["qwen3.5:4b"], updated["models"])

    def test_group_chat_defaults_to_coordinator_and_mentions_route_to_models(self):
        fake = {"available": True, "models": ["qwen2.5-coder:3b", "qwen3.5:4b"]}
        with patch("ground_space.webapp.probe_ollama", return_value=fake):
            self.post_json("/api/models/add", {"model": "qwen3.5:4b"})
            group = self.post_json("/api/groups/create", {
                "name": "Code Review", "models": ["qwen2.5-coder:3b", "qwen3.5:4b"],
            })
            with patch.object(self.app, "_process_group") as runner:
                response = self.post_json("/api/groups/send", {
                    "group_id": group["id"], "prompt": "Propose a simple function",
                    "request_type": "code_proposal", "performance": "fast",
                })
                deadline = time.monotonic() + 2
                while not runner.called and time.monotonic() < deadline:
                    time.sleep(0.01)
            self.assertEqual(1, len(response["task_ids"]))
            records = self.app.conversations[group["conversation_id"]]
            self.assertEqual(1, len(records))
            self.assertEqual("user", records[0]["role"])
            self.assertEqual(response["task_ids"], records[0]["task_ids"])
            first_task = self.app.task(response["task_ids"][0])
            self.assertEqual("Coordinator", first_task["payload"]["speaker"])
            self.assertEqual("qwen2.5-coder:3b", first_task["payload"]["model"])
            self.assertEqual(["read", "propose"], first_task["required_permissions"])
            self.assertNotIn("path", first_task["payload"])
            with patch.object(self.app, "_process_group"):
                mentioned = self.post_json("/api/groups/send", {
                    "group_id": group["id"], "prompt": "@qwen3.5:4b Please review this",
                    "performance": "fast",
                })
            self.assertEqual(1, len(mentioned["task_ids"]))
            direct = self.app.task(mentioned["task_ids"][0])
            self.assertEqual("qwen3.5:4b", direct["payload"]["speaker"])
            self.assertEqual("qwen3.5:4b", direct["payload"]["model"])
            with self.assertRaises(urllib.error.HTTPError) as blocked:
                self.post_json("/api/groups/send", {
                    "group_id": group["id"], "prompt": "@Claude Please respond",
                })
            self.assertEqual(400, blocked.exception.code)

    def test_group_execution_is_sequential_and_in_member_order(self):
        group = self.post_json("/api/groups/create", {
            "name": "Sequential", "models": ["qwen2.5-coder:3b"],
        })
        calls = []
        with patch.object(self.app, "_process_and_record",
                          side_effect=lambda task_id: calls.append(task_id)):
            self.app._process_group(["first", "second", "third"])
        self.assertEqual(["first", "second", "third"], calls)
        self.assertEqual("sequential", group["execution"])

    def test_group_rejects_unknown_project_and_unauthorized_folder(self):
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            self.post_json("/api/groups/create", {
                "name": "Bad project", "models": ["qwen2.5-coder:3b"],
                "project_id": "project-does-not-exist",
            })
        self.assertEqual(400, invalid.exception.code)
        restricted = self.state_dir / "allowed-root"
        restricted.mkdir()
        self.app.workspaces.allowed_roots = [restricted.resolve()]
        with self.assertRaises(urllib.error.HTTPError) as folder:
            self.post_json("/api/projects/add", {
                "path": str(self.state_dir),
            })
        self.assertEqual(400, folder.exception.code)

    def test_group_notes_and_invalid_members_never_dispatch(self):
        group = self.post_json("/api/groups/create", {
            "name": "Milestones", "models": ["qwen2.5-coder:3b"],
        })
        note = self.post_json("/api/chat", {
            "agent": "group", "group_id": group["id"],
            "prompt": "/milestone Complete the communication layer",
        })
        self.assertNotIn("task", note)
        self.assertEqual("milestone", note["entry"]["kind"])
        self.assertEqual(group["conversation_id"], note["conversation_id"])
        for models in ([], ["qwen2.5-coder:3b", "qwen2.5-coder:3b"], ["missing:4b"]):
            with self.subTest(models=models):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.post_json("/api/groups/create", {
                        "name": "Invalid", "models": models,
                    })
                self.assertEqual(400, caught.exception.code)
        with self.assertRaises(urllib.error.HTTPError) as missing:
            self.post_json("/api/groups/send", {
                "group_id": "group-unknown", "prompt": "Hi",
            })
        self.assertEqual(400, missing.exception.code)

    def test_project_and_group_endpoints_require_csrf(self):
        for endpoint, body in (
            ("/api/projects/add", {"path": str(self.state_dir)}),
            ("/api/groups/create", {"name": "One", "models": ["qwen2.5-coder:3b"]}),
            ("/api/groups/send", {"group_id": "x", "prompt": "hi"}),
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.post_json(endpoint, body, csrf=False)
                self.assertEqual(403, caught.exception.code)

    def test_private_history_survives_app_restart_and_is_bounded(self):
        for index in range(30):
            self.app.add_history("bounded", "user", f"message {index}")
        restored = GroundSpaceApp(self.state_dir, ollama_endpoint="http://127.0.0.1:1")
        self.assertEqual(24, len(restored.conversations["bounded"]))
        self.assertEqual("message 29", restored.conversations["bounded"][-1]["content"])

    def test_agents_report_offline_qwen_without_breaking_ui_data(self):
        agents = {item["agent_id"]: item for item in self.bootstrap["agents"]}
        self.assertTrue(agents["administrator"]["active"])
        self.assertFalse(agents["qwen-proposal"]["active"])


if __name__ == "__main__":
    unittest.main()
