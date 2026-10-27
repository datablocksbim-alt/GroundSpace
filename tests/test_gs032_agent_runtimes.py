"""GS-032 local coding-agent boundary and Qwen Code adapter tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ground_space.agent_runtimes import LocalCodingAgentWorker, discover_agent_runtimes
from ground_space.worker_process import local_coding_agent


class AgentDiscoveryTests(unittest.TestCase):
    @patch("ground_space.agent_runtimes.shutil.which")
    def test_every_agent_exposes_project_scoped_full_write_option(self, which):
        which.return_value = None
        records = discover_agent_runtimes()
        self.assertTrue(records)
        self.assertTrue(all(item["full_write_option"] for item in records))
        self.assertTrue(all(item["access_boundary"] == "selected_project_only" for item in records))
        self.assertTrue(all(not item["full_write_available"] for item in records))
        self.assertTrue(all(item["modes"] == ["chat", "cowork"] for item in records))

    def test_qwen_code_is_presented_as_external_account_not_ollama_install(self):
        root = Path(__file__).resolve().parents[1]
        javascript = (root / "web" / "public" / "app.js").read_text(encoding="utf-8")
        html = (root / "web" / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("item.agent_id==='qwen-code'", javascript)
        self.assertIn("Connect account", javascript)
        self.assertNotIn("Qwen Code — local coding agent", javascript)
        self.assertIn("never receives or stores your password", html)

    @patch("ground_space.agent_runtimes.shutil.which", return_value=r"C:\bin\qwen.cmd")
    def test_qwen_code_is_an_agent_runtime_not_a_raw_model(self, _which):
        worker = LocalCodingAgentWorker(agent_id="qwen-code", executable="qwen", active=True)
        self.assertEqual("local_agent", worker.descriptor.provider)
        self.assertFalse(worker.descriptor.metadata["raw_model"])
        self.assertIn("workspace_write", worker.descriptor.permissions)


class AgentExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.executable = self.project / "qwen.exe"
        self.executable.write_bytes(b"placeholder")
        self.spec = {"agent_id": "qwen-code", "executable": str(self.executable),
                     "request_timeout_seconds": 60, "approval_mode": "auto",
                     "max_session_turns": 10, "max_tool_calls": 20}

    @patch("ground_space.worker_process.subprocess.run")
    def test_chat_uses_plan_mode_and_workspace_task_uses_auto(self, run):
        def execute(command, **_kwargs):
            mode = command[command.index("--approval-mode") + 1]
            if mode == "auto":
                (self.project / "proof.txt").write_text("changed", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout=json.dumps({"response": "done"}), stderr="")
        run.side_effect = execute
        base = {"task_id": "GS-1", "correlation_id": "corr",
                "payload": {"project_path": str(self.project), "prompt": "inspect"}}
        result = local_coding_agent(self.spec, base)
        self.assertFalse(result["result"]["write_authorized"])
        self.assertEqual("plan", run.call_args.args[0][run.call_args.args[0].index("--approval-mode") + 1])

        base["payload"]["request_type"] = "workspace_change"
        result = local_coding_agent(self.spec, base)
        self.assertTrue(result["result"]["write_authorized"])
        self.assertEqual(["proof.txt"], result["result"]["changed_paths"])
        self.assertEqual("auto", run.call_args.args[0][run.call_args.args[0].index("--approval-mode") + 1])
        self.assertEqual(self.project.resolve(), run.call_args.kwargs["cwd"].resolve())

    def test_unknown_agent_is_rejected(self):
        spec = {**self.spec, "agent_id": "unqualified-agent"}
        with self.assertRaisesRegex(ValueError, "unqualified"):
            local_coding_agent(spec, {"payload": {}})


if __name__ == "__main__":
    unittest.main()
