"""Run three approved, live, proposal-only Qwen exchanges through Ground Space."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ground_space.bridge import AdministratorAdapter, OrchestratorAdapter
from ground_space.workers import OllamaProposalWorker, probe_ollama


ADMIN_ROOT = None
ENDPOINT = "http://127.0.0.1:11434"
MODEL = "qwen2.5-coder:3b"


REQUESTS = [
    ("explanation", "Explain in two sentences why correlation IDs are useful in asynchronous task systems."),
    ("assessment", "Assess whether a read-only proposal worker should receive filesystem write permission. Be concise."),
    ("code_proposal", "Propose a short Python function that validates a non-empty task ID. Return code only; do not execute it."),
]


def main() -> int:
    evidence = ROOT / "evidence" / "gs002"
    availability = probe_ollama(ENDPOINT)
    if not availability["available"] or MODEL not in availability["models"]:
        print(json.dumps({"completed": False, "reason": "required_local_model_unavailable", "ollama": availability}, indent=2))
        return 2
    administrator = AdministratorAdapter(
        ADMIN_ROOT, evidence / "queue", evidence / "message_audit.jsonl", retry_delay_seconds=0,
    )
    orchestrator = OrchestratorAdapter(administrator)
    orchestrator.register(OllamaProposalWorker(endpoint=ENDPOINT, model=MODEL, request_timeout_seconds=120))
    results = []
    for index, (request_type, prompt) in enumerate(REQUESTS, 1):
        task_id = f"GS-002-LIVE-{index}"
        task_path = evidence / "queue" / f"{task_id}.json"
        if task_path.exists():
            result = administrator.status(task_id)
        else:
            task = administrator.submit(
                {"request_type": request_type, "prompt": prompt},
                worker_id="qwen-proposal",
                required_permissions=["read", "propose"],
                task_id=task_id,
                correlation_id=f"gs002-live-{index}",
                execution_timeout_seconds=150,
            )
            administrator.approve(task["task_id"], owner="Karl")
            result = orchestrator.process(task["task_id"])
        worker_result = result.get("result", {})
        results.append({
            "task_id": result["task_id"],
            "correlation_id": result["correlation_id"],
            "status": result["status"],
            "model": worker_result.get("model"),
            "request_type": worker_result.get("request_type"),
            "answer": worker_result.get("answer"),
            "response_sha256": worker_result.get("response_sha256"),
            "proposal_only": worker_result.get("proposal_only"),
            "tools_executed": worker_result.get("tools_executed"),
        })
    summary = {
        "schema_version": 1,
        "completed": all(item["status"] == "completed" for item in results),
        "model": MODEL,
        "endpoint": ENDPOINT,
        "exchanges": results,
        "cloud_services_used": False,
        "paid_api_usage_aud": 0,
        "pyrene_modified": False,
    }
    (evidence / "live_exchange_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
