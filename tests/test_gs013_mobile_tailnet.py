"""GS-013: Coordinator-era Ground Space remains private and CSRF-protected over Tailscale."""
from __future__ import annotations

import http.cookiejar
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ground_space.webapp import GroundSpaceApp, configured_tailscale_origin, create_server


class TailnetOriginTests(unittest.TestCase):
    def test_no_remote_origin_by_default(self):
        with patch.dict(os.environ, {"GROUND_SPACE_TAILSCALE_ORIGIN": ""}):
            self.assertIsNone(configured_tailscale_origin())

    def test_only_exact_tailscale_https_origins_allowed(self):
        for value in (
            "http://asus.example.ts.net", "https://bad.example.com",
            "https://asus.example.ts.net/", "https://asus.example.ts.net:8080",
            "https://*.example.ts.net", "https://asus.example.ts.net/path",
            " https://asus.example.ts.net:8443", "https://asus.example.ts.net:8443/",
        ):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"GROUND_SPACE_TAILSCALE_ORIGIN": value}):
                    with self.assertRaises(ValueError):
                        configured_tailscale_origin()
        for value in ("https://asus.example.ts.net", "https://asus.example.ts.net:8443"):
            with patch.dict(os.environ, {"GROUND_SPACE_TAILSCALE_ORIGIN": value}):
                self.assertEqual(value, configured_tailscale_origin())

    def test_remote_chat_note_requires_allowlisted_origin_and_csrf(self):
        with TemporaryDirectory() as directory:
            app = GroundSpaceApp(Path(directory), ollama_endpoint="http://127.0.0.1:1")
            remote_origin = "https://asus.example.ts.net:8443"
            with patch.dict(os.environ, {"GROUND_SPACE_TAILSCALE_ORIGIN": remote_origin}):
                server = create_server(app, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                local_origin = f"http://127.0.0.1:{server.server_port}"
                self.assertIn(local_origin, server.allowed_origins)
                self.assertIn(remote_origin, server.allowed_origins)
                jar = http.cookiejar.CookieJar()
                client = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                   urllib.request.HTTPCookieProcessor(jar))
                with client.open(local_origin + "/api/bootstrap", timeout=8) as response:
                    bootstrap = json.load(response)
                body = json.dumps({
                    "agent": "administrator",
                    "prompt": "/goal Confirm mobile chat access",
                    "conversation_id": "gs012",
                }).encode("utf-8")
                def post(origin, csrf=True):
                    headers = {"Content-Type": "application/json", "Origin": origin}
                    if csrf:
                        headers["X-Ground-Space-CSRF"] = bootstrap["csrf_token"]
                    request = urllib.request.Request(
                        local_origin + "/api/chat", data=body,
                        headers=headers, method="POST",
                    )
                    return client.open(request, timeout=8)
                for origin, csrf in (
                    ("https://other.example.ts.net:8443", True),
                    (remote_origin, False),
                ):
                    with self.subTest(origin=origin, csrf=csrf):
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            post(origin, csrf=csrf)
                        self.assertEqual(403, caught.exception.code)
                with post(remote_origin) as response:
                    self.assertEqual(201, response.status)
                    created = json.load(response)
                self.assertEqual("goal", created["entry"]["kind"])
                self.assertNotIn("task", created, "Administrator planning note must not execute a worker")
                self.assertEqual("recorded", created["entry"]["planning_status"])
                with self.assertRaises(urllib.error.HTTPError) as forbidden:
                    post("http://127.0.0.1:8765")
                self.assertEqual(403, forbidden.exception.code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
