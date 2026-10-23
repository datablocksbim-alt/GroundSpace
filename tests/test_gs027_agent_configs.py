"""GS-027 persistent agent controls: conservative provider boundaries and defaults."""
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from ground_space.agent_configs import AgentConfigs, default_config, validate_config
from ground_space.model_profiles import ModelProfiles
from ground_space.webapp import GroundSpaceApp

LOCAL = ["qwen2.5-coder:3b", "qwen3.5:4b", "granite4:3b"]


class AgentConfigurationTests(unittest.TestCase):
    def setUp(self):
        t = TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path = Path(t.name) / "private" / "agent_configs.json"
        self.configs = AgentConfigs(self.path)

    def test_defaults_are_safe_and_compatible(self):
        self.assertEqual("balanced", self.configs.get(LOCAL[0])["level"])
        self.assertEqual("auto_read_only", self.configs.get(LOCAL[0])["approval"])
        self.assertNotIn("workspace_write", self.configs.get(LOCAL[0])["access"])
        self.assertEqual("manual", self.configs.get("codex")["approval"])
        self.assertEqual("", self.configs.get("codex")["model_id"])

    def test_persisted_configuration_survives_restart_without_changing_identity(self):
        config = {"model_id": LOCAL[1], "level": "detailed", "access": ["read", "review"],
                  "approval": "auto_read_only"}
        self.configs.save(LOCAL[0], config, LOCAL)
        after = AgentConfigs(self.path)
        self.assertEqual(LOCAL[1], after.get(LOCAL[0])["model_id"])
        self.assertEqual("detailed", after.get(LOCAL[0])["level"])
        self.assertEqual(["read", "review"], after.get(LOCAL[0])["access"])
        self.assertEqual(LOCAL[0], LOCAL[0])  # Agent member ID is unchanged.
        self.assertNotIn(LOCAL[1], after.entries)

    def test_codex_reasoning_and_access_survive_restart(self):
        value = {"model_id": "gpt-6.1-sol", "level": "high",
                 "access": ["read", "review"], "approval": "manual"}
        self.configs.save("codex", value, LOCAL)
        self.assertEqual(value, AgentConfigs(self.path).get("codex"))

    def test_provider_cannot_gain_unsupported_permissions_or_models(self):
        bad = [
            {"model_id": LOCAL[0], "level": "balanced", "access": ["read", "workspace_write"], "approval": "auto_read_only"},
            {"model_id": "claude-sonnet", "level": "balanced", "access": ["read"], "approval": "auto_read_only"},
            {"model_id": LOCAL[0], "level": "high", "access": ["read"], "approval": "auto_read_only"},
            {"model_id": LOCAL[0], "level": "balanced", "access": ["read"], "approval": "manual"},
        ]
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.configs.save(LOCAL[0], candidate, LOCAL)
        with self.assertRaises(ValueError):
            self.configs.save("claude", {"model_id": "claude", "level": "high", "access": ["read"], "approval": "manual"}, LOCAL)
        with self.assertRaises(ValueError):
            self.configs.save("codex", {"model_id": "gpt-6.1-sol", "level": "high",
                "access": ["workspace_write"], "approval": "manual"}, LOCAL)
        self.assertFalse(self.path.exists(), "Rejected settings must not mutate durable state")

    def test_bad_disk_state_fails_closed_without_overwrite(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"schema_version":1,"agents":{"qwen":{}}}', encoding="utf-8")
        with self.assertRaises(ValueError):
            AgentConfigs(self.path)
        self.assertEqual('{"schema_version":1,"agents":{"qwen":{}}}', self.path.read_text())

    def test_snapshot_is_agent_scoped_and_future_providers_disconnected(self):
        catalog = self.configs.snapshot(LOCAL, True)
        self.assertEqual(set(LOCAL + ["codex"]), set(catalog["profiles"]))
        self.assertFalse(next(x for x in catalog["providers"] if x["id"] == "anthropic")["connected"])
        self.assertFalse(next(x for x in catalog["providers"] if x["id"] == "grok")["connected"])


