"""Portable per-installation configuration for Ground Space Community Edition."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


def default_state_dir() -> Path:
    override = os.environ.get("GROUND_SPACE_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "DataBlocks" / "GroundSpace"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "datablocks" / "ground-space"


def ollama_endpoint() -> str:
    value = os.environ.get("GROUND_SPACE_OLLAMA_ENDPOINT", "http://127.0.0.1:11434").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("GROUND_SPACE_OLLAMA_ENDPOINT must be an HTTP(S) endpoint without credentials")
    return value.rstrip("/")


def executable_inventory() -> dict[str, str | None]:
    """Detect optional local integrations without assuming installation paths."""
    return {"ollama": shutil.which("ollama"), "codex": shutil.which("codex")}
