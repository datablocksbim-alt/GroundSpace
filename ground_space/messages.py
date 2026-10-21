"""Versioned structured messages exchanged by Ground Space components."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


MESSAGE_TYPES = {"submission", "acknowledgement", "progress", "completion", "failure"}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def message(
    message_type: str,
    *,
    task_id: str,
    correlation_id: str,
    sender: str,
    recipient: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if message_type not in MESSAGE_TYPES:
        raise ValueError(f"Unsupported message type: {message_type}")
    if not all((task_id, correlation_id, sender, recipient)):
        raise ValueError("Messages require task, correlation, sender, and recipient identities")
    return {
        "schema_version": 1,
        "message_id": uuid4().hex,
        "message_type": message_type,
        "task_id": task_id,
        "correlation_id": correlation_id,
        "timestamp": utc_timestamp(),
        "sender": sender,
        "recipient": recipient,
        "payload": payload or {},
    }
