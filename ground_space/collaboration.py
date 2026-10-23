"""GS-023 owner-controlled workflow: Qwen proposes -> Codex implements -> Granite reviews.

Handoffs use real existing adapters; this ledger creates NO new tool permissions.
Review is of the Codex textual report, not an independent filesystem audit.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

STATES = frozenset(("proposal_pending","codex_pending","review_pending","completed","failed"))
MAX_RUNS = 40


class CollaborationLedger:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        try:
            self.runs = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.runs = []
        except (OSError, ValueError) as error:
            raise ValueError("Collaboration records are unreadable; refusing to overwrite") from error
        if not isinstance(self.runs,list) or any(
            not isinstance(item,dict) or item.get("state") not in STATES for item in self.runs
        ):
            raise ValueError("Collaboration state is invalid")

    def snapshot(self) -> list[dict[str,Any]]:
        with self.lock:
            return [dict(r) for r in reversed(self.runs[-MAX_RUNS:])]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_name("." + self.path.name + "." + secrets.token_hex(5) + ".tmp")
        try:
            tmp.write_text(json.dumps(self.runs,indent=2),encoding="utf-8")
            os.replace(tmp,self.path)
        finally:
            tmp.unlink(missing_ok=True)

    def create(self, *, group_id: str, project_id: str, goal: str, qwen_task_id: str,
               qwen_model: str, granite_model: str) -> dict[str,Any]:
        if not all(isinstance(x,str) and x for x in (group_id,project_id,goal,qwen_task_id,qwen_model,granite_model)):
            raise ValueError("Missing collaboration identifiers")
        with self.lock:
            active=[r for r in self.runs if r["group_id"]==group_id and r["state"] not in ("completed","failed")]
            if active:
                raise ValueError("This group already has an active collaboration")
            record={"id":"FLOW-"+secrets.token_hex(8),"group_id":group_id,"project_id":project_id,
                    "goal":goal,"qwen_model":qwen_model,"granite_model":granite_model,
                    "proposal_task_id":qwen_task_id,"codex_job_id":None,"review_task_id":None,
                    "state":"proposal_pending","events":[{"stage":"proposal","task_id":qwen_task_id}]}
            self.runs=(self.runs+[record])[-MAX_RUNS:]
            self._save()
            return dict(record)

    def read(self, flow_id: str) -> dict[str,Any]:
        with self.lock:
            for flow in self.runs:
                if flow["id"]==flow_id:return dict(flow)
            raise ValueError("Unknown collaboration")

    def attach(self, flow_id: str, *, expected_state: str, state: str,
               link_name: str, link_id: str) -> dict[str,Any]:
        if state not in STATES or link_name not in ("codex_job_id","review_task_id"):
            raise ValueError("Invalid workflow transition")
        with self.lock:
            item=next((r for r in self.runs if r["id"]==flow_id),None)
            if item is None:raise ValueError("Unknown collaboration")
            if item["state"]!=expected_state or item[link_name] is not None:
                raise ValueError("Collaboration step was already dispatched")
            item[link_name]=link_id
            item["state"]=state
            item["events"].append({"stage":state,"task_id":link_id})
            self._save()
            return dict(item)

    def fail(self, flow_id: str, reason: str) -> dict[str,Any]:
        with self.lock:
            item=next((r for r in self.runs if r["id"]==flow_id),None)
            if item is None:raise ValueError("Unknown collaboration")
            if item["state"] in ("completed","failed"):return dict(item)
            item["state"]="failed"
            item["error"]=str(reason)[:200]
            item["events"].append({"stage":"failed","reason":item["error"]})
            self._save()
            return dict(item)

    def finish(self, flow_id: str) -> dict[str,Any]:
        with self.lock:
            item=next((r for r in self.runs if r["id"]==flow_id),None)
            if item is None or item["state"]!="review_pending":
                raise ValueError("Review must complete first")
            item["state"]="completed"
            item["events"].append({"stage":"completed"})
            self._save()
            return dict(item)
