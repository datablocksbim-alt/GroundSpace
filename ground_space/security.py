"""GS-025: safe owner-only deployment guard and bounded private API requests.

These controls DO NOT implement tenant isolation or OS-level sandboxing.
Public multi-user operation is deliberately fail-closed.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Callable


PUBLIC_FLAGS = ("GROUND_SPACE_PUBLIC_USERS", "GROUND_SPACE_ENABLE_MULTI_USER",
                "GROUND_SPACE_PUBLIC_HOSTING")


def assert_private_owner_mode() -> None:
    if os.environ.get("GROUND_SPACE_DEPLOYMENT_MODE", "owner_private") != "owner_private":
        raise RuntimeError("Public Ground Space is blocked: independent user identity and isolated workers are not installed")
    if any(os.environ.get(name,"").lower() in ("1","true","yes","on") for name in PUBLIC_FLAGS):
        raise RuntimeError("Public Ground Space is blocked: do not share this owner's Codex credentials or project files")


def security_posture() -> dict:
    return {"deployment":"owner_private","public_ready":False,"multi_user_accounts":False,
            "per_user_credential_isolation":False,"per_user_os_sandbox":False,
            "workspace_write":"owner_approved_codex_only",
            "public_access":"blocked_by_server_startup_policy"}


class RequestRateLimit:
    """Per-server sliding window. Proxied tailnet requests share the loopback key.

    A modest cap reduces accidental submission floods; it is *not* an
    authentication boundary or per-user billable usage limit.
    """
    def __init__(self, *, limit: int = 120, seconds: float = 60.0,
                 clock: Callable[[],float] = time.monotonic):
        if limit<1 or seconds<=0:raise ValueError("Invalid rate-limit configuration")
        self.limit=limit
        self.seconds=seconds
        self.clock=clock
        self.lock=threading.Lock()
        self.recent: dict[str,deque[float]]={}

    def allow(self, peer: str) -> bool:
        now=self.clock()
        with self.lock:
            hits=self.recent.setdefault(peer,deque())
            while hits and now-hits[0]>=self.seconds:
                hits.popleft()
            if len(hits)>=self.limit:return False
            hits.append(now)
            if len(self.recent)>512:
                for key in list(self.recent):
                    queue=self.recent[key]
                    while queue and now-queue[0]>=self.seconds:queue.popleft()
                    if not queue:del self.recent[key]
            return True


def require_verified_tenant(subject: str | None, project_owner: str | None) -> None:
    """Fail closed for future multi-user project actions until real OIDC exists."""
    if not subject or not project_owner or subject!=project_owner:
        raise PermissionError("A verified project owner session is required")
