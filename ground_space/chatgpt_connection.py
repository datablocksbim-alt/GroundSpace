"""Owner-only ChatGPT device-code sign-in via the official Codex app-server.

This is *not* multi-user OAuth. The login belongs to the local Codex CLI service
account. Passwords, OAuth tokens, and auth.json are never touched by Ground Space.
The device flow is only usable after explicit ASUS env opt-in.
"""
from __future__ import annotations

import atexit
import json
import os
import queue
import re
import shutil
import subprocess
import threading
from typing import Any, Callable
from urllib.parse import urlparse

from .security import assert_private_owner_mode

USER_CODE = re.compile(r"^[A-Za-z0-9-]{4,64}$")
TRUSTED_DEVICE_HOSTS = frozenset(("auth.openai.com", "chatgpt.com"))
MAX_RPC_WAIT = 20


class CodexAppServerClient:
    def __init__(self, *, executable: str | None = None, popen: Callable[...,Any] = subprocess.Popen):
        self.executable = executable
        self.popen = popen
        self.lock = threading.RLock()
        self.proc = None
        self.pending: dict[int,queue.Queue] = {}
        self.next_id = 1
        self.events: list[str] = []
        self.login_state = "not_started"
        self.last_error = ""
        atexit.register(self.close)

    def enabled(self) -> bool:
        return os.environ.get("GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED") == "1"

    def _ensure(self) -> None:
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                return
            executable = self.executable or shutil.which("codex")
            if not executable: raise ValueError("Codex CLI is unavailable on this ASUS")
            self.proc = self.popen([executable,"app-server"],
                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                 text=True,encoding="utf-8",errors="replace",bufsize=1,shell=False)
            self.pending.clear()
            self.next_id = 1
            self.events.clear()
            self.login_state = "not_started"
            threading.Thread(target=self._read_messages,daemon=True).start()
        self._rpc("initialize",{"clientInfo":{"name":"ground_space","version":"0.4"},
                                "capabilities":{}},timeout=10)
        self._notify("initialized",{})

    def _read_messages(self) -> None:
        proc=self.proc
        try:
            for line in proc.stdout:
                try: item=json.loads(line)
                except (ValueError,TypeError): continue
                if not isinstance(item,dict):continue
                mid=item.get("id")
                if isinstance(mid,int):
                    with self.lock:
                        waiting=self.pending.get(mid)
                    if waiting is not None:waiting.put(item)
                else:
                    event=item.get("method")
                    if event=="account/login/completed":
                        result=item.get("params") or {}
                        with self.lock:
                            self.login_state="connected" if result.get("success") else "failed"
                            self.last_error="Login failed or cancelled" if not result.get("success") else ""
                    elif event=="account/updated":
                        with self.lock:
                            self.events.append("account_updated")
        finally:
            with self.lock:
                for waiting in self.pending.values():
                    waiting.put({"error":{"message":"Codex app-server disconnected"}})

    def _notify(self,method: str,params: dict[str,Any]) -> None:
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError("Codex app-server is not running")
            self.proc.stdin.write(json.dumps({"method":method,"params":params})+"\n")
            self.proc.stdin.flush()

    def _rpc(self,method: str,params: dict[str,Any]|None=None, *, timeout: int = MAX_RPC_WAIT) -> dict[str,Any]:
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError("Codex app-server is not running")
            mid=self.next_id
            self.next_id+=1
            waiting: queue.Queue = queue.Queue(maxsize=1)
            self.pending[mid]=waiting
            try:
                self.proc.stdin.write(json.dumps({"id":mid,"method":method,
                    "params":params if params is not None else {}})+"\n")
                self.proc.stdin.flush()
            except (OSError,ValueError):
                self.pending.pop(mid,None)
                raise RuntimeError("Cannot write to Codex app-server")
        try:
            response=waiting.get(timeout=timeout)
        except queue.Empty as exc:
            raise RuntimeError("Codex app-server request timed out") from exc
        finally:
            with self.lock:self.pending.pop(mid,None)
        if response.get("error"):
            # Provider errors can include account details: do not echo raw text.
            raise RuntimeError("Codex app-server rejected the request. Check the CLI login and version on the ASUS.")
        result=response.get("result",{})
        if not isinstance(result,dict):raise RuntimeError("Unexpected Codex app-server response")
        return result

    @staticmethod
    def safe_device_response(response: dict[str,Any]) -> dict[str,str]:
        url=response.get("verificationUrl","")
        code=response.get("userCode","")
        login_id=response.get("loginId","")
        parsed=urlparse(url) if isinstance(url,str) else None
        if not parsed or parsed.scheme!="https" or parsed.hostname not in TRUSTED_DEVICE_HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError("Untrusted Codex verification URL")
        if not isinstance(code,str) or not USER_CODE.fullmatch(code):
            raise ValueError("Invalid Codex device code")
        if not isinstance(login_id,str) or len(login_id)>128 or not login_id:
            raise ValueError("Missing Codex login ID")
        return {"verification_url":url,"user_code":code,"login_id":login_id}

    def start_device_login(self) -> dict[str,str]:
        assert_private_owner_mode()
        if not self.enabled():
            raise ValueError("Owner ChatGPT connection is disabled on the ASUS")
        self._ensure()
        result=self._rpc("account/login/start",{"type":"chatgptDeviceCode"})
        safe=self.safe_device_response(result)
        with self.lock:self.login_state="pending"
        return safe

    def status(self) -> dict[str,Any]:
        data={"scope":"single_owner_codex_cli","enabled":self.enabled(),
              "supported_method":"chatgptDeviceCode","connected":False,
              "auth_mode":None,"plan_type":None,"login_state":self.login_state}
        if not self.enabled():return data
        try:
            self._ensure()
            account=self._rpc("account/read",{"refreshToken":False})
            details=account.get("account")
            if isinstance(details,dict):
                mode=details.get("type")
                if mode in ("chatgpt","apiKey"):
                    data["auth_mode"]=mode
                    data["connected"]=True
                    plan=details.get("planType")
                    if isinstance(plan,str) and len(plan)<40:
                        data["plan_type"]=plan
            data["login_state"]="connected" if data["connected"] else self.login_state
        except (OSError,ValueError,RuntimeError):
            data["login_state"]="unavailable"
        return data

    def close(self) -> None:
        with self.lock:
            proc=self.proc
            self.proc=None
        if proc is not None and proc.poll() is None:
            try:proc.terminate()
            except (OSError,ValueError):pass
