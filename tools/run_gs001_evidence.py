"""Produce durable GS-001 round-trip evidence using the existing Administrator queue."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ground_space.bridge import AdministratorAdapter, OrchestratorAdapter
from ground_space.workers import DeterministicReadOnlyWorker


ADMIN_ROOT = Path(r"D:\000_AI Project\AI Agents Datablocks")


def main() -> int:
    evidence = ROOT / "evidence"
    administrator = AdministratorAdapter(
        ADMIN_ROOT,
        evidence / "queue",
        evidence / "message_audit.jsonl",
        retry_delay_seconds=0,
    )
    orchestrator = OrchestratorAdapter(administrator)
    orchestrator.register(DeterministicReadOnlyWorker())
    results = []
    for sequence in range(1, 4):
        task_id = f"GS-001-EVIDENCE-{sequence}"
        path = evidence / "queue" / f"{task_id}.json"
        if path.exists():
            result = administrator.status(task_id)
        else:
            task = administrator.submit(
                {"sequence": sequence, "instruction": "deterministic read-only inspection"},
                task_id=task_id,
                correlation_id=f"gs001-round-trip-{sequence}",
            )
            result = orchestrator.process(task["task_id"])
        results.append({
            "task_id": task_id,
            "status": result["status"],
            "attempt_count": result["attempt_count"],
            "completed_by": result.get("completed_by"),
            "result": result.get("result"),
        })
    summary = {
        "schema_version": 1,
        "round_trips": results,
        "all_completed": all(item["status"] == "completed" for item in results),
        "cloud_services_used": False,
        "paid_api_usage_aud": 0,
    }
    (evidence / "round_trip_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
