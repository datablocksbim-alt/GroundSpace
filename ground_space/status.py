"""Generate the local-agent availability report without making model requests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .workers import ollama_descriptors, probe_ollama


def build_report(endpoint: str) -> dict:
    probe = probe_ollama(endpoint)
    agents = []
    for descriptor in ollama_descriptors(endpoint, probe):
        agents.append({
            "agent_id": descriptor.agent_id,
            "role": descriptor.role,
            "provider": descriptor.provider,
            "model": descriptor.model,
            "active": descriptor.active,
            "qualified": descriptor.qualified,
            "permissions": sorted(descriptor.permissions),
            "metadata": descriptor.metadata,
        })
    return {"ollama": probe, "agents": agents, "paid_api_usage": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.endpoint)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
