"""Append-only JSONL audit records for message exchange."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self._lock = Lock()

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]
