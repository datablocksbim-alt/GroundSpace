"""Safe, local-only Coordinator routing for Ground Space group conversations.

Routing a chat reply does not approve or dispatch any project work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MENTION = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9][A-Za-z0-9._:/-]{0,127})")
CLOUD_ALIASES = frozenset({"chatgpt", "openai", "claude", "anthropic"})


@dataclass(frozen=True)
class GroupRoute:
    models: tuple[str, ...]
    coordinator: bool


def coordinator_model(group_models: list[str]) -> str:
    """Prefer a local generalist if registered; otherwise use the first group member."""
    if not group_models:
        raise ValueError("Coordinator requires at least one registered group model")
    return next((model for model in group_models if model.casefold().startswith("ministral")), group_models[0])


def resolve_specialist(name: str, group_models: list[str]) -> str:
    """Resolve an @mention against the room only, without cloud fallback."""
    alias = name.casefold().rstrip(".")
    if alias in CLOUD_ALIASES:
        raise ValueError(f"@{name} is not connected; cloud models are disabled")
    exact = [model for model in group_models if model.casefold() == alias]
    if exact:
        return exact[0]
    family = [model for model in group_models if model.casefold().startswith(alias)]
    if not family:
        raise ValueError(f"@{name} is not a registered model in this group")
    if alias == "qwen":
        coder = next((model for model in family if model.casefold().startswith("qwen2.5-coder")), None)
        if coder:
            return coder
    if len(family) > 1:
        raise ValueError(f"@{name} is ambiguous; use the exact model name after @")
    return family[0]


def route_group_message(prompt: str, group_models: list[str], *, force_coordinator: bool = False) -> GroupRoute:
    """Unaddressed chat and all planning notes go to Coordinator only.

    A direct @model mention sends just a chat response to that model.
    Multiple explicit specialists may answer sequentially through existing GPU lock.
    """
    if force_coordinator:
        return GroupRoute((coordinator_model(group_models),), True)
    mentions = [match.group(1).rstrip(".") for match in MENTION.finditer(prompt)]
    if not mentions or all(name.casefold() == "coordinator" for name in mentions):
        return GroupRoute((coordinator_model(group_models),), True)
    if any(name.casefold() == "coordinator" for name in mentions):
        raise ValueError("Mention Coordinator or specialist models, not both in the same message")
    selected: list[str] = []
    for name in mentions:
        model = resolve_specialist(name, group_models)
        if model not in selected:
            selected.append(model)
    return GroupRoute(tuple(selected), False)


def coordinator_instructions(user_prompt: str, *, group_models: list[str], kind: str | None = None,
                             goal_id: str | None = None) -> str:
    """Tool-free planning instructions; proposals are never executable queue tasks."""
    room_members = ", ".join(group_models)
    planning = (
        "For this goal, propose up to three numbered task cards. Each proposed card "
        "must have title, suggested model from room members, proposed deliverable, "
        "acceptance check, dependencies, and status PROPOSED. Clearly say no tasks were "
        "assigned or executed; owner approval will be required for future dispatch."
        if kind == "goal" else
        "For this milestone, explain its relation to the current goal and propose "
        "acceptance checks; do not claim to assign or execute work."
        if kind == "milestone" else
        "Answer the user's chat message directly and briefly."
    )
    return (
        "You are Coordinator, the default named participant in this Ground Space room. "
        "You are powered by a local Ollama model, have no tools, and cannot browse "
        "project files, approve tasks, modify files, run code, or call cloud APIs. "
        "Never claim work was completed based only on a chat response. "
        f"Allowed group models: {room_members}. "
        f"Goal reference: {goal_id or 'none'}. {planning}\n\n"
        f"User message:\n{user_prompt}"
    )