class AppAgentRoutingTests(unittest.TestCase):
    def setUp(self):
        t = TemporaryDirectory()
        self.addCleanup(t.cleanup)
        path = Path(t.name)
        self.app = GroundSpaceApp.__new__(GroundSpaceApp)
        self.app.lock = threading.RLock()
        self.app.registered_models = list(LOCAL)
        self.app.agent_configs = AgentConfigs(path / "configs.json")
        self.app.model_profiles = ModelProfiles(path / "model_profiles.json")
        self.app.codex = Mock()
        self.app.codex.is_registered.return_value = True

    def test_saved_agent_defaults_used_when_no_legacy_direct_or_group_override(self):
        self.app.save_agent_config({"agent_id": "codex", "model_id": "gpt-6.1-sol",
            "level": "medium", "access": ["read", "review"], "approval": "manual"})
        self.assertEqual({"model_id": "gpt-6.1-sol", "reasoning_effort": "medium"}, self.app.codex_selection())
        self.assertEqual({"model_id": "gpt-6.1-sol", "reasoning_effort": "medium"},
                         self.app.codex_selection(group_id="group-001"))
        self.app.model_profiles.set(group_id="group-001", model_id="gpt-5.6-sol", reasoning_effort="high")
        self.assertEqual("gpt-5.6-sol", self.app.codex_selection(group_id="group-001")["model_id"])
        self.assertEqual("gpt-6.1-sol", self.app.codex_selection(group_id="group-002")["model_id"])

    def test_saved_config_blocks_future_write_tasks(self):
        self.app.save_agent_config({"agent_id": "codex", "model_id": "gpt-6.1-sol",
            "level": "high", "access": ["read", "review"], "approval": "manual"})
        self.app.require_agent_access("codex", write=False)
        with self.assertRaisesRegex(ValueError, "workspace_write"):
            self.app.require_agent_access("codex", write=True)
        self.app.save_agent_config({"agent_id": "codex", "model_id": "gpt-6.1-sol",
            "level": "high", "access": ["read", "review"], "approval": "disabled"})
        with self.assertRaisesRegex(ValueError, "disabled"):
            self.app.require_agent_access("codex")

    def test_codex_save_failure_restores_previous_approval(self):
        self.app.codex.mode.return_value = "manual"
        with unittest.mock.patch.object(self.app.agent_configs, "save",
                                         side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.app.save_agent_config({
                    "agent_id": "codex", "model_id": "gpt-6.1-sol",
                    "level": "high", "access": ["read", "review"],
                    "approval": "disabled"})
        self.assertEqual(
            [unittest.mock.call({"mode": "disabled", "project_id": None}),
             unittest.mock.call({"mode": "manual", "project_id": None})],
            self.app.codex.set_policy.call_args_list)
        self.assertNotIn("codex", self.app.agent_configs.entries)

    def test_failed_policy_save_does_not_touch_agent_profile(self):
        self.app.codex.set_policy.side_effect = OSError("policy is read-only")
        with self.assertRaisesRegex(OSError, "policy is read-only"):
            self.app.save_agent_config({
                "agent_id": "codex", "model_id": "gpt-6.1-sol",
                "level": "medium", "access": ["read", "review"],
                "approval": "manual"})
        self.assertNotIn("codex", self.app.agent_configs.entries)

    def test_model_selection_cannot_register_new_ollama_worker(self):
        with self.assertRaisesRegex(ValueError, "registered Ollama"):
            self.app.save_agent_config({"agent_id": LOCAL[0], "model_id": "unknown:7b",
                "level": "fast", "access": ["chat", "read"], "approval": "auto_read_only"})
        self.assertEqual(LOCAL[0], self.app.agent_config(LOCAL[0])["model_id"])




class GroupAgentDispatchTests(unittest.TestCase):
    def setUp(self):
        from ground_space.workspaces import WorkspaceRegistry
        from tests.test_gs017_group_approvals import FakeAdministrator
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.app=GroundSpaceApp.__new__(GroundSpaceApp)
        self.app.lock=threading.RLock()
        self.app.group_dispatch_lock=threading.Lock()
        self.app.ollama_endpoint="http://127.0.0.1:1"
        self.app.registered_models=list(LOCAL[:2])
        self.app.codex=SimpleNamespace(is_registered=Mock(return_value=False))
        self.app.workspaces=WorkspaceRegistry(self.root/"private",[self.root])
        self.app.agent_configs=AgentConfigs(self.root/"private"/"agent_configs.json")
        self.app.administrator=FakeAdministrator()
        self.app.conversations={}
        self.app.history_path=self.root/"private"/"conversations.json"
        self.app._register_worker=Mock()
        self.app.worker_id=GroundSpaceApp.worker_id
        self.group=self.app.create_group({"name":"Test group",
          "models":[LOCAL[0]],"project_id":None})

    def test_group_uses_saved_model_and_level_without_changing_agent_identity(self):
        from unittest.mock import patch
        self.app.save_agent_config({"agent_id":LOCAL[0],"model_id":LOCAL[1],
            "level":"fast","access":["chat","read","propose","review"],
            "approval":"auto_read_only"})
        with patch("ground_space.webapp.probe_ollama",return_value={"available":False,"models":[]}), \
             patch("ground_space.webapp.threading.Thread"):
            result=self.app.submit_group({"group_id":self.group["id"],"prompt":"Hello"})
        task=self.app.administrator.status(result["task_ids"][0])
        self.assertEqual(LOCAL[1],task["payload"]["model"])
        self.assertEqual(LOCAL[0],task["payload"]["agent_id"])
        self.assertEqual("fast",task["payload"]["performance"])
        self.assertEqual(GroundSpaceApp.worker_id(LOCAL[1]),task["requested_worker"])
        self.assertEqual("approved",task["approval"]["status"])
        self.app.save_agent_config({"agent_id":LOCAL[0],"model_id":LOCAL[0],
            "level":"detailed","access":["chat","read","propose","review"],
            "approval":"auto_read_only"})
        self.assertEqual(LOCAL[1],self.app.administrator.status(task["task_id"])["payload"]["model"])

    def test_disabling_agent_prevents_group_dispatch_without_new_task(self):
        from unittest.mock import patch
        self.app.save_agent_config({"agent_id":LOCAL[0],"model_id":LOCAL[0],
            "level":"balanced","access":["chat","read","propose"],
            "approval":"disabled"})
        with patch("ground_space.webapp.probe_ollama",return_value={"available":False,"models":[]}):
            with self.assertRaisesRegex(ValueError,"disabled"):
                self.app.submit_group({"group_id":self.group["id"],"prompt":"Hello"})
        self.assertEqual({},self.app.administrator.tasks)

if __name__ == "__main__":
    unittest.main()
