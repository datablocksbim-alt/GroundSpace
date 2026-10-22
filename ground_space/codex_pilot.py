"""Owner-only Codex CLI read-only review pilot with project approval settings."""
from __future__ import annotations
import json
import os
import secrets
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

MODES = ("manual", "auto_read_only", "disabled")

def persist(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + "." + secrets.token_hex(4) + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def read(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError: return default
    except (OSError, ValueError) as error:
        raise ValueError("Codex state is invalid. Restore from backup; no data was overwritten.") from error

class CodexPilot:
    def __init__(self, private_dir: Path, workspaces: Any, *, run=subprocess.run, which=shutil.which):
        self.workspaces, self.run, self.which = workspaces, run, which
        self.policy_path = private_dir / "codex_approval.json"
        self.jobs_path = private_dir / "codex_jobs.json"
        self.agent_path = private_dir / "codex_agent.json"
        self.agent_settings = read(self.agent_path, {"registered":False})
        if not isinstance(self.agent_settings, dict) or not isinstance(self.agent_settings.get("registered"), bool):
            raise ValueError("Codex agent registry invalid")
        self.lock = threading.RLock()
        self.policy_data = read(self.policy_path, {"default":"manual", "projects":{}})
        self.jobs = read(self.jobs_path, [])
        if not isinstance(self.policy_data, dict) or self.policy_data.get("default") not in MODES or not isinstance(self.policy_data.get("projects"),dict) or not isinstance(self.jobs,list):
            raise ValueError("Codex settings are invalid")
        for item in self.jobs:
            if item.get("status") == "running":
                item.update(status="interrupted", error="Ground Space restarted while Codex was reviewing")
        if self.jobs: persist(self.jobs_path,self.jobs)

    def is_registered(self) -> bool:
        with self.lock:
            return self.agent_settings["registered"]

    def set_registered(self, enabled: bool) -> dict[str, Any]:
        with self.lock:
            if enabled and not self.which("codex"):
                raise ValueError("Codex CLI must be installed on the ASUS first")
            persist(self.agent_path, {"registered": enabled})
            self.agent_settings = {"registered": enabled}
        return self.snapshot()

    def available(self) -> bool:
        return bool(self.which("codex"))

    def writable_available(self) -> bool:
        # Explicit opt-in; requires separate confirmation on the actual owner ASUS.
        return os.environ.get("GROUND_SPACE_CODEX_WRITE_ENABLED") == "1"

    def mode(self, project_id: str | None) -> str:
        with self.lock:
            value = self.policy_data["projects"].get(project_id, self.policy_data["default"])
            return value if value in MODES else "manual"

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"scope":"single_owner_pilot", "per_user_accounts":False,
                "cli_installed":bool(self.which("codex")), "registered":self.agent_settings["registered"],
                "write_enabled":self.writable_available(), "max_permission":"workspace_write_if_owner_approved",
                "default_mode":self.policy_data["default"],
                "project_modes":dict(self.policy_data["projects"]),
                "jobs":[dict(x) for x in reversed(self.jobs[-50:])]}

    def set_policy(self, body: dict[str,Any]) -> dict[str,Any]:
        mode = body.get("mode")
        project_id = body.get("project_id")
        if mode not in MODES: raise ValueError("Invalid approval mode")
        if project_id is not None:
            if not isinstance(project_id,str) or not project_id: raise ValueError("Invalid project ID")
            self.workspaces.get_project(project_id)
        with self.lock:
            data = {"default":self.policy_data["default"],
                    "projects":dict(self.policy_data["projects"])}
            if project_id is None: data["default"] = mode
            else: data["projects"][project_id] = mode
            persist(self.policy_path, data)
            self.policy_data = data
        return self.snapshot()

    def _job(self, job_id: str) -> dict[str,Any]:
        for job in self.jobs:
            if job["id"] == job_id: return job
        raise ValueError("Unknown Codex job")

    def submit(self, body: dict[str,Any], *, group_auto_approval: bool = False) -> dict[str,Any]:
        project_id, prompt = body.get("project_id"), body.get("prompt")
        scope = body.get("scope", "read_only")
        if scope not in ("read_only", "workspace_write"):
            raise ValueError("Invalid Codex operation scope")
        if scope == "workspace_write" and not self.writable_available():
            raise ValueError("Writable Codex agent is off. Explicitly enable the workspace-write pilot on the ASUS.")
        if scope == "workspace_write" and not self.is_registered():
            raise ValueError("Add Codex in Agents before assigning writable work")
        if not isinstance(project_id,str) or not project_id:
            raise ValueError("Choose a registered project for Codex")
        project = self.workspaces.get_project(project_id)
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>4000:
            raise ValueError("Codex review instructions must contain 1–4000 characters")
        mode = self.mode(project_id)
        if mode=="disabled": raise ValueError("Codex is disabled for this project")
        if not self.which("codex"): raise ValueError("Codex CLI is not installed or available to Ground Space")
        with self.lock:
            if sum(job["status"]=="pending_approval" for job in self.jobs)>=10:
                raise ValueError("Codex review queue is full; approve or reject pending reviews first")
            record = {"id":"CODEX-"+secrets.token_hex(7),"project_id":project_id,
                      "project_name":project["name"],"prompt":prompt.strip(),
                      "mode_at_submission":mode,"status":"pending_approval",
                      "scope":scope,"answer":"","error":"",
                      "group_id":body.get("group_id"), "conversation_id":body.get("conversation_id")}
            self.jobs = (self.jobs+[record])[-50:]
            persist(self.jobs_path,self.jobs)
        if mode=="auto_read_only" and scope=="read_only": self.approve({"job_id":record["id"]})
        # Only the trusted group dispatcher may grant an auto-approval based
        # on the persisted per-bot policy. Never use a browser-submitted flag.
        if group_auto_approval:
            group_id=record.get("group_id")
            if not isinstance(group_id,str) or not group_id:
                raise ValueError("Automatic writable permission requires a group")
            group=self.workspaces.get_group(group_id)
            if "codex" not in group["models"] or group.get("approval_modes",{}).get("codex")!="approve_for_me":
                raise ValueError("Codex is not automatically approved in this group")
            self.approve({"job_id":record["id"]})
        return self.get(record["id"])

    def get(self, job_id: str) -> dict[str,Any]:
        with self.lock: return dict(self._job(job_id))

    def approve(self, body: dict[str,Any]) -> dict[str,Any]:
        job_id=body.get("job_id")
        if not isinstance(job_id,str): raise ValueError("Job ID required")
        with self.lock:
            job=self._job(job_id)
            if job["status"]!="pending_approval": raise ValueError("Codex job is not awaiting approval")
            if any(other["status"]=="running" for other in self.jobs):
                raise ValueError("Another Codex review is already running; wait for it to finish")
            if self.mode(job["project_id"])=="disabled": raise ValueError("Codex is disabled for this project")
            if job["scope"]=="workspace_write" and (not self.writable_available() or not self.is_registered()):
                raise ValueError("Writable Codex is not enabled and registered")
            self.workspaces.get_project(job["project_id"])
            if job.get("group_id"):
                group=self.workspaces.get_group(job["group_id"])
                if "codex" not in group["models"] or group.get("approval_modes",{}).get("codex","approve_for_me")=="disabled":
                    raise ValueError("Codex approval has been disabled in this group")
            if not self.which("codex"): raise ValueError("Codex CLI is unavailable")
            job["status"]="running"
            persist(self.jobs_path,self.jobs)
        threading.Thread(target=self._execute,args=(job_id,),daemon=True).start()
        return self.get(job_id)

    def reject(self, body: dict[str,Any]) -> dict[str,Any]:
        job_id=body.get("job_id")
        if not isinstance(job_id,str): raise ValueError("Job ID required")
        with self.lock:
            job=self._job(job_id)
            if job["status"]!="pending_approval": raise ValueError("Only pending reviews can be rejected")
            job["status"]="rejected"
            persist(self.jobs_path,self.jobs)
            return dict(job)

    def _execute(self, job_id: str) -> None:
        try:
            job=self.get(job_id)
            project=self.workspaces.get_project(job["project_id"])
            cwd=Path(project["path"]).resolve(strict=True)
            if job.get("scope") == "workspace_write" and (not cwd.is_dir() or not any(
                    cwd != allowed and cwd.is_relative_to(allowed)
                    for allowed in getattr(self.workspaces, "allowed_roots", []))):
                raise RuntimeError("Selected project no longer lies within allowed roots")
            executable=self.which("codex")
            if not executable: raise RuntimeError("Codex CLI unavailable")
            writable = job.get("scope")=="workspace_write"
            if writable and (not self.writable_available() or not self.is_registered()):
                raise RuntimeError("Writable Codex permission was revoked")
            # This is a sandboxed workspace run, not OS-level user isolation.
            # Only the configured Codex sandbox decides actual filesystem reach;
            # do not claim all operating-system files are inaccessible.
            prompt = (
                ("WORKSPACE CODING TASK. You may create, edit, run tests and delete "
                 "files inside the selected project as needed. Do not touch parent folders, "
                 "unrelated projects, .git, credentials, secrets, or system configuration. "
                 "Report exactly what you changed and tests run.\\n\\n")
                if writable else
                ("READ-ONLY REVIEW: Inspect and explain code. Suggest changes in text. "
                 "Do not edit files, install packages, execute untrusted code or request "
                 "elevated permissions.\\n\\n")
            ) + job["prompt"]
            args=[executable,"--ask-for-approval","never","exec","--sandbox",
                  "workspace-write" if writable else "read-only","--skip-git-repo-check","-"]
            completed=self.run(args,input=prompt,text=True,cwd=str(cwd),
                               capture_output=True,timeout=180,shell=False,check=False)
            if completed.returncode:
                raise RuntimeError("Codex exited unsuccessfully. Check local CLI login and logs.")
            answer=completed.stdout.strip()
            if not answer: raise RuntimeError("Codex returned no review")
            with self.lock:
                self._job(job_id).update(status="completed",answer=answer[-20000:])
                persist(self.jobs_path,self.jobs)
        except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
            error="Codex timed out" if isinstance(exc,subprocess.TimeoutExpired) else str(exc)
            with self.lock:
                self._job(job_id).update(status="failed",error=error[:250])
                persist(self.jobs_path,self.jobs)
