"""GS-016: owner Codex approval policy and strictly read-only subprocess behavior."""
import json
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.codex_pilot import CodexPilot


class FakeWorkspaces:
    def __init__(self, project):
        self.project = project
    def get_project(self, project_id):
        if project_id != self.project["id"]:
            raise ValueError("Unknown project")
        return self.project


class CodexPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.workspace = self.path / "workspace"
        self.workspace.mkdir()
        self.project = {"id": "project-1", "name": "Ground Space", "path": str(self.workspace)}
        self.run = Mock(return_value=SimpleNamespace(returncode=0,stdout="Found 2 issues",stderr=""))
        self.pilot = CodexPilot(self.path / "state", FakeWorkspaces(self.project),
                                run=self.run, which=lambda _: "/usr/bin/codex")

    def test_manual_is_default_and_requires_approval(self):
        job = self.pilot.submit({"project_id":"project-1","prompt":"Review tests"})
        self.assertEqual("pending_approval", job["status"])
        self.assertEqual(0, self.run.call_count)
        with patch("ground_space.codex_pilot.threading.Thread") as worker:
            result = self.pilot.approve({"job_id":job["id"]})
            self.assertEqual("running",result["status"])
            worker.assert_called_once()
            with self.assertRaisesRegex(ValueError, "not awaiting approval"):
                self.pilot.approve({"job_id":job["id"]})
        self.pilot._execute(job["id"])
        self.assertEqual("completed",self.pilot.get(job["id"])["status"])
        args,kwargs=self.run.call_args
        self.assertIn("read-only",args[0])
        self.assertIn("--ask-for-approval",args[0])
        self.assertIn("never",args[0])
        self.assertNotIn("workspace-write",args[0])
        self.assertEqual(False,kwargs["shell"])
        self.assertTrue(os.path.samefile(self.workspace, kwargs["cwd"]))
        self.assertEqual("Found 2 issues",self.pilot.get(job["id"])["answer"])

    def test_auto_read_only_runs_without_a_second_click(self):
        self.pilot.set_policy({"mode":"auto_read_only","project_id":"project-1"})
        with patch("ground_space.codex_pilot.threading.Thread") as worker:
            item=self.pilot.submit({"project_id":"project-1","prompt":"Review app"})
            self.assertEqual("running",item["status"])
            worker.assert_called_once()
        self.pilot._execute(item["id"])
        self.assertEqual("completed",self.pilot.get(item["id"])["status"])

    def test_project_override_does_not_modify_owner_default(self):
        self.pilot.set_policy({"mode":"disabled","project_id":"project-1"})
        self.assertEqual("manual",self.pilot.mode(None))
        self.assertEqual("disabled",self.pilot.mode("project-1"))
        self.assertEqual("disabled",CodexPilot(self.path/"state",FakeWorkspaces(self.project),
                          run=self.run,which=lambda _: "/usr/bin/codex").mode("project-1"))
        with self.assertRaisesRegex(ValueError,"disabled"):
            self.pilot.submit({"project_id":"project-1","prompt":"Review app"})

    def test_bad_modes_and_unknown_projects_are_rejected(self):
        for mode in ["full_auto","never","workspace-write","auto_write","danger-full-access"]:
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,"Invalid approval mode"):
                self.pilot.set_policy({"mode":mode,"project_id":"project-1"})
        with self.assertRaisesRegex(ValueError,"Unknown project"):
            self.pilot.set_policy({"mode":"auto_read_only","project_id":"bad-project"})
        with self.assertRaisesRegex(ValueError,"Unknown project"):
            self.pilot.submit({"project_id":"bad-project","prompt":"Anything"})

    def test_reject_and_disabled_pending_do_not_execute(self):
        entry=self.pilot.submit({"project_id":"project-1","prompt":"Propose review"})
        self.pilot.reject({"job_id":entry["id"]})
        self.assertEqual("rejected",self.pilot.get(entry["id"])["status"])
        with self.assertRaisesRegex(ValueError,"not awaiting approval"):
            self.pilot.approve({"job_id":entry["id"]})
        entry=self.pilot.submit({"project_id":"project-1","prompt":"Review later"})
        self.pilot.set_policy({"mode":"disabled","project_id":"project-1"})
        with self.assertRaisesRegex(ValueError,"disabled"):
            self.pilot.approve({"job_id":entry["id"]})
        self.assertFalse(self.run.called)

    def test_only_one_codex_review_can_run_and_pending_queue_is_bounded(self):
        first=self.pilot.submit({"project_id":"project-1","prompt":"First"})
        second=self.pilot.submit({"project_id":"project-1","prompt":"Second"})
        with patch("ground_space.codex_pilot.threading.Thread"):
            self.pilot.approve({"job_id":first["id"]})
            with self.assertRaisesRegex(ValueError,"already running"):
                self.pilot.approve({"job_id":second["id"]})
        for i in range(9):
            self.pilot.submit({"project_id":"project-1","prompt":f"Review {i}"})
        with self.assertRaisesRegex(ValueError,"queue is full"):
            self.pilot.submit({"project_id":"project-1","prompt":"Review beyond limit"})

    def test_cli_missing_never_starts_job(self):
        pilot=CodexPilot(self.path/"other",FakeWorkspaces(self.project),
                         run=self.run,which=lambda _: None)
        self.assertFalse(pilot.snapshot()["cli_installed"])
        with self.assertRaisesRegex(ValueError,"not installed"):
            pilot.submit({"project_id":"project-1","prompt":"Review"})

    def test_restart_marks_inflight_job_interrupted(self):
        job=self.pilot.submit({"project_id":"project-1","prompt":"Review"})
        with patch("ground_space.codex_pilot.threading.Thread"):
            self.pilot.approve({"job_id":job["id"]})
        other=CodexPilot(self.path/"state",FakeWorkspaces(self.project),
                         run=self.run,which=lambda _: "/usr/bin/codex")
        self.assertEqual("interrupted",other.get(job["id"])["status"])

    def test_provider_exposes_only_local_owner_pilot(self):
        status=self.pilot.snapshot()
        self.assertEqual("workspace_write_if_owner_approved",status["max_permission"])
        self.assertEqual("single_owner_pilot",status["scope"])
        self.assertFalse(status["per_user_accounts"])


if __name__=="__main__":
    unittest.main()
