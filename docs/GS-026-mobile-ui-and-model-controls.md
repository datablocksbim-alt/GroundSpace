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

## Non-destructive ASUS preview (GS-025 stays running)

**Never switch the existing GS-025 working checkout just to try GS-026.**
The approved GS-025 installation and Tailscale Serve mapping on port 8765 stay unchanged. Do not run `restart_gs016_codex.ps1 -Restart` until the owner explicitly approves cutover.

Open a PowerShell window **in the existing Ground Space repository**, then create a separate Git worktree at a new path. Stop if the proposed preview folder already exists; don't delete any existing directory.

```powershell
$root = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Open PowerShell in the Ground Space repository' }
$preview = 'D:\000_AI Project\GroundSpace-GS026-Preview'
if (Test-Path -LiteralPath $preview) { throw 'Preview path already exists; investigate before continuing' }
git -C $root fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
git -C $root worktree add --detach $preview origin/feature/gs-026-mobile-agent-model-controls
if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated GS-026 preview' }
Set-Location -LiteralPath $preview
git rev-parse --short HEAD
```

Run the cross-platform portable regression tests and syntax checks from that **preview** directory (no service restart):

```powershell
py -3 -m unittest tests.test_gs026_model_profiles tests.test_gs026_model_controls tests.test_gs025_public_security tests.test_gs024_device_login tests.test_gs023_collaboration tests.test_gs018_codex_agent tests.test_gs017_group_approvals tests.test_gs016_codex -v
if ($LASTEXITCODE -ne 0) { throw 'GS-026 regression failed; leave GS-025 running' }
node --check web/public/app.js
if ($LASTEXITCODE -ne 0) { throw 'GS-026 JavaScript parsing failed' }
```

For a local-only **UI preview**, start a second server on 127.0.0.1:8766 with isolated disposable state. It won't show the existing user's chats, projects or linked agents because no GS-025 state is copied. It must not be routed through Tailscale Serve.

```powershell
$previewState = Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace-GS026-Preview'
$env:GROUND_SPACE_DEPLOYMENT_MODE = 'owner_private'
$env:GROUND_SPACE_CODEX_WRITE_ENABLED = '0'
$env:GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED = '0'
Remove-Item Env:GROUND_SPACE_TAILSCALE_ORIGIN -ErrorAction SilentlyContinue
py -3 -m ground_space.webapp --port 8766 --state-dir $previewState --no-browser
```

Open `http://127.0.0.1:8766` **on the ASUS only** and verify the compact navigation and Tasks layout. Stop the preview with Ctrl+C. Existing port 8765 and its Tailscale URL remain untouched. Do not test project writes in the preview.

### Owner-gated cutover, not yet authorised

A final release decision still requires the owner to run the full ASUS-local integration suite and live Codex model/effort tests against a disposable project, then physically check iPhone Safari. In particular, mocked subprocess tests prove the `--model` and reasoning `-c` flags are constructed, **not** that the signed-in account accepts a named model ID. Before any live rollout, back up owner-local GS-025 state, confirm no running Codex jobs, agree a rollback method and approve the guarded restart explicitly. A separate worktree alone does not keep two servers' shared state safe unless `--state-dir` is isolated as above.

## Release boundaries

CI covers mocked CLI model flags, durable profiles, invalid/malicious model IDs, group-versus-direct scoping, Co-work setting propagation, Windows/Linux regressions, and actual Chromium 390px + desktop interactions. It **cannot** certify a real provider entitlement, iPhone Safari rendering, external Administrator dependency, or safe public-user machine execution.

GS-026 remains a private owner-only improvement; public multi-user operations stay blocked under GS-025 safeguards.
