"""GS-018: Codex is an addable agent with approved writable project tasks."""
from __future__ import annotations

import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.codex_pilot import CodexPilot
from ground_space.workspaces import WorkspaceRegistry
from ground_space.webapp import GroundSpaceApp
from ground_space.coordinator import route_group_message


class WorkspaceAgentTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.project_path=self.root/"project"
        self.project_path.mkdir()
        self.workspaces=WorkspaceRegistry(self.root/"state", [self.root])
        self.project=self.workspaces.add_project(str(self.project_path),"Test repository")
        self.run=Mock(return_value=SimpleNamespace(returncode=0, stdout="Created test.py and ran tests",stderr=""))
        self.codex=CodexPilot(self.root/"state",self.workspaces,run=self.run,
                              which=lambda name: "/mock/codex" if name=="codex" else None)

    def test_codex_must_be_explicitly_added_as_an_agent(self):
        self.assertFalse(self.codex.is_registered())
        self.assertTrue(self.codex.available())
        self.codex.set_registered(True)
        self.assertTrue(CodexPilot(self.root/"state",self.workspaces,run=self.run,
                                   which=lambda _: "/mock/codex").is_registered())
        self.codex.set_registered(False)
        self.assertFalse(self.codex.is_registered())

    def test_writable_task_requires_owner_opt_in_and_agent_registration(self):
        body={"project_id":self.project["id"],"prompt":"Create a small file", "scope":"workspace_write"}
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop("GROUND_SPACE_CODEX_WRITE_ENABLED",None)
            with self.assertRaisesRegex(ValueError,"Writable Codex"):
                self.codex.submit(body)
        with patch.dict(os.environ,{"GROUND_SPACE_CODEX_WRITE_ENABLED":"1"}):
            with self.assertRaisesRegex(ValueError,"Add Codex"):
                self.codex.submit(body)
            self.codex.set_registered(True)
            job=self.codex.submit(body)
            self.assertEqual("pending_approval",job["status"])
            self.assertEqual("workspace_write",job["scope"])
            self.assertFalse(self.run.called)

    def test_approved_writable_task_invokes_workspace_sandbox(self):
        self.codex.set_registered(True)
        with patch.dict(os.environ,{"GROUND_SPACE_CODEX_WRITE_ENABLED":"1"}):
            job=self.codex.submit({"project_id":self.project["id"],"prompt":"Edit and test",
                                   "scope":"workspace_write"})
            with patch("ground_space.codex_pilot.threading.Thread") as worker:
                result=self.codex.approve({"job_id":job["id"]})
                self.assertEqual("running",result["status"])
                worker.assert_called_once()
            self.codex._execute(job["id"])
            self.assertEqual("completed",self.codex.get(job["id"])["status"])
            args,kwargs=self.run.call_args
            self.assertIn("workspace-write",args[0])
            self.assertNotIn("danger-full-access",args[0])
            self.assertNotIn("full-auto",args[0])
            self.assertEqual(False,kwargs["shell"])
            self.assertTrue(os.path.samefile(self.project_path,kwargs["cwd"]))
            self.assertIn("Edit and test",kwargs["input"])

    def test_auto_writable_requires_opt_in_and_explicit_request(self):
        self.codex.set_registered(True)
        with patch.dict(os.environ,{"GROUND_SPACE_CODEX_WRITE_ENABLED":"1"}):
            group=self.workspaces.create_group("Agent dev",["codex"],self.project["id"],["codex"],
                {"codex":"approve_for_me"})
            with patch("ground_space.codex_pilot.threading.Thread") as worker:
                result=self.codex.submit({"project_id":self.project["id"],"prompt":"Implement a unit test",
                                         "scope":"workspace_write","group_id":group["id"]},
                                         group_auto_approval=True)
                self.assertEqual("running",result["status"])
                worker.assert_called_once()

    def test_group_can_include_codex_and_route_mention(self):
        codex_group=["qwen2.5-coder:3b","codex"]
        group=self.workspaces.create_group("Test group",codex_group,self.project["id"],codex_group,
            {"qwen2.5-coder:3b":"approve_for_me","codex":"manual"})
        self.assertEqual("manual",self.workspaces.get_group(group["id"])["approval_modes"]["codex"])
        route=route_group_message("@Codex create a test",codex_group)
        self.assertEqual(("codex",),route.models)
        self.assertFalse(route.coordinator)

    def test_codex_only_appears_in_catalog_once_added(self):
        app=GroundSpaceApp.__new__(GroundSpaceApp)
        app.codex=self.codex
        app.registered_models=["qwen2.5-coder:3b"]
        app.lock=threading.RLock()
        app.ollama_endpoint="http://127.0.0.1:1"
        app.worker_id=GroundSpaceApp.worker_id
        avail={"models":["qwen2.5-coder:3b"],"available":True}
        cat=app.catalog(availability=avail)
        self.assertIn("codex",cat["discovered"])
        self.codex.set_registered(True)
        cat=app.catalog(availability=avail)
        self.assertIn("codex",[x["model"] for x in cat["registered"]])
        self.assertNotIn("codex",cat["discovered"])

    def test_codex_does_not_accept_unknown_paths_or_permissions(self):
        self.codex.set_registered(True)
        with patch.dict(os.environ,{"GROUND_SPACE_CODEX_WRITE_ENABLED":"1"}):
            with self.assertRaisesRegex(ValueError,"Unknown project"):
                self.codex.submit({"project_id":"project-fake","scope":"workspace_write","prompt":"Edit"})
            with self.assertRaisesRegex(ValueError,"Invalid Codex operation scope"):
                self.codex.submit({"project_id":self.project["id"],"scope":"danger-full-access","prompt":"Edit"})


if __name__ == "__main__":
    unittest.main()
