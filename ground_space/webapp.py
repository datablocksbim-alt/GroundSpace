"""Local-only GS-003 HTTP application using the existing Ground Space bridge."""

from __future__ import annotations

import argparse
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
from .messages import utc_timestamp
from .workers import AdministratorConsoleWorker, OllamaProposalWorker, ollama_descriptors, probe_ollama


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "web" / "public"
ADMIN_ROOT = Path(os.environ.get("DATABLOCKS_ADMIN_ROOT", r"D:\000_AI Project\AI Agents Datablocks"))
MAX_HISTORY_MESSAGES = 24
MAX_MESSAGE_LENGTH = 12_000


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
        self.lock = threading.RLock()
        self.administrator = AdministratorAdapter(
            ADMIN_ROOT, self.queue_dir, self.state_dir / "private" / "audit" / "messages.jsonl",
            retry_delay_seconds=0,
        )
        self.orchestrator = OrchestratorAdapter(self.administrator)
        self.orchestrator.register(AdministratorConsoleWorker(str(self.queue_dir)))
        availability = probe_ollama(ollama_endpoint)
        qwen_active = availability["available"] and "qwen2.5-coder:3b" in availability["models"]
        self.orchestrator.register(OllamaProposalWorker(endpoint=ollama_endpoint, active=qwen_active))
        self.conversations = self._load_history()

    def _load_history(self) -> dict[str, list[dict[str, Any]]]:
        try:
            value = json.loads(self.history_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def add_history(self, conversation_id: str, role: str, content: str, **metadata: Any) -> None:
        with self.lock:
            messages = self.conversations.setdefault(conversation_id, [])
            messages.append({"role": role, "content": content, "timestamp": utc_timestamp(), **metadata})
            self.conversations[conversation_id] = messages[-MAX_HISTORY_MESSAGES:]
            atomic_json(self.history_path, self.conversations)

    def conversation_context(self, conversation_id: str) -> str:
        messages = self.conversations.get(conversation_id, [])[-8:]
        return "\n".join(f"{item.get('role')}: {item.get('content')}" for item in messages)[-8000:]

    def submit_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        agent = str(body.get("agent", ""))
        prompt = str(body.get("prompt", "")).strip()
        conversation_id = str(body.get("conversation_id") or secrets.token_hex(12))
        if agent not in {"administrator", "qwen"}:
            raise ValueError("Agent must be administrator or qwen")
        if not prompt or len(prompt) > MAX_MESSAGE_LENGTH:
            raise ValueError("Message is empty or too long")
        if agent == "qwen":
            request_type = str(body.get("request_type", "explanation"))
            context = self.conversation_context(conversation_id)
            full_prompt = f"Bounded conversation context:\n{context}\n\nCurrent user request:\n{prompt}" if context else prompt
            payload = {"request_type": request_type, "prompt": full_prompt, "conversation_id": conversation_id}
            worker_id, permissions, timeout = "qwen-proposal", ["read", "propose"], 150
        else:
            lowered = prompt.casefold().strip()
            if lowered in {"help", "commands"}:
                payload = {"operation": "help", "conversation_id": conversation_id}
            elif lowered in {"list", "list tasks", "tasks"}:
                payload = {"operation": "list", "conversation_id": conversation_id}
            elif lowered.startswith("status "):
                payload = {"operation": "status", "target_task_id": prompt.split(maxsplit=1)[1].strip(),
                           "conversation_id": conversation_id}
            else:
                raise ValueError("Administrator supports: help, list tasks, status <task-id>")
            worker_id, permissions, timeout = "administrator-console", ["read"], 10
        task = self.administrator.submit(
            payload, worker_id=worker_id, required_permissions=permissions,
            execution_timeout_seconds=timeout, approved=True,
            approval_source="ground-space-local-chat",
        )
        self.add_history(conversation_id, "user", prompt, task_id=task["task_id"], agent=agent)
        threading.Thread(target=self._process_and_record, args=(task["task_id"],), daemon=True).start()
        return {"task": task, "conversation_id": conversation_id}

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
                             agent="qwen" if result.get("requested_worker") == "qwen-proposal" else "administrator")
        elif result.get("status") in {"failed", "blocked", "retry_pending"}:
            self.add_history(conversation_id, "system",
                             str(result.get("failure") or result.get("failed_stage") or "Task did not complete"),
                             task_id=task_id,
                             agent="qwen" if result.get("requested_worker") == "qwen-proposal" else "administrator")

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
        return [
            {"agent_id": "administrator", "role": "queue, automatic dispatch, audit", "active": True,
             "permissions": ["submit", "status"]},
            {"agent_id": "orchestrator", "role": "authorized routing", "active": True,
             "permissions": ["claim", "dispatch", "retry"]},
            *[{"agent_id": item.agent_id, "role": item.role, "active": item.active,
               "permissions": sorted(item.permissions), "model": item.model}
              for item in model_agents.values()],
        ]

    def bootstrap(self) -> dict[str, Any]:
        return {"agents": self.agents(), "tasks": self.tasks(), "conversations": self.conversations,
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
