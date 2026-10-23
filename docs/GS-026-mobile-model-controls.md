# GS-026 — Mobile workspace focus and configurable online-agent models

**Status:** Code complete for private-owner testing on a stacked feature branch. Not deployed or merged.

## UI feedback implemented

- Group Chats and Projects are first in the workspace drawer.
- Private agent channels (Qwen, Administrator, Codex) live in a small, collapsed **Private AI chats** disclosure control, not as large primary navigation cards.
- The former 250px Active Agents information panel is hidden to give the conversation more room.
- Mobile Tasks show a shortened task description + full ID on a second line, and status; worker, approval and timestamp are still accessible by opening the task details. No horizontal task-table scrolling.
- iPhone composer and chat viewport behavior are preserved, including the original mobile keyboard-height handling and manual Codex approvals.

## Model and response effort controls

- From a private Codex chat, use **Model ⚙** to select the CLI default, a conditional example model, or enter a verified Codex model ID. Set Default / Low / Medium / High reasoning effort.
- From a group containing Codex, **Model ⚙** saves that group's independent Codex model and effort. These are used by both direct `@Codex` messages and the Qwen → Codex → Granite Co-work handoff.
- Persisted profiles are stored **privately on the ASUS**, separated between `codex:direct` and `codex:group:<group_id>`.
- The backend translates supported choices to `codex -c model_reasoning_effort=<effort> exec ... --model <id>`. No selected effort silently overrides Codex's sandbox, workspace restriction or manual approval policy. The job stores the requested model/effort.
- The UI clearly labels model suggestions **“if supported by CLI”**. A saved value is a preference, not proof of availability or entitlement; the actual Codex CLI confirms model access when executing a job. If it cannot run the model, the job fails without silently switching to a different one.
- **Claude is not connected**: its option is disabled. The interface makes room for a future verified Claude connector with a separate model catalog and Claude-specific supported thinking controls. It does not claim a ChatGPT login authorizes Claude.
- Local Qwen's separate Fast/Balanced/Detailed response controls remain in place, and Qwen and Granite remain proposal-only.
- No arbitrary API key, user credential, token or unvalidated model identifier is accepted.

## Validation

- Python tests `tests/test_gs026_model_profiles.py` cover persistence, per-group isolation, malformed names, unsupported providers, Codex CLI arguments and continued manual approvals.
- Existing `tests/test_gs023_collaboration.py` includes Co-work profile propagation.
- Browser `tools/test_gs015_browser.mjs` checks the compact navigation, mobile Tasks width, model-settings dialog, disabled Claude option and use of the selection in group and Co-work jobs in headless Chromium at iPhone-like and desktop viewport sizes.
- Cross-platform CI: `.github/workflows/gs026-mobile-model-controls.yml`, plus existing regression checks.

## ASUS private-owner acceptance still required

Before switching branches: protect any uncommitted work and verify no running Codex job. On the actual ASUS:

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git status --short
git fetch origin
git switch feature/gs-026-mobile-agent-model-controls
git pull --ff-only
.\tools\restart_gs016_codex.ps1
```

If preflight passes, use the existing guarded restart with Codex writable jobs and optional owner-only ChatGPT device connection:

```powershell
.\tools\restart_gs016_codex.ps1 -Restart -EnableCodexWrite -EnableChatGPTConnect
.\tools\verify_gs022_local.ps1
```

Verify `/api/bootstrap` reports `backend_release: GS-026`. On the iPhone private Tailscale URL, test group/project drawer, private AI chats icon, Tasks tap-to-expand, model settings and Co-work with an **actually supported CLI model** in the disposable `Codex Test` project. Do not start with Pyrene Mini.

**Release limits:** This remains a **single-owner, Tailscale-private** app. Independent ChatGPT/Claude users, public multi-tenant sessions and OS-isolated execution are not built. Do not publicly host, or merge stacked draft PRs without full ASUS-local tests.
