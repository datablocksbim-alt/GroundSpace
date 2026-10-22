"""GS-015 — button wiring and actual backend model/project registration contracts."""
from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.webapp import GroundSpaceApp
from ground_space.workspaces import WorkspaceRegistry


class FunctionalControlsTests(unittest.TestCase):
    def test_startup_uses_all_buttons_instead_of_crashing_on_first_element(self):
        js = (Path(__file__).resolve().parents[1] / "web/public/app.js").read_text(encoding="utf-8")
        self.assertIn("$$('.nav-button').forEach", js)
        self.assertIn("$$('.agent-choice').forEach", js)

    def test_dialog_errors_are_inside_dialog_top_layer(self):
        base = Path(__file__).resolve().parents[1] / "web/public"
        html = (base / "index.html").read_text(encoding="utf-8")
        js = (base / "app.js").read_text(encoding="utf-8")
        for element in ('id="projectDialogError"', 'id="groupDialogError"',
                        'id="modelImportStatus"'):
            self.assertIn(element, html)
        self.assertIn("showDialogError('#projectDialogError',error)", js)
        self.assertIn("showDialogError('#groupDialogError',error)", js)
        self.assertIn("already registered", js)

    def test_project_registration_persists_and_prevents_unsafe_paths(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            allowed = root / "allowed"
            folder = allowed / "Demo"
            folder.mkdir(parents=True)
            private = root / "state"
            registry = WorkspaceRegistry(private, [allowed])
            project = registry.add_project(str(folder), "My demo")
            self.assertEqual("My demo", project["name"])
            self.assertEqual("metadata_only", project["scope"])
            self.assertEqual(project["id"], WorkspaceRegistry(private, [allowed]).projects[0]["id"])
            with self.assertRaisesRegex(ValueError, "already registered"):
                registry.add_project(str(folder))
            with self.assertRaisesRegex(ValueError, "inside an allowed"):
                registry.add_project(str(allowed))
            with self.assertRaisesRegex(ValueError, "inside an allowed"):
                registry.add_project(str(root))

    def test_installed_model_registration_persists_and_rejects_missing(self):
        with TemporaryDirectory() as d:
            app = GroundSpaceApp.__new__(GroundSpaceApp)
            app.models_path = Path(d) / "models.json"
            app.lock = threading.RLock()
            app.ollama_endpoint = "http://127.0.0.1:11434"
            app.registered_models = ["qwen2.5-coder:3b"]
            app.orchestrator = SimpleNamespace(register=Mock())
            availability = {"available": True, "models": ["qwen2.5-coder:3b", "granite4:3b"]}
            with patch("ground_space.webapp.probe_ollama", return_value=availability):
                catalog = app.add_model("granite4:3b")
                self.assertIn("granite4:3b", [record["model"] for record in catalog["registered"]])
                self.assertEqual(json.loads(app.models_path.read_text())["models"],
                                 ["qwen2.5-coder:3b", "granite4:3b"])
                with self.assertRaisesRegex(ValueError, "already registered"):
                    app.add_model("granite4:3b")
                with self.assertRaisesRegex(ValueError, "must already be installed"):
                    app.add_model("model-not-installed:2b")
                self.assertNotIn("chatgpt", [r["model"] for r in catalog["registered"]])


if __name__ == "__main__":
    unittest.main()
