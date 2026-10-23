# GS-026 — iPhone-first collaboration navigation and model controls

**Status:** Code complete on rollback-safe feature branch. Windows/Linux portable CI plus headless Chromium iPhone-size/desktop button tests passed. Actual iPhone Safari and ASUS Codex CLI model availability remain manual gates. No merge or live restart has occurred.

## UI changes

- Left navigation now presents **Group Chats** and **Projects** first. Large direct/private AI channels are now folded into a compact **Private AI chats** disclosure beneath them; Qwen, Administrator and Codex remain available.
- The wide Active Agents panel is hidden, keeping the conversation focused rather than adding a competing third column.
- Tasks display a short human-readable title, truncate safely with ellipsis, and keep the exact task ID and full JSON detail accessible on tap. Mobile Tasks fits the viewport without a horizontal scroller.
- Kept the existing iPhone drawer, fullscreen chat layout, keyboard-aware composer, CSRF token flow, per-bot approval settings and Tailscale Serve route unchanged.

## Model and reasoning control — actual supported pilot

- In a direct **Codex** chat or a group containing Codex, tap **Model ⚙** beside the project selector.
- Options: Codex CLI default, GPT-5.6 Sol, GPT-5.6 Terra, GPT-6.1 Sol, or an exact custom model ID. These are **model IDs to request**, not promised entitlements. The authenticated CLI/provider determines which model IDs work. A failed request is not silently routed to a different model.
- Reasoning effort: CLI default / Low / Medium / High. This is a real Codex CLI config value (`-c model_reasoning_effort=...`) for each subsequent job. The model ID is passed as `--model`. All arguments remain arrays with `shell=False`, and model IDs are strictly validated to prevent shell/config injection.
- Settings are stored under the owner-local private state directory in `agent_model_profiles.json`, independently for the **direct Codex channel** and **each group**. No provider credentials are written to this file.
- `@Codex` tasks and **Co-work's Codex implementation** use that group's saved model/effort. The job record retains the requested values; changes affect future jobs, not already approved/running jobs.
- **Claude:** marked **Not connected** rather than a fake working model control. An authenticated Claude integration, provider discovery and capability/effort mapping must be implemented and verified before users can apply these controls to Claude. Same principle for separate ChatGPT cloud-chat routing (distinct from the current Codex CLI agent).
- These settings do not change approval boundaries, tool privileges, project root validation or token budget reporting.

## Local rollout (owner-only ASUS)

Keep GS-025 available for rollback. Before switching:

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git status --short
git fetch origin
git switch feature/gs-026-mobile-agent-model-controls
git pull --ff-only
.\tools\restart_gs016_codex.ps1
```

If the working tree isn't clean, or the guarded preflight reports an active job, **stop**.

Then explicitly restart the private pilot (retains the existing Tailscale route):

```powershell
.\tools\restart_gs016_codex.ps1 -Restart -EnableCodexWrite -EnableChatGPTConnect
.\tools\verify_gs022_local.ps1
```

The guarded restart requires `backend_release=GS-026`, which prevents stale GS-025 backends from being mistaken for the new UI.

On iPhone, test:
1. Open Chats drawer: Group Chats and Projects lead; tap compact Private AI chats to reveal Qwen, Administrator, Codex.
2. Open Tasks with long descriptions; verify labels truncate, IDs remain visible, and tapping one opens the complete record with no horizontal page overflow.
3. Open Codex Test as a registered project. In Codex direct chat tap Model ⚙ → choose supported model/effort and save. Verify a **manually approved** CLI task prints the requested model/effort in its job record and the selected CLI model actually responds.
4. Open a group containing Qwen, Codex and Granite. Set its Codex model to a different value (or use CLI default); verify `@Codex` and Co-work use the group-specific setting and preserve Ask me approval.
5. Set custom invalid model ID to confirm the form/backend rejects unsafe values; verify Claude reads Not connected.

**No live cloud-provider charge guarantee:** signed-in Codex may consume account usage/credits. The model's availability or usage terms are determined by the connected account.

## Release boundaries

CI covers mocked CLI model flags, durable profiles, invalid/malicious model IDs, group-versus-direct scoping, Co-work setting propagation, Windows/Linux regressions, and actual Chromium 390px + desktop interactions. It **cannot** certify a real provider entitlement, iPhone Safari rendering, external Administrator dependency, or safe public-user machine execution.

GS-026 remains a private owner-only improvement; public multi-user operations stay blocked under GS-025 safeguards.
