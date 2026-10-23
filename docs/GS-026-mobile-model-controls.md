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

Use the **non-destructive, isolated preview** in [GS-026 iPhone-first validation](GS-026-mobile-ui-and-model-controls.md#non-destructive-asus-preview-gs-025-stays-running). It creates a separate Git worktree, private state directory, and loopback-only port 8766. Do **not** switch or restart the approved GS-025 installation before explicit owner approval.

The final release gate still requires the full ASUS integration suite, signed-in Codex CLI model/effort checks in a disposable project, and physical iPhone Safari verification. CI can validate argument construction and a Chromium mobile-sized viewport, but cannot certify Codex account entitlements, real workspace safety or Safari behavior.

**Release limits:** This remains a **single-owner, Tailscale-private** app. Independent ChatGPT/Claude users, public multi-tenant sessions and OS-isolated execution are not built. Do not publicly host, or merge stacked draft PRs without full ASUS-local tests.
