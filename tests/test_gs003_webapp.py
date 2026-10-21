from __future__ import annotations

import http.cookiejar
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from ground_space.webapp import GroundSpaceApp, create_server


class GS003WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.state_dir = Path(self.temporary.name)
        self.app = GroundSpaceApp(self.state_dir, "test-owner-token", ollama_endpoint="http://127.0.0.1:1")
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

    def test_approval_requires_authentication_and_dispatches_async(self):
        created = self.post_json("/api/chat", {"agent": "administrator", "prompt": "help",
                                                "conversation_id": "web-test"})
        task_id = created["task"]["task_id"]
        self.assertEqual("pending", created["task"]["approval"]["status"])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post_json(f"/api/tasks/{task_id}/approve", {}, token="wrong-token")
        self.assertEqual(401, caught.exception.code)
        accepted = self.post_json(f"/api/tasks/{task_id}/approve", {}, token="test-owner-token")
        self.assertEqual("approved", accepted["task"]["approval"]["status"])
        deadline = time.monotonic() + 4
        task = {}
        while time.monotonic() < deadline:
            task = self.get_json(f"/api/tasks/{task_id}")
            if task.get("status") == "completed":
                break
            time.sleep(0.05)
        self.assertEqual("completed", task.get("status"))
        self.assertTrue(task["result"]["read_only"])

    def test_private_history_survives_app_restart_and_is_bounded(self):
        for index in range(30):
            self.app.add_history("bounded", "user", f"message {index}")
        restored = GroundSpaceApp(self.state_dir, "new-token", ollama_endpoint="http://127.0.0.1:1")
        self.assertEqual(24, len(restored.conversations["bounded"]))
        self.assertEqual("message 29", restored.conversations["bounded"][-1]["content"])

    def test_agents_report_offline_qwen_without_breaking_ui_data(self):
        agents = {item["agent_id"]: item for item in self.bootstrap["agents"]}
        self.assertTrue(agents["administrator"]["active"])
        self.assertFalse(agents["qwen-proposal"]["active"])


if __name__ == "__main__":
    unittest.main()
