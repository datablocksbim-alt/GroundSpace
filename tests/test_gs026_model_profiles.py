"""GS-026: model selection, reasoning effort, and honest unsupported-provider handling."""
from __future__ import annotations

import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.model_profiles import ModelProfiles, validated_selection
from ground_space.codex_pilot import CodexPilot
from ground_space.workspaces import WorkspaceRegistry
from ground_space.webapp import GroundSpaceApp


class ModelProfileTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.folder=Path(t.name)
        self.profiles=ModelProfiles(self.folder/"state.json")

    def test_defaults_scoped_group_and_durable_restart(self):
        self.assertEqual({"model_id":"","reasoning_effort":""},self.profiles.get())
        self.profiles.set(model_id="gpt-5.6-sol",reasoning_effort="low")
        self.profiles.set(group_id="group-123",model_id="gpt-6",reasoning_effort="high")
        again=ModelProfiles(self.folder/"state.json")
        self.assertEqual("low",again.get()["reasoning_effort"])
        self.assertEqual("gpt-6",again.get(group_id="group-123")["model_id"])
        self.assertEqual("",again.get(group_id="other")["model_id"])
        again.set(group_id="group-123",model_id="",reasoning_effort="")
        self.assertNotIn("codex:group:group-123",again.snapshot()["profiles"])

    def test_bad_model_ids_and_efforts_fail_before_persist(self):
        for value in ("a b","x;rm -rf", "-negative","",None, 10, "a"*81):
            # Empty model is intentional default, not invalid
            if value=="":continue
            with self.subTest(value=value),self.assertRaises(ValueError):
                validated_selection(value,"low")
        for effort in ("extra_high","LOW","unlimited",None, 1):
            with self.subTest(effort=effort),self.assertRaises(ValueError):
                validated_selection("gpt-5.6-sol",effort)
        with self.assertRaises(ValueError):
            self.profiles.set(group_id="../bad",model_id="safe")
        self.assertFalse((self.folder/"state.json").exists())

    def test_corrupt_settings_are_never_overwritten(self):
        self.profiles.path.write_text('{"codex:direct":{"model_id":"$(malicious)","reasoning_effort":"low"}}')
        with self.assertRaises(ValueError):
            ModelProfiles(self.profiles.path)
        self.assertIn("$(malicious)",self.profiles.path.read_text())

    def test_public_claude_cannot_be_selected_when_not_integrated(self):
        app=GroundSpaceApp.__new__(GroundSpaceApp)
        app.codex=SimpleNamespace(is_registered=Mock(return_value=True))
        app.model_profiles=self.profiles
        app.workspaces=SimpleNamespace(get_group=Mock(return_value={
            "id":"group1","models":["codex"],"project_id":"project1"
        }))
        with self.assertRaisesRegex(ValueError,"not connected"):
            app.set_model_profile({"provider":"claude","model_id":"claude-opus",
                                   "reasoning_effort":"high"})
        self.assertEqual({},self.profiles.snapshot()["profiles"])
        with self.assertRaisesRegex(ValueError,"not a member"):
            app.workspaces.get_group.return_value={"id":"group1","models":["qwen2.5-coder:3b"]}
            app.set_model_profile({"provider":"codex","group_id":"group1",
                                   "model_id":"gpt-6","reasoning_effort":"high"})
        app.workspaces.get_group.return_value={"id":"group1","models":["codex"]}
        saved=app.set_model_profile({"provider":"codex","group_id":"group1",
                                   "model_id":"gpt-5.6-sol","reasoning_effort":"medium"})
        self.assertEqual("medium",saved["reasoning_effort"])


class CodexModelInvocationTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        project=self.root/"project"
        project.mkdir()
        self.workspaces=WorkspaceRegistry(self.root/"state",[self.root])
        self.project=self.workspaces.add_project(str(project),"Test")
        self.run=Mock(return_value=SimpleNamespace(returncode=0,stdout="READY",stderr=""))
        self.codex=CodexPilot(self.root/"state",self.workspaces,
                              run=self.run,which=lambda _: "/fake/codex")
        self.codex.set_registered(True)

    def execute(self,*,model_id="",reasoning_effort=""):
        with patch.dict(os.environ,{"GROUND_SPACE_CODEX_WRITE_ENABLED":"1"}):
            job=self.codex.submit({"project_id":self.project["id"],
                "prompt":"Generate a test module","scope":"workspace_write",
                "model_id":model_id,"reasoning_effort":reasoning_effort})
            self.assertEqual("pending_approval",job["status"])
            with patch("ground_space.codex_pilot.threading.Thread"):
                self.codex.approve({"job_id":job["id"]})
            self.codex._execute(job["id"])
            self.assertEqual("completed",self.codex.get(job["id"])["status"])
            return self.run.call_args.args[0]

    def test_model_and_reasoning_flags_after_manual_approval(self):
        args=self.execute(model_id="gpt-5.6-sol",reasoning_effort="high")
        self.assertEqual(["/fake/codex","--ask-for-approval","never"],
                         args[:3])
        self.assertEqual("model_reasoning_effort=high",args[args.index("-c")+1])
        self.assertLess(args.index("-c"),args.index("exec"))
        self.assertEqual("gpt-5.6-sol",args[args.index("--model")+1])
        self.assertEqual("workspace-write",args[args.index("--sandbox")+1])
        self.assertNotIn("danger-full-access",args)

    def test_cli_defaults_do_not_set_model_or_reasoning(self):
        args=self.execute()
        self.assertNotIn("--model",args)
        self.assertNotIn("-c",args)

    def test_rejected_bad_config_does_not_spawn_process(self):
        with patch.dict(os.environ,{"GROUND_SPACE_CODEX_WRITE_ENABLED":"1"}):
            with self.assertRaises(ValueError):
                self.codex.submit({"project_id":self.project["id"],
                 "prompt":"Write","scope":"workspace_write",
                 "model_id":"gpt-5.6-sol;inject","reasoning_effort":"high"})
        self.run.assert_not_called()


if __name__=="__main__":
    unittest.main()
