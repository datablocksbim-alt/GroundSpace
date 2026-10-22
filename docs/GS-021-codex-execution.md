# GS-021 — Codex workspace execution repair

## Architecture

Ground Space remains the approval and routing layer. `CodexPilot` accepts only registered project IDs, resolves the server-owned project path, persists a job, and waits for the applicable manual or group approval policy. An approved job starts the authenticated local Codex CLI with the selected project as both the process working directory and explicit `-C` workspace root.

Writable jobs use Codex `workspace-write`; read-only reviews use `read-only`. Both are noninteractive, ephemeral CLI runs. Ground Space never uses `danger-full-access`, never bypasses the sandbox, never accepts a browser-supplied path, and never gives Ollama agents Codex permissions.

## Diagnostics and runtime identity

Every CLI completion appends an owner-local diagnostic record to `%LOCALAPPDATA%\DataBlocks\GroundSpace\private\codex_diagnostics.jsonl`. Records contain the job ID, exit code, selected workspace, CLI argument shape, and redacted stderr. Common tokens, secrets, bearer values, and email addresses are removed before persistence. Raw diagnostics are not returned by the web API or rendered in chat.

The bootstrap response exposes `backend_release: GS-021`. The guarded restart helper requires this value during health checking, preventing an old process from being mistaken for the updated backend.

## CLI contract

The verified ASUS CLI is `codex-cli 0.163.0-alpha.11`. Ground Space uses the supported global approval flag before `exec`:

```text
codex --ask-for-approval never exec --sandbox workspace-write --skip-git-repo-check --ephemeral --color never -C <registered-project> -
```

The task prompt is supplied on stdin. The child inherits the authenticated owner's environment without logging it. Ground Space adds only `NO_COLOR=1` and captures UTF-8 output with replacement for malformed terminal bytes.

## Verification boundary

Automated tests cover manual approval, rejection, auto-read-only, trusted group auto-approval, one-running-job enforcement, registered-path enforcement, sandbox selection, command shape, and credential redaction. Live file-operation evidence must use only `D:\000_AI Project\Codex Test`; success requires filesystem inspection after create, execute, edit, execute, and delete jobs.
