"""Permission-scoped local worker adapters and Ollama availability probing."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class WorkerDescriptor:
    agent_id: str
    role: str
    permissions: frozenset[str]
    active: bool = True
    provider: str = "python"
    model: str | None = None
    endpoint: str | None = None
    qualified: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class DeterministicReadOnlyWorker:
    descriptor = WorkerDescriptor(
        agent_id="python-readonly-1",
        role="deterministic_read_only",
        permissions=frozenset({"read"}),
    )

    def execute(self, task: dict[str, Any], progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        if set(task.get("required_permissions", [])) - self.descriptor.permissions:
            raise PermissionError("Task exceeds deterministic worker permissions")
        payload = task.get("payload", {})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        progress({"stage": "inspected", "percent": 50})
        result = {
            "operation": "deterministic_inspect",
            "input_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "keys": sorted(payload),
            "read_only": True,
        }
        progress({"stage": "finished", "percent": 100})
        return result


def probe_ollama(endpoint: str = "http://127.0.0.1:11434", timeout: float = 2.0) -> dict[str, Any]:
    url = endpoint.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = json.load(response)
        models = sorted(str(item.get("name", "")) for item in body.get("models", []) if item.get("name"))
        return {"available": True, "endpoint": endpoint, "models": models, "reason": None}
    except (OSError, ValueError, urllib.error.URLError) as error:
        return {"available": False, "endpoint": endpoint, "models": [], "reason": f"{type(error).__name__}: {error}"}


def ollama_descriptors(endpoint: str, availability: dict[str, Any]) -> list[WorkerDescriptor]:
    installed = set(availability.get("models", []))

    def has(prefix: str) -> bool:
        return any(name == prefix or name.startswith(prefix + ":") for name in installed)

    online = bool(availability.get("available"))
    return [
        WorkerDescriptor("qwen-proposal", "proposal_only", frozenset({"read", "propose"}),
                         active=online and has("qwen3.5"), provider="ollama", model="qwen3.5:4b", endpoint=endpoint,
                         qualified=True, metadata={"production_write_authority": False}),
        WorkerDescriptor("granite-review", "read_only_reviewer", frozenset({"read", "review"}),
                         active=online and has("granite4"), provider="ollama", model="granite4:3b", endpoint=endpoint,
                         qualified=True, metadata={"production_approval_authority": False}),
        WorkerDescriptor("ministral", "orchestrator_candidate", frozenset({"read"}), active=False,
                         provider="ollama", model="ministral-3:8b", endpoint=endpoint, qualified=False,
                         metadata={"reason": "setup_and_qualification_incomplete"}),
    ]
