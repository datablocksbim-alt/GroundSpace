# GS-009 — Coordinator chat and task-card contract (design sample)

Status: **design only — not wired to chat dispatch or project-file execution**.

## Conversation rules

- In a group room, **Coordinator** is a permanent, named participant and the default respondent to unaddressed chat messages.
- A `/goal <objective>` message is saved as a **soft-yellow** planning card. Coordinator always replies with a plan and **proposed** task cards, not executed work.
- A `/milestone <description>` message stays **periwinkle**. Coordinator links it to the current goal (or asks the user to choose a goal if ambiguous).
- A direct mention such as `@Qwen` routes the **chat reply** only to that explicitly included and installed model. Coordinator does not speak over the specialist unless asked to summarize. If multiple models are mentioned, run them sequentially on the laptop.
- `@ChatGPT` or `@Claude` is unavailable while its provider adapter is unconnected; never fake a response or silently fall back to another model.
- A **direct model chat reply is not a project work assignment**. Only a separately approved task may enter the existing Administrator queue.

## Example room

**Room:** Pyrene Development | **Project:** Pyrene Mini | **Participants:** Coordinator, Qwen 2.5 Coder, Qwen 3.5, Granite

**User:** `/goal Finish the Codex tablet prototype on the third island.`

**Coordinator:** "I have prepared three proposed tasks. No project files have been accessed or changed. Approve the plan before I dispatch any work."

| ID | Assignee | Assignment | Output / check | Depends on | State |
|---|---|---|---|---|---|
| PYR-001 | Qwen 2.5 Coder | Propose Codex assembly UI and Python-node architecture | Architecture notes + acceptance tests | None | Proposed |
| PYR-002 | Qwen 3.5 | Propose NPC, robot capture and tablet-parts quest flow | Quest outline + completion criteria | None | Proposed |
| PYR-003 | Granite | Review the combined proposals for scope and risks | Review checklist and issues | PYR-001, PYR-002 | Blocked on dependencies |

**User:** `@Qwen What Godot scene structure would you recommend?`

**Qwen 2.5 Coder:** "I would propose a separate Codex panel scene with assembly-state components and a controlled Python-node editor."

**User:** `Coordinator, show task PYR-002.`

**Coordinator:** "PYR-002 is proposed, assigned to Qwen 3.5. It has not been dispatched."

## Portable task-card JSON (version 1)

```json
{
  "schema_version": 1,
  "task_id": "PYR-001",
  "goal_id": "PYR-GOAL-001",
  "milestone_id": "PYR-M1",
  "project_id": "<registered-project-id>",
  "conversation_id": "<room-conversation-id>",
  "title": "Propose Codex assembly architecture",
  "assignee": {
    "provider": "ollama",
    "model": "qwen2.5-coder:3b",
    "worker_id": "<registered-worker-id>"
  },
  "instructions": "Propose Godot Codex tablet assembly UI and a restricted Python-node design.",
  "context_refs": ["<saved-goal-note-id>"],
  "deliverables": ["Architecture proposal", "Suggested tests"],
  "acceptance_criteria": [
    "Proposed design covers assembly, programming and inventory",
    "No arbitrary player-supplied code runs on the host"
  ],
  "depends_on": [],
  "priority": "normal",
  "required_permissions": ["read", "propose"],
  "approval": {"status": "pending", "approved_by": null},
  "status": "proposed",
  "reviewer": "granite",
  "result_refs": []
}
```

## Contract and dispatch safeguards

1. A task card is a **proposal** until the user approves the specific task or an explicitly named batch. Typing `/goal`, `/milestone`, `@Qwen`, or selecting a project is **never** write or execution approval.
2. `project_id` refers to an existing validated WorkspaceRegistry project, not a raw client-supplied filesystem path. Linking a project provides metadata only.
3. The Coordinator must validate a proposed assignee against **models registered and present in that group**; an optional reviewer must also be available. Never assign to an unavailable model or online provider by inference.
4. Validate required permissions against the worker's capabilities; for this design stage only `read` and `propose` are allowed. Keep current path restrictions, queue approval, worker isolation and audit logging in force.
5. Dependency checks require that every `depends_on` ID resolves to a task in the same goal/project. Reject dependency cycles. A dependent task remains blocked until predecessors complete and review gates clear.
6. On approval, translate the card into the existing `AdministratorAdapter.submit(...)` contract, preserving `task_id`, `correlation_id`, `requested_worker`, `required_permissions`, explicit approval and `payload`. Do **not** create an alternative execution queue.
7. Status transitions for the future implementation: `proposed → approved → queued → running → review → completed`; `blocked` and `failed` must be visible and auditable. Never report `completed` merely because a model wrote text.
8. Coordinator summarizes status, problems and next decisions in chat. Review must be performed by a separate configured reviewer where required, with bounded retry attempts; file write/command execution remain disabled unless separately built and authorised.
9. **No cloud API spend:** installed Ollama models are the default. ChatGPT/Claude integration remains unconnected until explicitly configured with its own permissions and costs.

## Current implementation boundary

GS-007 currently submits normal group messages to each group model. GS-008 makes slash goals AI-aware but does **not** supply Coordinator-first routing or task approval lifecycle. This document specifies the intended GS-009 implementation; a separate tested Python coordinator and UI integration are required before any live behaviour can be claimed.
