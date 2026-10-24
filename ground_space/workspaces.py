"""Private, lightweight registries for local projects and AI group chats.

Folder selection is metadata only. No worker gains filesystem access by linking a
project. Ground Space may identify the selected folder in a local Ollama prompt,
but workers receive no filesystem tools or read/write authority.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from .messages import utc_timestamp

MAX_PROJECTS = 30
MAX_GROUPS = 30
MAX_GROUP_MODELS = 6
# These options approve only local read/propose chat, never filesystem or CLI writes.
GROUP_APPROVAL_MODES = frozenset({'manual', 'approve_for_me', 'disabled'})


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def allowed_project_roots(private_dir: Path | None = None) -> list[Path]:
    """Resolve portable roots plus parents of already registered projects."""
    candidates = [Path.home()]
    extra = os.environ.get("GROUND_SPACE_ALLOWED_PROJECT_ROOTS", "")
    candidates.extend(Path(item.strip()) for item in extra.split(os.pathsep) if item.strip())
    if private_dir is not None:
        try:
            saved = json.loads((private_dir / "projects.json").read_text(encoding="utf-8"))
            for project in saved.get("projects", []):
                if isinstance(project, dict) and isinstance(project.get("path"), str):
                    candidates.append(Path(project["path"]).expanduser().parent)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            # WorkspaceRegistry will report corrupt state without silently
            # overwriting it; root discovery must not broaden access on error.
            pass
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve(strict=True)
            if resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
        except (OSError, RuntimeError):
            continue
    return roots


class WorkspaceRegistry:
    def __init__(self, private_dir: Path, allowed_roots: list[Path]):
        self.private_dir = private_dir
        self.projects_file = private_dir / "projects.json"
        self.groups_file = private_dir / "groups.json"
        self.allowed_roots = [root.resolve() for root in allowed_roots]
        self.lock = threading.RLock()
        self.projects = self._load(self.projects_file, "projects")
        self.groups = self._load(self.groups_file, "groups")

    @staticmethod
    def _load(path: Path, key: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            raise ValueError(f"Invalid private {key} registry")
        return data[key]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"projects": [dict(p) for p in self.projects],
                    "groups": [{**g, "approval_modes": dict(g.get("approval_modes", {}))} for g in self.groups],
                    "allowed_project_roots": [str(root) for root in self.allowed_roots]}

    def browse_folders(self, path_text: str | None = None) -> dict[str, Any]:
        """Metadata-only folder picker; never follows a path outside allowed roots."""
        if not path_text:
            return {"current": None, "folders": [
                {"name": str(root), "path": str(root)} for root in self.allowed_roots
            ], "is_root_list": True}
        if len(path_text) > 1200:
            raise ValueError("Folder path too long")
        try:
            resolved = Path(path_text).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError("Folder not found") from error
        if not resolved.is_dir() or not any(
            resolved == root or resolved.is_relative_to(root) for root in self.allowed_roots
        ):
            raise ValueError("Folder browsing is restricted to allowed project roots")
        children = []
        try:
            for item in sorted(resolved.iterdir(), key=lambda p: p.name.casefold()):
                if item.name.startswith("."):
                    continue
                try:
                    target = item.resolve(strict=True)
                    if (target.is_dir() and any(
                        target == root or target.is_relative_to(root)
                        for root in self.allowed_roots
                    )):
                        children.append({"name": item.name, "path": str(target)})
                except (OSError, RuntimeError):
                    continue
                if len(children) >= 100:
                    break
        except OSError as error:
            raise ValueError("Cannot list this folder") from error
        parent = resolved.parent
        can_up = any(parent == root or parent.is_relative_to(root)
                     for root in self.allowed_roots)
        return {"current": str(resolved), "folders": children,
                "parent": str(parent) if can_up else None,
                "is_root_list": False}

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.lock:
            for project in self.projects:
                if project["id"] == project_id:
                    return dict(project)
        raise ValueError("Unknown project ID")

    def validate_project(self, project_id: str | None) -> str | None:
        if not project_id:
            return None
        return self.get_project(str(project_id))["id"]

    def add_project(self, path_text: str, name: str = "") -> dict[str, Any]:
        if not isinstance(path_text, str) or len(path_text) > 1200:
            raise ValueError("Invalid project directory")
        supplied = Path(path_text.strip()).expanduser()
        if not supplied.is_absolute():
            raise ValueError("Provide an absolute local project folder path")
        try:
            resolved = supplied.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError("Project folder does not exist on this computer") from error
        if not resolved.is_dir() or not any(
            resolved != root and resolved.is_relative_to(root) for root in self.allowed_roots
        ):
            raise ValueError("Project folder must be inside an allowed project root")
        label = name.strip() or resolved.name
        if len(label) > 80 or not label:
            raise ValueError("Project name must be 1–80 characters")
        with self.lock:
            if any(p["path"] == str(resolved) for p in self.projects):
                raise ValueError("This project folder is already registered")
            if len(self.projects) >= MAX_PROJECTS:
                raise ValueError("Project registry is full")
            project = {"id": "project-" + secrets.token_hex(8), "name": label,
                       "path": str(resolved), "created_at": utc_timestamp(),
                       "scope": "metadata_only"}
            updated = [*self.projects, project]
            _save(self.projects_file, {"schema_version": 1, "projects": updated})
            self.projects = updated
            return dict(project)

    def rename_project(self, project_id: str, name: str) -> dict[str, Any]:
        """Rename only the project label. The selected ASUS path never changes."""
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Project name must be 1–80 characters")
        with self.lock:
            original = self.get_project(project_id)
            replacement = {**original, "name": name.strip()}
            updated = [replacement if p["id"] == project_id else p for p in self.projects]
            _save(self.projects_file, {"schema_version": 1, "projects": updated})
            self.projects = updated
            return dict(replacement)

    def remove_project(self, project_id: str) -> dict[str, Any]:
        """Unregister metadata only; preserve chat groups and their conversation IDs.

        Nested groups become unassigned, retaining their members, messages and
        approval policies. This never touches the selected filesystem folder.
        """
        if not isinstance(project_id, str) or not project_id.startswith("project-"):
            raise ValueError("Valid project ID required")
        with self.lock:
            project = self.get_project(project_id)
            remaining = [p for p in self.projects if p["id"] != project_id]
            previous_groups = self.groups
            groups = [
                {**g, "project_id": None} if g.get("project_id") == project_id else g
                for g in previous_groups
            ]
            # Update both small registries before in-memory mutation. If
            # project persistence fails, restore the previous group registry.
            if groups != previous_groups:
                _save(self.groups_file, {"schema_version": 1, "groups": groups})
            try:
                _save(self.projects_file, {"schema_version": 1, "projects": remaining})
            except Exception:
                if groups != previous_groups:
                    _save(self.groups_file, {"schema_version": 1, "groups": previous_groups})
                raise
            self.projects = remaining
            self.groups = groups
            return {"removed": project["id"], "name": project["name"],
                    "unassigned_chats": sum(
                        g.get("project_id") == project_id for g in previous_groups
                    ), "folder_deleted": False}

    def get_group(self, group_id: str) -> dict[str, Any]:
        with self.lock:
            for group in self.groups:
                if group["id"] == group_id:
                    return dict(group)
        raise ValueError("Unknown group chat")

    def rename_group(self, group_id: str, name: str) -> dict[str, Any]:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 70:
            raise ValueError("Chat name must be 1–70 characters")
        with self.lock:
            original = self.get_group(group_id)
            replacement = {**original, "name": name.strip()}
            updated = [replacement if g["id"] == group_id else g for g in self.groups]
            _save(self.groups_file, {"schema_version": 1, "groups": updated})
            self.groups = updated
            return dict(replacement)

    def remove_group(self, group_id: str) -> dict[str, Any]:
        """Remove a chat from navigation. History and audit are retained for recovery."""
        with self.lock:
            group = self.get_group(group_id)
            updated = [g for g in self.groups if g["id"] != group_id]
            _save(self.groups_file, {"schema_version": 1, "groups": updated})
            self.groups = updated
            return {"removed": group["id"], "name": group["name"],
                    "conversation_id": group["conversation_id"],
                    "transcript_retained": True}

    @staticmethod
    def _validate_members(models: Any, registered: list[str]) -> list[str]:
        if not isinstance(models, list) or not 1 <= len(models) <= MAX_GROUP_MODELS:
            raise ValueError("Choose between 1 and 6 local AI models")
        if not all(isinstance(m, str) for m in models):
            raise ValueError("Group members must be model identifiers")
        if len(set(models)) != len(models):
            raise ValueError("Duplicate AI models are not permitted in a group")
        if not set(models).issubset(set(registered)):
            raise ValueError("Group models must be registered under Agents first")
        return list(models)

    @staticmethod
    def _validate_approvals(approvals: Any, members: list[str], existing: dict[str, str] | None = None) -> dict[str, str]:
        if approvals is None:
            # Existing groups used automatic read/propose chat. Preserve that behavior.
            return {model: (existing or {}).get(model, "manual" if model == "codex" else "approve_for_me") for model in members}
        if not isinstance(approvals, dict) or set(approvals) - set(members):
            raise ValueError("Approval settings must match selected group members")
        if any(not isinstance(mode, str) or mode not in GROUP_APPROVAL_MODES
               for mode in approvals.values()):
            raise ValueError("Invalid group bot approval mode")
        return {model: approvals.get(model, (existing or {}).get(model, "manual" if model == "codex" else "approve_for_me")) for model in members}

    def create_group(self, name: str, models: Any, project_id: str | None,
                     registered: list[str], approval_modes: Any = None) -> dict[str, Any]:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 70:
            raise ValueError("Group name must be 1–70 characters")
        members = self._validate_members(models, registered)
        approvals = self._validate_approvals(approval_modes, members)
        project = self.validate_project(project_id)
        with self.lock:
            if len(self.groups) >= MAX_GROUPS:
                raise ValueError("Group registry is full")
            group = {"id": "group-" + secrets.token_hex(8),
                     "conversation_id": "room-" + secrets.token_hex(12),
                     "name": name.strip(), "models": members,
                     "approval_modes": approvals, "project_id": project, "created_at": utc_timestamp(),
                     "execution": "sequential", "scope": "proposal_only"}
            updated = [*self.groups, group]
            _save(self.groups_file, {"schema_version": 1, "groups": updated})
            self.groups = updated
            return dict(group)

    def update_group(self, group_id: str, models: Any, project_id: str | None,
                     registered: list[str], approval_modes: Any = None) -> dict[str, Any]:
        members = self._validate_members(models, registered)
        project = self.validate_project(project_id)
        with self.lock:
            target = self.get_group(group_id)
            approvals = self._validate_approvals(approval_modes, members, target.get("approval_modes"))
            updated_group = {**target, "models": members, "approval_modes": approvals,
                             "project_id": project}
            updated = [updated_group if g["id"] == group_id else g for g in self.groups]
            _save(self.groups_file, {"schema_version": 1, "groups": updated})
            self.groups = updated
            return dict(updated_group)
