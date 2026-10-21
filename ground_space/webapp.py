"""Local-only GS-003 HTTP application using the existing Ground Space bridge."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .bridge import AdministratorAdapter, OrchestratorAdapter
from .coordinator import ProposalStore, coordinator_prompt, select_participants
from .messages import utc_timestamp
from .workspaces import WorkspaceRegistry, allowed_project_roots
from .workers import (AdministratorConsoleWorker, OllamaProposalWorker, PERFORMANCE_PRESETS,
                      ollama_descriptors, probe_ollama, valid_model_name)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "web" / "public"
ADMIN_ROOT = Path(os.environ.get("DATABLOCKS_ADMIN_ROOT", r"D:\000_AI Project\AI Agents Datablocks"))
MAX_HISTORY_MESSAGES = 24
MAX_PLANNING_NOTES = 100
MAX_MESSAGE_LENGTH = 12_000
SLASH_NOTE_TYPES = frozenset({"goal", "milestone"})


def parse_slash_note(prompt: str) -> tuple[str, str] | None:
    """Parse an owner-authored conversation annotation, never an agent command."""
    if not prompt.startswith("/"):
        return None
    parts = prompt.split(maxsplit=1)
    kind = parts[0][1:].casefold()
    if kind not in SLASH_NOTE_TYPES:
        raise ValueError("Unknown slash command. Available: /goal and /milestone")
    details = parts[1].strip() if len(parts) == 2 else ""
    if not details:
        raise ValueError(f"Add a description after /{kind}")
    return kind, details


def planning_followup_prompt(kind: str, description: str) -> str:
    """Ask for a plan, without treating a planning note as execution approval."""
    label = "GOAL" if kind == "goal" else "MILESTONE"
    guidance = (
        "Summarize the goal and suggest up to three practical milestones or next steps."
        if kind == "goal" else
        "Explain how this milestone contributes to the plan, suggest its acceptance criteria and immediate next step."
    )
    return (
        f"The user added a persistent {label} planning note. "
        "Recognize it as a project objective, not a normal chat question. "
        f"{guidance} Keep the answer concise and useful. "
        "Do not claim to have completed work, assigned agents, inspected files, "
        "or run any commands. This is planning only.\n\n"
        f"{label} description:\n{description}"
    )


def default_state_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return base / "DataBlocks" / "GroundSpace"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


class GroundSpaceApp:
    def __init__(self, state_dir: Path, *, ollama_endpoint: str = "http://127.0.0.1:11434"):
        self.state_dir = state_dir.resolve()
        self.ollama_endpoint = ollama_endpoint
        self.history_path = self.state_dir / "private" / "conversations.json"
        self.queue_dir = self.state_dir / "private" / "queue"
        self.models_path = self.state_dir / "private" / "chat_models.json"
        self.workspaces = WorkspaceRegistry(self.state_dir / "private", allowed_project_roots(ADMIN_ROOT))
        self.proposals = ProposalStore(self.state_dir / "private" / "coordinator_proposals.json")
        self.group_dispatch_lock = threading.Lock()
        self.lock = threading.RLock()
        self.administrator = AdministratorAdapter(
            ADMIN_ROOT, self.queue_dir, self.state_dir / "private" / "audit" / "messages.jsonl",
            retry_delay_seconds=0,
        )
        self.orchestrator = OrchestratorAdapter(self.administrator)
        self.orchestrator.register(AdministratorConsoleWorker(str(self.queue_dir)))
        self.registered_models = self._load_registered_models()
        availability = probe_ollama(ollama_endpoint)
        for model in self.registered_models:
            self._register_worker(model, availability)
        self.conversations = self._load_history()


    @staticmethod
    def worker_id(model: str) -> str:
        if model == "qwen2.5-coder:3b":
            return "qwen-proposal"
        return "ollama-chat-" + hashlib.sha256(model.encode("utf-8")).hexdigest()[:16]

    def _load_registered_models(self) -> list[str]:
        try:
            records = json.loads(self.models_path.read_text(encoding="utf-8"))
            models = records["models"]
            if not isinstance(models, list):
                raise ValueError("Invalid registered models")
            return list(dict.fromkeys(
                name for name in models[:24] if isinstance(name, str) and valid_model_name(name)
            ))[:12]
        except FileNotFoundError:
            return ["qwen2.5-coder:3b"]
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("Private model registry is damaged; fix chat_models.json before starting")

    def _register_worker(self, model: str, availability: dict[str, Any]) -> None:
        self.orchestrator.register(OllamaProposalWorker(
            endpoint=self.ollama_endpoint, model=model,
            agent_id=self.worker_id(model),
            active=bool(availability.get("available") and model in availability.get("models", [])),
            qualified=model == "qwen2.5-coder:3b",
        ))

    def catalog(self) -> dict[str, Any]:
        availability = probe_ollama(self.ollama_endpoint)
        installed = sorted(model for model in availability["models"] if valid_model_name(model))
        with self.lock:
            registered = list(self.registered_models)
        return {
            "registered": [
                {"provider": "ollama", "model": model, "worker_id": self.worker_id(model),
                 "available": model in installed, "label": model,
                 "role": "proposal-only" if model == "qwen2.5-coder:3b" else "experimental proposal-only"}
                for model in registered
            ],
            "discovered": [model for model in installed if model not in registered],
            "presets": [{"id": key, "label": value["label"],
                         "max_output_tokens": value["num_predict"]}
                        for key, value in PERFORMANCE_PRESETS.items()],
            "future_providers": [
                {"id": "openai", "label": "ChatGPT / OpenAI", "status": "not_connected"},
                {"id": "anthropic", "label": "Claude", "status": "not_connected"},
            ],
        }

    def add_model(self, name: str) -> dict[str, Any]:
        if not valid_model_name(name):
            raise ValueError("Invalid local model name")
        availability = probe_ollama(self.ollama_endpoint)
        if name not in availability.get("models", []):
            raise ValueError("Model must already be installed in local Ollama")
        with self.lock:
            if name in self.registered_models:
                raise ValueError("Model is already registered")
            if len(self.registered_models) >= 12:
                raise ValueError("Ground Space supports up to 12 model registrations")
            updated = self.registered_models + [name]
            atomic_json(self.models_path, {"schema_version": 1, "models": updated})
            self.registered_models = updated
            self._register_worker(name, availability)
        return self.catalog()

    def remove_model(self, name: str) -> dict[str, Any]:
        with self.lock:
            if name not in self.registered_models:
                raise ValueError("Model is not registered")
            updated = [model for model in self.registered_models if model != name]
            atomic_json(self.models_path, {"schema_version": 1, "models": updated})
            self.registered_models = updated
            self.orchestrator.workers.pop(self.worker_id(name), None)
        return self.catalog()


    def add_project(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.workspaces.add_project(
            str(body.get("path", "")), str(body.get("name", ""))
        )

    def create_group(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return self.workspaces.create_group(
                body.get("name"), body.get("models"), body.get("project_id"),
                list(self.registered_models),
            )

    def update_group(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return self.workspaces.update_group(
                str(body.get("group_id", "")), body.get("models"),
                body.get("project_id"), list(self.registered_models),
            )

    def submit_group(self, body: dict[str, Any], *, annotation_entry: dict[str, Any] | None = None) -> dict[str, Any]:
        group = self.workspaces.get_group(str(body.get("group_id", "")))
        prompt = str(body.get("prompt", "")).strip()
        if not prompt or len(prompt) > MAX_MESSAGE_LENGTH:
            raise ValueError("Message is empty or too long")
        if parse_slash_note(prompt):
            raise ValueError("Use the chat endpoint for /goal or /milestone notes")
        request_type = str(body.get("request_type", "explanation"))
        if request_type not in {"explanation", "assessment", "code_proposal"}:
            raise ValueError("Invalid group request capability")
        performance = str(body.get("performance", "balanced"))
        if performance not in PERFORMANCE_PRESETS:
            raise ValueError("Unknown performance preset")
        with self.lock:
            models = list(group["models"])
            if not set(models).issubset(set(self.registered_models)):
                raise ValueError("A group AI model is no longer registered; edit its members")
            # An unaddressed message is for Coordinator. Explicit @model mentions
            # select only those room members; no unconnected cloud provider fallback.
            targets = ([(models[0], "Coordinator")] if annotation_entry is not None
                       else select_participants(prompt, models))
            availability = probe_ollama(self.ollama_endpoint)
            for model, _speaker in targets:
                self._register_worker(model, availability)
            conversation_id = group["conversation_id"]
            context = self.conversation_context(conversation_id)
            new_cards = (self.proposals.create_goal(annotation_entry["content"], group)
                         if annotation_entry is not None and annotation_entry.get("kind") == "goal"
                         else [])
            group_turn_id = "TURN-" + secrets.token_hex(8)
            task_ids: list[str] = []
            timeout = PERFORMANCE_PRESETS[performance]["timeout_seconds"] + 5
            for model, speaker in targets:
                current_request = (coordinator_prompt(prompt, new_cards)
                                   if speaker == "Coordinator" else prompt)
                # Never feed another model's current-turn output into this request.
                full_prompt = (f"Bounded conversation context:\n{context}\n\nCurrent user request:\n{current_request}"
                               if context else current_request)
                payload = {"request_type": request_type, "prompt": full_prompt,
                           "conversation_id": conversation_id, "model": model, "speaker": speaker,
                           "performance": performance, "group_id": group["id"],
                           "group_turn_id": group_turn_id, "project_id": group["project_id"]}
                task = self.administrator.submit(
                    payload, worker_id=self.worker_id(model),
                    required_permissions=["read", "propose"],
                    execution_timeout_seconds=timeout, approved=True,
                    approval_source="ground-space-group-chat",
                )
                task_ids.append(task["task_id"])
            if annotation_entry is None:
                self.add_history(
                    conversation_id, "user", prompt, agent="group",
                    group_id=group["id"], group_turn_id=group_turn_id,
                    task_ids=task_ids, project_id=group["project_id"],
                )
            else:
                annotation_entry.update(task_ids=task_ids, group_turn_id=group_turn_id,
                                        proposal_ids=[card["task_id"] for card in new_cards])
                atomic_json(self.history_path, self.conversations)
        threading.Thread(
            target=self._process_group, args=(task_ids,), daemon=True,
        ).start()
        response = {"group": group, "task_ids": task_ids, "conversation_id": conversation_id,
                    "proposal_ids": [card["task_id"] for card in new_cards]}
        if annotation_entry is not None:
            response["entry"] = annotation_entry
        return response

    def approve_proposal(self, body: dict[str, Any]) -> dict[str, Any]:
        """Explicit owner action, limited to tool-free read/propose worker calls."""
        if body.get("confirm") is not True:
            raise ValueError("Explicit task approval confirmation is required")
        task_id = str(body.get("task_id", ""))
        group_id = str(body.get("group_id", ""))
        with self.lock:
            proposal = self.proposals.get(task_id)
            group = self.workspaces.get_group(group_id)
            if proposal["group_id"] != group["id"] or proposal["project_id"] != group["project_id"]:
                raise ValueError("Proposal does not belong to this group and project")
            if proposal["status"] != "proposed":
                raise ValueError("Proposal already dispatched")
            if proposal["assignee"] not in group["models"] or proposal["assignee"] not in self.registered_models:
                raise ValueError("Proposed worker is no longer a registered group member")
            for dependency in proposal["depends_on"]:
                previous = self.proposals.get(dependency)
                if previous["goal_id"] != proposal["goal_id"] or previous["project_id"] != proposal["project_id"]:
                    raise ValueError("Invalid proposal dependency")
                try:
                    predecessor = self.administrator.status(dependency)
                except (OSError, ValueError) as error:
                    raise ValueError("Complete prerequisite tasks before approving this proposal") from error
                if predecessor.get("status") != "completed":
                    raise ValueError("Complete prerequisite tasks before approving this proposal")
            availability = probe_ollama(self.ollama_endpoint)
            model = proposal["assignee"]
            if model not in availability.get("models", []):
                raise ValueError("Assigned local Ollama model is currently unavailable")
            self._register_worker(model, availability)
            # File system paths and execution privileges are NEVER passed to the worker.
            payload = {
                "request_type": "code_proposal",
                "prompt": "Produce a written, non-executing proposal for this approved task. "
                          "Do not claim to inspect or edit files. No tools are available.\n"
                          f"Goal: {proposal['goal']}\nAssignment: {proposal['title']}\n"
                          f"Instructions: {proposal['instructions']}\n"
                          f"Acceptance: {', '.join(proposal['acceptance_criteria'])}",
                "model": model, "speaker": model, "group_id": group_id,
                "conversation_id": proposal["conversation_id"],
                "project_id": proposal["project_id"],
                "proposal_id": task_id, "performance": "balanced",
            }
            queued = self.administrator.submit(
                payload, task_id=task_id, worker_id=self.worker_id(model),
                required_permissions=["read", "propose"],
                execution_timeout_seconds=PERFORMANCE_PRESETS["balanced"]["timeout_seconds"] + 5,
                approved=True, approval_source="ground-space-owner-click",
            )
            self.proposals.mark_queued(task_id)
        threading.Thread(target=self._process_group, args=([task_id],), daemon=True).start()
        return {"task": queued, "proposal_id": task_id}

    def _process_group(self, task_ids: list[str]) -> None:
        # Single laptop GPU: avoid parallel simultaneous Ollama generations.
        with self.group_dispatch_lock:
            for task_id in task_ids:
                try:
                    self._process_and_record(task_id)
                except Exception as error:
                    self.administrator.audit.append({
                        "schema_version": 1, "event": "group_dispatch_error",
                        "task_id": task_id, "timestamp": utc_timestamp(),
                        "message": type(error).__name__,
                    })

    def _load_history(self) -> dict[str, list[dict[str, Any]]]:
        try:
            value = json.loads(self.history_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def add_history(self, conversation_id: str, role: str, content: str, **metadata: Any) -> dict[str, Any]:
        with self.lock:
            messages = self.conversations.setdefault(conversation_id, [])
            entry = {"role": role, "content": content, "timestamp": utc_timestamp(), **metadata}
            messages.append(entry)
            # Keep planning notes separately within the same bounded local history
            # so ordinary chat messages do not immediately evict goals/milestones.
            normal = [item for item in messages if item.get("role") != "note"]
            planning = [item for item in messages if item.get("role") == "note"]
            keep = {id(item) for item in normal[-MAX_HISTORY_MESSAGES:]}
            keep.update(id(item) for item in planning[-MAX_PLANNING_NOTES:])
            self.conversations[conversation_id] = [item for item in messages if id(item) in keep]
            atomic_json(self.history_path, self.conversations)
            return entry

    def conversation_context(self, conversation_id: str) -> str:
        """Keep recent planning objectives visible after normal chat turns roll off."""
        with self.lock:
            messages = list(self.conversations.get(conversation_id, []))
        notes = [item for item in messages if item.get("role") == "note"][-12:]
        recent = [item for item in messages if item.get("role") != "note"][-8:]
        lines = [
            f"planning_{item.get('kind', 'note')}: {item.get('content', '')}"
            for item in notes
        ] + [
            f"{item.get('role')}: {item.get('content')}"
            for item in recent
        ]
        return "\n".join(lines)[-8000:]

    def submit_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        agent = str(body.get("agent", ""))
        prompt = str(body.get("prompt", "")).strip()
        conversation_id = str(body.get("conversation_id") or secrets.token_hex(12))
        if agent not in {"administrator", "qwen", "group"}:
            raise ValueError("Agent must be administrator, qwen, or group")
        group = (self.workspaces.get_group(str(body.get("group_id", "")))
                 if agent == "group" else None)
        project_id = (group["project_id"] if group else
                      self.workspaces.validate_project(body.get("project_id")))
        if group:
            conversation_id = group["conversation_id"]
        if not prompt or len(prompt) > MAX_MESSAGE_LENGTH:
            raise ValueError("Message is empty or too long")
        note = parse_slash_note(prompt)
        if note and agent == "qwen":
            # Reject an unavailable selection before persisting a note as review-requested.
            if str(body.get("performance", "balanced")) not in PERFORMANCE_PRESETS:
                raise ValueError("Invalid response performance preset")
            with self.lock:
                if str(body.get("model", "qwen2.5-coder:3b")) not in self.registered_models:
                    raise ValueError("Select a registered local model in the model manager")
        if note and group:
            if str(body.get("performance", "balanced")) not in PERFORMANCE_PRESETS:
                raise ValueError("Unknown performance preset")
            with self.lock:
                if not set(group["models"]).issubset(set(self.registered_models)):
                    raise ValueError("A group AI model is no longer registered; edit its members")
        if note:
            kind, description = note
            entry = self.add_history(
                conversation_id, "note", description, agent=agent,
                kind=kind, note_id=f"NOTE-{secrets.token_hex(8)}",
                source="slash_command", group_id=group["id"] if group else None,
                project_id=project_id, planning_status="ai_review_requested" if agent != "administrator" else "recorded",
            )
            if agent == "administrator":
                # The read-only console cannot perform model planning or execute goals.
                return {"entry": entry, "conversation_id": conversation_id}
            prompt = planning_followup_prompt(kind, description)
            if group:
                # The same note is the source of the group turn; do not add a duplicate user bubble.
                return self.submit_group(
                    {**body, "group_id": group["id"], "prompt": prompt,
                     "request_type": "explanation"},
                    annotation_entry=entry,
                )
        if group:
            # Non-note group turns must go through /api/groups/send.
            raise ValueError("Group conversations use group send")
        if agent == "qwen":
            request_type = str(body.get("request_type", "explanation"))
            model = str(body.get("model", "qwen2.5-coder:3b"))
            performance = str(body.get("performance", "balanced"))
            if performance not in PERFORMANCE_PRESETS:
                raise ValueError("Invalid response performance preset")
            with self.lock:
                if model not in self.registered_models:
                    raise ValueError("Select a registered local model in the model manager")
                self._register_worker(model, probe_ollama(self.ollama_endpoint))
            context = self.conversation_context(conversation_id)
            full_prompt = f"Bounded conversation context:\n{context}\n\nCurrent user request:\n{prompt}" if context else prompt
            payload = {"request_type": request_type, "prompt": full_prompt,
                       "conversation_id": conversation_id, "model": model,
                       "performance": performance, "project_id": project_id}
            worker_id, permissions, timeout = self.worker_id(model), ["read", "propose"], (
                PERFORMANCE_PRESETS[performance]["timeout_seconds"] + 5
            )
        else:
            lowered = prompt.casefold().strip()
            if lowered in {"help", "commands"}:
                payload = {"operation": "help", "conversation_id": conversation_id, "project_id": project_id}
            elif lowered in {"list", "list tasks", "tasks"}:
                payload = {"operation": "list", "conversation_id": conversation_id, "project_id": project_id}
            elif lowered.startswith("status "):
                payload = {"operation": "status", "target_task_id": prompt.split(maxsplit=1)[1].strip(),
                           "conversation_id": conversation_id, "project_id": project_id}
            else:
                raise ValueError("Administrator supports: help, list tasks, status <task-id>")
            worker_id, permissions, timeout = "administrator-console", ["read"], 10
        task = self.administrator.submit(
            payload, worker_id=worker_id, required_permissions=permissions,
            execution_timeout_seconds=timeout, approved=True,
            approval_source="ground-space-local-chat",
        )
        if note:
            # Connect the proposal task to its original planning card for status and recovery.
            with self.lock:
                entry.update(task_id=task["task_id"], model=payload.get("model"))
                atomic_json(self.history_path, self.conversations)
        else:
            self.add_history(conversation_id, "user", prompt, task_id=task["task_id"], agent=agent,
                             model=payload.get("model"), performance=payload.get("performance"),
                             project_id=project_id)
        threading.Thread(target=self._process_and_record, args=(task["task_id"],), daemon=True).start()
        response = {"task": task, "conversation_id": conversation_id}
        if note:
            response["entry"] = entry
        return response

    def _process_and_record(self, task_id: str) -> None:
        result = self.orchestrator.process(task_id)
        payload = result.get("payload", {})
        conversation_id = str(payload.get("conversation_id", ""))
        if not conversation_id:
            return
        worker_result = result.get("result") or {}
        answer = worker_result.get("answer")
        if answer:
            self.add_history(conversation_id, "assistant", str(answer), task_id=task_id,
                             agent=("administrator" if result.get("requested_worker") == "administrator-console"
                                     else "coordinator" if payload.get("speaker") == "Coordinator" else "qwen"),
                              speaker=payload.get("speaker"),
                             model=worker_result.get("model"), performance=worker_result.get("performance"),
                             tokens_per_second=worker_result.get("tokens_per_second"),
                             generation_seconds=worker_result.get("generation_seconds"),
                             group_id=payload.get("group_id"),
                             group_turn_id=payload.get("group_turn_id"),
                             project_id=payload.get("project_id"))
        elif result.get("status") in {"failed", "blocked", "retry_pending"}:
            self.add_history(conversation_id, "system",
                             str(result.get("failure") or result.get("failed_stage") or "Task did not complete"),
                             task_id=task_id,
                             agent=("administrator" if result.get("requested_worker") == "administrator-console"
                                     else "coordinator" if payload.get("speaker") == "Coordinator" else "qwen"),
                              speaker=payload.get("speaker"),
                             model=payload.get("model"), group_id=payload.get("group_id"),
                             group_turn_id=payload.get("group_turn_id"),
                             project_id=payload.get("project_id"))

    def task(self, task_id: str) -> dict[str, Any]:
        return self.administrator.status(task_id)

    def tasks(self) -> list[dict[str, Any]]:
        records = []
        for path in sorted(self.queue_dir.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)[:100]:
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return records

    def agents(self) -> list[dict[str, Any]]:
        availability = probe_ollama(self.ollama_endpoint)
        model_agents = {item.agent_id: item for item in ollama_descriptors(self.ollama_endpoint, availability)}
        installed = set(availability.get("models", []))
        with self.lock:
            registered = list(self.registered_models)
        return [
            {"agent_id": "administrator", "role": "queue, automatic dispatch, audit", "active": True,
             "permissions": ["submit", "status"]},
            {"agent_id": "coordinator", "role": "group conversation and proposed task planning", "active": True,
              "permissions": ["read", "propose"]},
            {"agent_id": "orchestrator", "role": "authorized routing", "active": True,
             "permissions": ["claim", "dispatch", "retry"]},
            *[{"agent_id": item.agent_id, "role": item.role, "active": item.active,
               "permissions": sorted(item.permissions), "model": item.model}
              for item in model_agents.values() if item.agent_id != "qwen-proposal"],
            *[{"agent_id": self.worker_id(model), "role": "proposal_only_chat",
               "active": bool(availability.get("available") and model in installed),
               "permissions": ["read", "propose"], "model": model}
              for model in registered],
        ]

    def bootstrap(self) -> dict[str, Any]:
        # Snapshot chat history under lock while multiple model replies are arriving.
        with self.lock:
            history = {key: [dict(item) for item in records]
                       for key, records in self.conversations.items()}
        return {"agents": self.agents(), "tasks": self.tasks(), "conversations": history,
                "models": self.catalog(), "workspaces": self.workspaces.snapshot(),
                 "proposals": self.proposals.snapshot(),
                "paid_api_usage_aud": 0}


class GroundSpaceHandler(BaseHTTPRequestHandler):
    server_version = "GroundSpace/0.3"

    @property
    def app(self) -> GroundSpaceApp:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[GroundSpace] {self.address_string()} {format % args}")

    def _json(self, status: int, value: Any, *, cookie: str | None = None) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _csrf_valid(self) -> bool:
        origin = self.headers.get("Origin", "")
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"  # type: ignore[attr-defined]
        if origin != expected_origin or self.headers.get_content_type() != "application/json":
            return False
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        cookie_token = cookie.get("gs_csrf")
        header_token = self.headers.get("X-Ground-Space-CSRF", "")
        return bool(cookie_token and header_token and hmac.compare_digest(cookie_token.value, header_token))

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 128_000:
            raise ValueError("Invalid request body size")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/projects/browse":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            chosen = query.get("path", [None])[0]
            try:
                self._json(HTTPStatus.OK, self.app.workspaces.browse_folders(chosen))
            except (ValueError, OSError) as error:
                self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        if path == "/api/bootstrap":
            token = secrets.token_urlsafe(24)
            self._json(200, {**self.app.bootstrap(), "csrf_token": token},
                       cookie=f"gs_csrf={token}; Path=/; SameSite=Strict")
            return
        if path.startswith("/api/tasks/"):
            try:
                self._json(200, self.app.task(path.rsplit("/", 1)[1]))
            except (OSError, ValueError) as error:
                self._error(404, str(error))
            return
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/app.css": ("app.css", "text/css; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8")}
        if path not in files:
            self.send_error(404)
            return
        filename, content_type = files[path]
        body = (PUBLIC / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self._csrf_valid():
            self._error(HTTPStatus.FORBIDDEN, "Cross-site request protection failed")
            return
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/chat":
                self._json(HTTPStatus.CREATED, self.app.submit_chat(body))
                return
            if path == "/api/projects/add":
                self._json(HTTPStatus.CREATED, self.app.add_project(body))
                return
            if path == "/api/groups/create":
                self._json(HTTPStatus.CREATED, self.app.create_group(body))
                return
            if path == "/api/groups/update":
                self._json(HTTPStatus.OK, self.app.update_group(body))
                return
            if path == "/api/groups/send":
                self._json(HTTPStatus.CREATED, self.app.submit_group(body))
                return
            if path == "/api/coordinator/approve":
                self._json(HTTPStatus.CREATED, self.app.approve_proposal(body))
                return
            if path == "/api/models/add":
                self._json(HTTPStatus.CREATED, self.app.add_model(str(body.get("model", ""))))
                return
            if path == "/api/models/remove":
                self._json(HTTPStatus.OK, self.app.remove_model(str(body.get("model", ""))))
                return
            self._error(HTTPStatus.NOT_FOUND, "Endpoint not found")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))


def create_server(app: GroundSpaceApp, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), GroundSpaceHandler)
    server.app = app  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Data Blocks Ground Space local chat")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    app = GroundSpaceApp(args.state_dir)
    server = create_server(app, args.port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Ground Space: {url}")
    print(f"Private state: {app.state_dir}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
