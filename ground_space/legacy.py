"""Loader for the Administrator's existing PersistentQueue implementation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_task_queue(administrator_root: Path) -> ModuleType:
    source = administrator_root.resolve() / "orchestrator" / "task_queue.py"
    if not source.is_file():
        raise FileNotFoundError(f"Administrator queue interface not found: {source}")
    spec = importlib.util.spec_from_file_location("datablocks_administrator_task_queue", source)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Administrator queue interface: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
