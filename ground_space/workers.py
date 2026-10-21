"""Permission-scoped local worker adapters and Ollama availability probing."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


# Model choices are server-owned; untrusted browser requests cannot supply a model name.
CHAT_MODELS = {
    "qwen25": {"model": "qwen2.5-coder:3b", "worker_id": "qwen-proposal",
               "label": "Qwen 2.5 Coder 3B", "qualified": True},
    "qwen35": {"model": "qwen3.5:4b", "worker_id": "qwen35-chat-proposal",
               "label": "Qwen 3.5 4B (experimental chat)", "qualified": False},
}

# Output caps affect response length/latency; they are not fixed tokens-per-second guarantees.
PERFORMANCE_PRESETS = {
    "fast": {"label": "Fast · concise", "num_predict": 256, "num_ctx": 4096,
             "timeout_seconds": 90, "temperature": 0.2},
    "balanced": {"label": "Balanced", "num_predict": 640, "num_ctx": 6144,
                 "timeout_seconds": 155, "temperature": 0.2},
    "detailed": {"label": "Detailed · slower", "num_predict": 1200, "num_ctx": 8192,
                 "timeout_seconds": 235, "temperature": 0.2},
}


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

    def execution_request(self) -> dict[str, Any]:
        return {"kind": "deterministic"}


class OllamaProposalWorker:
    """Configuration-only adapter for a tool-free local Ollama proposal worker."""

    def __init__(self, *, endpoint: str = "http://127.0.0.1:11434", model: str = "qwen2.5-coder:3b",
                 agent_id: str = "qwen-proposal", active: bool = True,
                 qualified: bool = True, request_timeout_seconds: float = 235.0):
        if model not in {item["model"] for item in CHAT_MODELS.values()}:
            raise ValueError("Ollama model is not in the approved chat registry")
        self.descriptor = WorkerDescriptor(
            agent_id=agent_id,
            role="proposal_only",
            permissions=frozenset({"read", "propose"}),
            active=active,
            provider="ollama",
            model=model,
            endpoint=endpoint,
            qualified=qualified,
            metadata={"production_write_authority": False, "tool_access": False},
        )
        self.request_timeout_seconds = request_timeout_seconds

    def execution_request(self) -> dict[str, Any]:
        return {
            "kind": "ollama_proposal",
            "endpoint": self.descriptor.endpoint,
            "model": self.descriptor.model,
            "request_timeout_seconds": self.request_timeout_seconds,
        }


class AdministratorConsoleWorker:
    """Read-only task-management view over the Administrator queue."""

    def __init__(self, queue_dir: str):
        self.queue_dir = queue_dir
        self.descriptor = WorkerDescriptor(
            agent_id="administrator-console",
            role="task_management",
            permissions=frozenset({"read"}),
            metadata={"write_authority": False},
        )

    def execution_request(self) -> dict[str, Any]:
        return {"kind": "administrator_console", "queue_dir": self.queue_dir}


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
                         active=online and has("qwen2.5-coder"), provider="ollama", model="qwen2.5-coder:3b", endpoint=endpoint,
                         qualified=True, metadata={"production_write_authority": False}),
        WorkerDescriptor("granite-review", "read_only_reviewer", frozenset({"read", "review"}),
                         active=online and has("granite4"), provider="ollama", model="granite4:3b", endpoint=endpoint,
                         qualified=True, metadata={"production_approval_authority": False}),
        WorkerDescriptor("ministral", "orchestrator_candidate", frozenset({"read"}), active=False,
                         provider="ollama", model="ministral-3:8b", endpoint=endpoint, qualified=False,
                         metadata={"reason": "setup_and_qualification_incomplete"}),
    ]
