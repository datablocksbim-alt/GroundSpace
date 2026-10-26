"""Discovery and queue adapters for installed local AI agent runtimes.

Ground Space owns authorization and task state. These adapters launch an
installed coding agent inside the already-authorized project working directory;
they do not pretend that a raw model endpoint is an autonomous agent.
"""
from __future__ import annotations

import shutil
import subprocess
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .workers import WorkerDescriptor


@dataclass(frozen=True)
class AgentRuntimeDefinition:
    agent_id: str
    label: str
    executable: str
    provider: str
    setup_command: str
    qualified: bool = False


RUNTIMES = (
    AgentRuntimeDefinition("qwen-code", "Qwen Code", "qwen", "qwen",
                           "npm install -g @qwen-code/qwen-code@latest", True),
    AgentRuntimeDefinition("claude-code", "Claude Code", "claude", "anthropic",
                           "npm install -g @anthropic-ai/claude-code"),
    AgentRuntimeDefinition("gemini-cli", "Gemini CLI", "gemini", "google",
                           "npm install -g @google/gemini-cli"),
    AgentRuntimeDefinition("opencode", "OpenCode", "opencode", "multi-provider",
                           "npm install -g opencode-ai"),
)


def discover_agent_runtimes(run: Any = subprocess.run) -> list[dict[str, Any]]:
    """Return non-secret executable capability metadata."""
    records: list[dict[str, Any]] = []
    for definition in RUNTIMES:
        executable = shutil.which(definition.executable)
        # Discovery is part of the browser's frequently-polled bootstrap path.
        # Never execute third-party CLIs merely to render status; version/auth
        # qualification belongs to an explicit setup or health-check action.
        version = None
        authenticated = False
        if definition.agent_id == "qwen-code" and executable:
            try:
                settings = json.loads((Path.home() / ".qwen" / "settings.json").read_text(encoding="utf-8"))
                authenticated = bool(settings.get("security", {}).get("auth", {}).get("selectedType"))
            except (FileNotFoundError, OSError, ValueError, AttributeError):
                authenticated = False
            authenticated = authenticated or any(os.environ.get(name) for name in (
                "OPENAI_API_KEY", "QWENCLOUD_API_KEY", "QWENCLOUD_TOKEN_PLAN_API_KEY",
                "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"))
        records.append({
            "agent_id": definition.agent_id, "label": definition.label,
            "provider": definition.provider, "installed": bool(executable),
            "available": bool(executable and definition.qualified and authenticated),
            "authenticated": authenticated,
            "qualified": definition.qualified, "version": version,
            "setup_command": definition.setup_command,
            "full_write_option": True,
            "full_write_available": bool(executable and definition.qualified and authenticated),
            "access_boundary": "selected_project_only",
            "runtime_kind": "coding_agent",
        })
    return records


class LocalCodingAgentWorker:
    """Queue worker for a qualified, installed local coding-agent CLI."""

    def __init__(self, *, agent_id: str, executable: str, active: bool,
                 timeout_seconds: float = 600.0, model: str | None = None,
                 base_url: str | None = None):
        if agent_id != "qwen-code":
            raise ValueError("Local coding agent is not qualified")
        resolved = shutil.which(executable)
        self.descriptor = WorkerDescriptor(
            agent_id=f"agent-runtime-{agent_id}", role="local_coding_agent",
            permissions=frozenset({"read", "propose", "workspace_write", "execute"}),
            active=bool(active and resolved), provider="local_agent", model=agent_id,
            qualified=True, metadata={"project_scoped": True, "raw_model": False},
        )
        self.executable = resolved or executable
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.base_url = base_url

    def execution_request(self) -> dict[str, Any]:
        return {"kind": "local_coding_agent", "agent_id": "qwen-code",
                "executable": self.executable,
                "model": self.model, "base_url": self.base_url,
                "request_timeout_seconds": self.timeout_seconds,
                "approval_mode": "auto", "max_session_turns": 30,
                "max_tool_calls": 80}
