"""No test imports or executes Qwen's source on the host."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

from ground_space.proposal_validation import validate_proposal


class SafeValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "candidate.py"
        self.source.write_text("def schedule_tasks(tasks):\n    return []\n", encoding="utf-8")

    def test_missing_docker_blocks_without_execution(self):
        with patch("ground_space.proposal_validation.shutil.which", return_value=None), \
             patch("ground_space.proposal_validation.subprocess.run") as run:
            report = validate_proposal(self.source)
        self.assertEqual("blocked", report["status"])
        run.assert_not_called()

    def test_bad_python_blocks_before_docker(self):
        self.source.write_text("def schedule_tasks(:", encoding="utf-8")
        with patch("ground_space.proposal_validation.shutil.which") as which:
            report = validate_proposal(self.source)
        self.assertEqual("failed", report["status"])
        which.assert_not_called()

    def test_missing_function_blocks_before_docker(self):
        self.source.write_text("def unrelated():\n    pass\n", encoding="utf-8")
        with patch("ground_space.proposal_validation.shutil.which") as which:
            report = validate_proposal(self.source)
        self.assertEqual("failed", report["status"])
        which.assert_not_called()

    def test_missing_cached_image_fails_closed(self):
        with patch("ground_space.proposal_validation.shutil.which", return_value="docker"), \
             patch("ground_space.proposal_validation.subprocess.run", return_value=CompletedProcess([], 1)) as run:
            report = validate_proposal(self.source)
        self.assertEqual("blocked", report["status"])
        self.assertEqual(1, run.call_count)
        self.assertEqual(["docker", "image", "inspect", "python:3.11-alpine"], run.call_args.args[0])

    def test_only_docker_runs_proposal_and_container_restrictions_enforced(self):
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            if args[1] == "image":
                return CompletedProcess(args, 0, "image cached", "")
            return CompletedProcess(args, 0, "", "Ran 9 tests in 0.001s\n\nOK\n")

        with patch("ground_space.proposal_validation.shutil.which", return_value="docker"), \
             patch("ground_space.proposal_validation.subprocess.run", side_effect=fake_run):
            report = validate_proposal(self.source)
        self.assertEqual("passed", report["status"])
        command, kwargs = calls[1]
        self.assertEqual("docker", command[0])
        for required in ("--network", "none", "--read-only", "--cap-drop", "ALL",
                         "--pull", "never", "--pids-limit", "--memory", "--cpus",
                         "--user", "65534:65534"):
            self.assertIn(required, command)
        self.assertEqual(30, kwargs["timeout"])

    def test_failing_tests_are_not_accepted(self):
        side_effect = [
            CompletedProcess([], 0, "", ""),
            CompletedProcess([], 1, "", "Ran 9 tests\nFAILED (failures=1)"),
        ]
        with patch("ground_space.proposal_validation.shutil.which", return_value="docker"), \
             patch("ground_space.proposal_validation.subprocess.run", side_effect=side_effect):
            report = validate_proposal(self.source)
        self.assertEqual("failed", report["status"])

    def test_timeout_blocks_and_attempts_container_cleanup(self):
        import subprocess
        calls = []
        def fake_run(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                return CompletedProcess(args, 0, "", "")
            if len(calls) == 2:
                raise subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=30)
            return CompletedProcess(args, 0, "removed", "")
        with patch("ground_space.proposal_validation.shutil.which", return_value="docker"), \
             patch("ground_space.proposal_validation.subprocess.run", side_effect=fake_run):
            report = validate_proposal(self.source)
        self.assertEqual("blocked", report["status"])
        self.assertEqual(["docker", "rm", "-f"], calls[2][:3])


if __name__ == "__main__":
    unittest.main()
