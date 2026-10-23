"""Owner-authorized recovery for exactly two old direct, read-only Qwen greetings.

This intentionally does not bypass permissions, approve project writes, edit
conversations, modify Pyrene, change server settings, or start GS-029.
Use from the ASUS only. Without --execute, this is read-only inspection.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ground_space.bridge import AdministratorAdapter, OrchestratorAdapter
from ground_space.webapp import ADMIN_ROOT, default_state_dir
from ground_space.workers import OllamaProposalWorker, probe_ollama

MODEL = "qwen2.5-coder:3b"
WORKER = "qwen-proposal"
ALLOWED = frozenset({"read", "propose"})
EXPECTED_PROMPTS = {"hi qwen", "are you there"}
URL = "http://127.0.0.1:8765/api/bootstrap"


def greeting(task: dict[str, Any]) -> str | None:
    payload = task.get("payload")
    if not isinstance(payload, dict):
        return None
    text = payload.get("prompt")
    if not isinstance(text, str):
        return None
    cleaned = text.strip().casefold()
    if cleaned == "hi qwen":
        return "hi qwen"
    if re.search(r"(?:^|\n)current user request:\s*are you there\s*$", cleaned):
        return "are you there"
    return None


def validate_target(task: dict[str, Any]) -> str:
    task_id = task.get("task_id")
    if not isinstance(task_id, str) or not re.fullmatch(r"GS-[a-f0-9]{32}", task_id):
        raise ValueError("Unexpected task ID format; refusing approval.")
    if task.get("source") != "ground_space":
        raise ValueError(f"{task_id}: source is not Ground Space.")
    if task.get("requested_worker") != WORKER:
        raise ValueError(f"{task_id}: unexpected worker.")
    if task.get("status") != "queued" or (task.get("approval") or {}).get("status") != "pending":
        raise ValueError(f"{task_id}: not a queued/pending task.")
    payload = task.get("payload") or {}
    if payload.get("model") != MODEL or payload.get("group_id") or payload.get("project_id"):
        raise ValueError(f"{task_id}: not an unassigned direct Qwen 2.5 greeting.")
    if payload.get("request_type") not in ("explanation", None):
        raise ValueError(f"{task_id}: unexpected request type.")
    if set(task.get("required_permissions") or []) != ALLOWED:
        raise ValueError(f"{task_id}: permissions not exactly read/propose.")
    request = greeting(task)
    if request not in EXPECTED_PROMPTS:
        raise ValueError(f"{task_id}: prompt is not one of the two owner-approved greetings.")
    return request


def target_pair(tasks: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str]]:
    # Fail closed if there are any other pending queue tasks, even from other agents.
    pending = [x for x in tasks if x.get("status") == "queued" and
               (x.get("approval") or {}).get("status") == "pending"]
    if len(pending) != 2:
        raise ValueError(f"Expected exactly 2 queued/pending tasks, found {len(pending)}. No changes.")
    validated = [(task, validate_target(task)) for task in pending]
    if {name for _, name in validated} != EXPECTED_PROMPTS:
        raise ValueError("Pending tasks do not match the two greetings. No changes.")
    return validated


def live_tasks() -> list[dict[str, Any]]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL, timeout=12) as resp:
        data = json.load(resp)
    if str(data.get("backend_release")) not in {"GS-026", "GS-027", "GS-028"}:
        raise ValueError("Live version is not the supported pre-GS-029 server. No changes.")
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("Live task list missing.")
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Approve only the validated two greetings and process them serially.")
    args = parser.parse_args()
    selection = target_pair(live_tasks())
    for task, name in selection:
        print(f"VERIFIED {task['task_id']} — {name!r}, worker={WORKER}, permissions=read/propose")
    if not args.execute:
        print("PRECHECK PASS — read-only. Re-run with --execute for owner-approved processing.")
        return 0

    availability = probe_ollama(timeout=3)
    if MODEL not in availability.get("models", []):
        raise RuntimeError("Local Qwen 2.5 Coder 3B is unavailable. Nothing approved.")

    state = default_state_dir()
    admin = AdministratorAdapter(
        ADMIN_ROOT, state / "private" / "queue",
        state / "private" / "audit" / "messages.jsonl",
        retry_delay_seconds=0,
    )
    orchestrator = OrchestratorAdapter(admin)
    orchestrator.register(OllamaProposalWorker(model=MODEL, agent_id=WORKER, active=True))

    for task, request in selection:
        # Compare the live record with the persisted one immediately before each decision.
        current = admin.status(task["task_id"])
        validate_target(current)
        if current.get("payload") != task.get("payload"):
            raise RuntimeError(f"Task {task['task_id']} changed; stopping without further approval.")
        admin.approve(task["task_id"], owner="ground-space-owner-explicit-approval")
        print(f"APPROVED {task['task_id']} — {request!r}. Running read/propose worker...")
        outcome = orchestrator.process(task["task_id"])
        print(f"RESULT {task['task_id']}: {outcome.get('status')}")
        if outcome.get("status") != "completed":
            raise RuntimeError("Task did not complete; inspect Tasks before retrying. No other task will run.")
        answer = (outcome.get("result") or {}).get("answer")
        if isinstance(answer, str):
            print("QWEN ANSWER:", answer[:900].replace("\n", " "))
    print("APPROVAL + EXECUTION COMPLETE: both verified greetings processed.")
    print("Answers are in task records/PowerShell, not necessarily appended to the live chat.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"STOPPED: {error}", file=sys.stderr)
        raise SystemExit(1)
