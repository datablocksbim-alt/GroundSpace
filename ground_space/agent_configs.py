"""GS-027 durable owner-only agent defaults, separate from provider authority.

Legacy model IDs remain stable group/member identifiers. Model selection changes
the provider's execution model only; a UI checkbox cannot grant filesystem rights.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from .model_profiles import validated_selection
from .workers import PERFORMANCE_PRESETS, valid_model_name

APPROVALS = frozenset({"manual", "auto_read_only", "disabled"})
LOCAL_ACCESS = frozenset({"chat", "read", "propose", "review"})
CODEX_ACCESS = frozenset({"read", "review", "workspace_write"})
MAX_RECORDS = 32


def default_config(agent_id: str) -> dict[str, Any]:
    if agent_id == "codex":
        return {"model_id": "", "level": "", "access": ["read", "review", "workspace_write"],
                "approval": "manual"}
    return {"model_id": agent_id, "level": "balanced",
            "access": ["chat", "read", "propose", "review"],
            "approval": "auto_read_only"}


def validate_config(agent_id: str, value: Any, registered: list[str]) -> dict[str, Any]:
    if not isinstance(agent_id, str) or (agent_id != "codex" and agent_id not in registered):
        raise ValueError("Agent is not registered")
    if not isinstance(value, dict) or set(value) != {"model_id", "level", "access", "approval"}:
        raise ValueError("Model, access, level and approval are required")
    model, level, access, approval = (value[k] for k in ("model_id", "level", "access", "approval"))
    if not isinstance(approval, str) or approval not in APPROVALS:
        raise ValueError("Invalid approval setting")
    if agent_id != "codex" and approval == "manual":
        raise ValueError("Direct local agents only support automatic read-only or Off; use group Ask me for manual review")
    if not isinstance(access, list) or not access or len(access) != len(set(map(str, access))):
        raise ValueError("Choose unique supported access capabilities")
    if agent_id == "codex":
        validated_selection(model, level)
        allowed = CODEX_ACCESS
    else:
        if not isinstance(model, str) or model not in registered or not valid_model_name(model):
            raise ValueError("Select a registered Ollama model")
        if not isinstance(level, str) or level not in PERFORMANCE_PRESETS:
            raise ValueError("Choose a supported local response level")
        allowed = LOCAL_ACCESS
    if any(not isinstance(item, str) or item not in allowed for item in access):
        raise ValueError("Access exceeds the agent provider's supported capabilities")
    if agent_id == "codex" and not {"read", "review"}.issubset(access) and "workspace_write" in access:
        raise ValueError("Workspace coding also requires read and review access")
    return {"model_id": model, "level": level, "access": sorted(access),
            "approval": approval}


class AgentConfigs:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            obj = {"schema_version": 1, "agents": {}}
        except (OSError, ValueError) as exc:
            raise ValueError("Agent configuration is unreadable; preserve original state") from exc
        if not isinstance(obj, dict) or obj.get("schema_version") != 1 or not isinstance(obj.get("agents"), dict):
            raise ValueError("Agent configuration schema is invalid")
        if len(obj["agents"]) > MAX_RECORDS:
            raise ValueError("Too many agent configurations")
        for key, item in obj["agents"].items():
            if not isinstance(key, str) or not isinstance(item, dict) or set(item) != {"model_id", "level", "access", "approval"}:
                raise ValueError("Invalid persisted agent configuration; preserve original file")
        self.entries = obj["agents"]

    def get(self, agent_id: str) -> dict[str, Any]:
        with self.lock:
            value = self.entries.get(agent_id, default_config(agent_id))
            return {**value, "access": list(value["access"])}

    def save(self, agent_id: str, value: dict[str, Any], registered: list[str]) -> dict[str, Any]:
        normalized = validate_config(agent_id, value, registered)
        with self.lock:
            updated = dict(self.entries)
            updated[agent_id] = normalized
            if len(updated) > MAX_RECORDS:
                raise ValueError("Agent configuration limit reached")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_name("." + self.path.name + "." + secrets.token_hex(6) + ".tmp")
            try:
                temp.write_text(json.dumps({"schema_version": 1, "agents": updated},
                                           indent=2, sort_keys=True), encoding="utf-8")
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)
            self.entries = updated
        return self.get(agent_id)

    def snapshot(self, registered: list[str], codex_registered: bool) -> dict[str, Any]:
        names = list(registered) + (["codex"] if codex_registered else [])
        return {"schema_version": 1, "profiles": {name: self.get(name) for name in names},
                # Registration is not provider authentication. Codex CLI
                # confirms model entitlement/login on actual execution.
                "providers": [{"id": "ollama", "status": "local_adapter"},
                              {"id": "openai_codex_cli",
                               "status": "registered_cli" if codex_registered else "not_registered",
                               "authentication": "checked_on_execution"},
                              {"id": "anthropic", "connected": False},
                              {"id": "grok", "connected": False}]}
