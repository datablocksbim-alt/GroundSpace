"""GS-026: real scoped model/effort settings for Codex CLI and Co-work."""
from __future__ import annotations
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock,patch

from ground_space.model_profiles import ModelProfiles,validated_selection
from ground_space.workspaces import WorkspaceRegistry
from ground_space.codex_pilot import CodexPilot
from ground_space.webapp import GroundSpaceApp


class ModelProfileTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.profiles=ModelProfiles(self.root/"private"/"model_profiles.json")

    def test_default_and_group_preferences_persist_separately(self):
        self.assertEqual({"model_id":"","reasoning_effort":""},self.profiles.get())
        self.profiles.set(model_id="gpt-5.6-sol",reasoning_effort="high")
        self.profiles.set(group_id="group-01",model_id="gpt-6.1-sol",reasoning_effort="low")
        again=ModelProfiles(self.profiles.path)
        self.assertEqual("gpt-5.6-sol",again.get()["model_id"])
        self.assertEqual("high",again.get()["reasoning_effort"])
        self.assertEqual("gpt-6.1-sol",again.get(group_id="group-01")["model_id"])
        self.assertEqual("low",again.get(group_id="group-01")["reasoning_effort"])
        self.assertEqual("",again.get(group_id="group-02")["model_id"])

    def test_default_resets_without_affecting_other_groups(self):
        self.profiles.set(model_id="gpt-5.6-sol",reasoning_effort="medium")
        self.profiles.set(group_id="g1",model_id="gpt-6.1-sol",reasoning_effort="high")
        self.profiles.set()
        self.assertEqual("",ModelProfiles(self.profiles.path).get()["model_id"])
        self.assertEqual("high",self.profiles.get(group_id="g1")["reasoning_effort"])

    def test_invalid_provider_tokens_flags_and_paths_rejected(self):
        bad=["-c model_reasoning_effort=high","../../secrets","hello; rm -rf /",
             "http://example.com","m"*81,"","abc def"]
        for value in bad:
            if not value:continue
            with self.subTest(model=value),self.assertRaises(ValueError):
                validated_selection(value,"low")
        for effort in ("xhigh","max","none","--sandbox","HIGH",None):
            with self.subTest(effort=effort),self.assertRaises(ValueError):
                validated_selection("gpt-5.6-sol",effort)
        with self.assertRaises(ValueError):
            self.profiles.set(group_id="../private",model_id="gpt-5.6-sol")
        with self.assertRaises(ValueError):
            ModelProfiles(self.root/"no"/"malformed.json") if False else validated_selection("gpt-5.6-sol","full-auto")

    def test_corruption_does_not_overwrite_existing_state(self):
        self.profiles.path.parent.mkdir(parents=True,exist_ok=True)
        original='{"openai:direct":{"model_id":"test","reasoning_effort":"high"}}'
        self.profiles.path.write_text(original,encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"unknown provider"):
            ModelProfiles(self.profiles.path)
        self.assertEqual(original,self.profiles.path.read_text(encoding="utf-8"))


class CodexModelInvocationTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.workspace=WorkspaceRegistry(self.root/"state",[self.root])
        self.project_dir=self.root/"project";self.project_dir.mkdir()
        self.project=self.workspace.add_project(str(self.project_dir),"Test")
        self.run=Mock(return_value=SimpleNamespace(returncode=0,stdout="OK",stderr=""))
        self.codex=CodexPilot(self.root/"state",self.workspace,run=self.run,
                              which=lambda n:"/mock/codex" if n=="codex" else None)
        self.codex.set_registered(True)

    def execute(self,**selection):
        with patch.dict(os.environ,{"GROUND_SPACE_CODEX_WRITE_ENABLED":"1",
                                     "GROUND_SPACE_DEPLOYMENT_MODE":"owner_private",
                                     "GROUND_SPACE_PUBLIC_USERS":"0"}):
            job=self.codex.submit({"project_id":self.project["id"],"prompt":"Write a disposable test",
                "scope":"workspace_write",**selection})
            with patch("ground_space.codex_pilot.threading.Thread"):
                self.codex.approve({"job_id":job["id"]})
            self.codex._execute(job["id"])
            return self.codex.get(job["id"]),self.run.call_args.args[0]

    def test_explicit_model_and_effort_reach_real_subprocess_arguments(self):
        job,args=self.execute(model_id="gpt-5.6-sol",reasoning_effort="high")
        self.assertEqual("completed",job["status"])
        self.assertEqual("gpt-5.6-sol",job["model_id"])
        self.assertIn("--model",args)
        self.assertEqual("gpt-5.6-sol",args[args.index("--model")+1])
        self.assertIn("-c",args)
        self.assertEqual("model_reasoning_effort=high",args[args.index("-c")+1])
        self.assertLess(args.index("-c"),args.index("exec"))
        self.assertIn("workspace-write",args)
        self.assertNotIn("danger-full-access",args)

    def test_default_uses_codex_cli_default_model_and_effort(self):
        job,args=self.execute()
        self.assertEqual("",job["model_id"])
        self.assertNotIn("--model",args)
        self.assertNotIn("-c",args)

    def test_malformed_model_does_not_create_or_execute_job(self):
        with self.assertRaises(ValueError):
            self.codex.submit({"project_id":self.project["id"],"prompt":"Hello",
                "model_id":"--danger-full-access"})
        self.assertEqual([],self.codex.jobs)
        self.run.assert_not_called()

    def test_backend_rejects_unconnected_provider_and_nonmember_group(self):
        app=GroundSpaceApp.__new__(GroundSpaceApp)
        app.codex=self.codex
        app.model_profiles=ModelProfiles(self.root/"private"/"settings.json")
        group={"models":["qwen2.5-coder:3b"]}
        app.workspaces=SimpleNamespace(get_group=lambda _:group)
        with self.assertRaisesRegex(ValueError,"not connected"):
            app.set_model_profile({"provider":"claude","model_id":"claude-sonnet-4-6"})
        with self.assertRaisesRegex(ValueError,"not a member"):
            app.set_model_profile({"provider":"codex","group_id":"room1","model_id":"gpt-5.6-sol"})
        app.set_model_profile({"provider":"codex","model_id":"gpt-5.6-sol","reasoning_effort":"medium"})
        self.assertEqual("medium",app.codex_selection()["reasoning_effort"])


if __name__=="__main__":
    unittest.main()
