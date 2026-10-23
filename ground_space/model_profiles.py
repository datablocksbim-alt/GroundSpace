"""GS-026: durable, per-conversation Codex CLI model/effort preferences.

This owner-only pilot deliberately does not impersonate a connected Claude provider.
Model availability and ChatGPT plan eligibility are checked by the provider on execution.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from pathlib import Path
from typing import Any

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
EFFORTS = frozenset(("", "low", "medium", "high"))
MAX_PROFILES = 100


def validated_selection(model_id: Any = "", reasoning_effort: Any = "") -> dict[str, str]:
    if not isinstance(model_id,str) or (model_id and not MODEL_ID.fullmatch(model_id)):
        raise ValueError("Invalid Codex model ID; enter a supported alphanumeric CLI model identifier")
    if not isinstance(reasoning_effort,str) or reasoning_effort not in EFFORTS:
        raise ValueError("Codex reasoning effort must be Default, Low, Medium or High")
    return {"model_id":model_id,"reasoning_effort":reasoning_effort}


class ModelProfiles:
    def __init__(self,path: Path):
        self.path=path
        self.lock=threading.RLock()
        try:
            entries=json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            entries={}
        except (OSError,ValueError) as exc:
            raise ValueError("Model settings are unreadable; preserve original file") from exc
        if not isinstance(entries,dict) or len(entries)>MAX_PROFILES:
            raise ValueError("Invalid model settings")
        for key,value in entries.items():
            if not isinstance(key,str) or not key.startswith("codex:") or not isinstance(value,dict):
                raise ValueError("Model settings have an unknown provider or scope")
            if validated_selection(value.get("model_id",""),value.get("reasoning_effort","")) != value:
                raise ValueError("Invalid model settings record")
        self.entries=entries

    @staticmethod
    def key(*,group_id: str | None = None) -> str:
        if group_id is not None and (not isinstance(group_id,str) or not group_id or len(group_id)>128 or
                                     not re.fullmatch(r"[A-Za-z0-9_-]+",group_id)):
            raise ValueError("Invalid group identifier for Codex model settings")
        return "codex:"+("group:"+group_id if group_id else "direct")

    def get(self,*,group_id: str | None = None) -> dict[str,str]:
        with self.lock:
            return dict(self.entries.get(self.key(group_id=group_id),validated_selection()))

    def set(self,*,group_id: str | None = None,model_id: str = "",
            reasoning_effort: str = "") -> dict[str,str]:
        key=self.key(group_id=group_id)
        value=validated_selection(model_id,reasoning_effort)
        with self.lock:
            update=dict(self.entries)
            if value==validated_selection():
                update.pop(key,None)
            else:
                update[key]=value
            if len(update)>MAX_PROFILES:
                raise ValueError("Too many model profiles")
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_name("."+self.path.name+"."+secrets.token_hex(5)+".tmp")
            try:
                tmp.write_text(json.dumps(update,indent=2),encoding="utf-8")
                os.replace(tmp,self.path)
            finally:
                tmp.unlink(missing_ok=True)
            self.entries=update
            return dict(value)

    def snapshot(self) -> dict[str,Any]:
        with self.lock:
            return {"provider":"codex_cli","supported_efforts":["low","medium","high"],
                "other_cloud_providers_connected":False,
                "profiles":{key:dict(val) for key,val in self.entries.items()}}
