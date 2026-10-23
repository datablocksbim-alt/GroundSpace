"""GS-031 Community Edition diagnostic tests; no production dependency."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.check_gs031_readiness import inspect_repository


class CommunityReadinessTests(unittest.TestCase):
    def test_current_source_fails_standalone_dependency_gate(self):
        root = Path(__file__).resolve().parents[1]
        checks = {x["check"]: x for x in inspect_repository(root)}
        self.assertEqual(checks["standalone_queue"]["status"], "blocked")
        self.assertEqual(checks["portable_launcher"]["status"], "blocked")
        self.assertEqual(checks["public_mode_off"]["status"], "ready")
        self.assertEqual(checks["public_license"]["status"], "blocked")

    def test_gate_reports_ready_fixture_without_private_files(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ground_space").mkdir()
            (root / "tools").mkdir()
            (root / "distribution").mkdir()
            (root / "ground_space" / "legacy.py").write_text("# packaged queue", encoding="utf-8")
            (root / "ground_space" / "security.py").write_text(
                "def assert_private_owner_mode(): pass", encoding="utf-8")
            (root / "tools" / "start_ground_space.ps1").write_text(
                "python -m ground_space.webapp", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='ground-space'\n",
                                                   encoding="utf-8")
            (root / "LICENSE").write_text("fixture", encoding="utf-8")
            (root / "distribution" / "ALLOWLIST.txt").write_text("ground_space/\n",
                                                                  encoding="utf-8")
            checks = inspect_repository(root)
            self.assertEqual(len(checks), 6)
            self.assertTrue(all(x["status"] == "ready" for x in checks))

    def test_report_has_no_private_data_or_side_effects(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root / "tools" / "check_gs031_readiness.py")],
                                capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertGreater(report["blockers"], 0)
        self.assertEqual(len(report["readiness"]), 6)
        self.assertNotIn("conversations.json", result.stdout)
        self.assertNotIn("auth.json", result.stdout)


if __name__ == "__main__":
    unittest.main()
