# GS-026 — iPhone-first collaboration navigation and model controls

**Status:** GS-026 code remains a draft, unmerged feature branch. GitHub portable CI covers Windows/Linux and headless mobile-sized Chromium; iPhone Safari and ASUS Codex CLI are manual gates. The ASUS was observed running **GS-021**, not GS-025, on port 8765. No upgrade or live restart has occurred.

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

## Non-destructive ASUS preview (the existing GS-021 stays running)

**Never switch the existing GS-021 working checkout just to try GS-026.**
The observed ASUS server is GS-021 on port 8765. Keep its checkout, private state and Tailscale Serve mapping unchanged. Do not run `restart_gs016_codex.ps1 -Restart`; that script expects the GS-026 branch and would not be an appropriate unattended migration procedure.

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

Run the guarded verification script in the isolated preview worktree. It checks GS-026 model controls and prior security/approval regressions, and validates frontend JavaScript. It refuses the primary installation checkout.

```powershell
.\tools\prepare_gs026_preview.ps1
```

After **PRECHECK PASS**, launch a separate, desktop-only UI preview on `http://127.0.0.1:8766`:

```powershell
.\tools\prepare_gs026_preview.ps1 -StartPreview
```

Stop the preview with Ctrl+C. The preview uses `%LOCALAPPDATA%\DataBlocks\GroundSpace-GS026-Preview` as private state and deliberately does **not** import the existing GS-021 chats, projects, linked accounts or agent settings. It cannot be accessed from the iPhone through the existing Tailscale route, because Tailscale Serve remains pointed at port 8765. This preview is **not** a live Codex account or iPhone Safari acceptance test.

#### Optional Windows reboot after owner approval

Rebooting the ASUS is separate from restarting the Ground Space application. First save work, verify no active Codex tasks, and make sure you can sign back in. **Only when deliberately ready**, run from PowerShell:

```powershell
shutdown.exe /r /t 60 /c "Ground Space maintenance reboot"
```

Cancel the pending reboot within 60 seconds with `shutdown.exe /a`. A reboot stops the running Ground Space server; do not assume it will automatically start again unless a verified Windows startup task/service exists. Recheck the app and private Tailscale access after sign-in. These commands are instructions only; nothing in GS-026 runs them automatically.

### Full ASUS automated gate (no restart)

After the isolated preview check, run this **from the GS-026 preview worktree** to inspect the existing GS-021 server and the external ASUS-only Administrator integration before discussing a live cutover. GS-021 must be explicitly authorized as the observed legacy version:

```powershell
.\tools\check_gs026_asus.ps1 -AllowLegacyGS021
```

It checks the existing port-8765 server reports exactly `GS-021` (or `GS-025`), refuses if Codex jobs are running, checks private Tailscale Serve status **without modifying it**, replays the focused GS-026 checks, and runs the entire local Ground Space/Administrator suite. It explicitly warns that GS-025 protections are **not** currently active on the GS-021 server. Add `-Browser` only when Playwright and its Chromium browser are already installed on that machine. The script **does not** invoke Codex with live model credentials and **does not** start or stop any production process. A clean result is an automated **preflight**, not completion of owner-only Codex entitlement, physical Safari or rollback checks.

A Windows reboot is **not required** for GS-026. Keep it deferred unless the owner separately wants a maintenance reboot; a reboot may stop Ground Space until its startup behavior is verified.

### Owner-gated cutover, not yet authorised

A final release decision still requires the owner to run the full ASUS-local integration suite and live Codex model/effort tests against a disposable project, then physically check iPhone Safari. In particular, mocked subprocess tests prove the `--model` and reasoning `-c` flags are constructed, **not** that the signed-in account accepts a named model ID. Before any live rollout, positively identify the port-8765 process, make a consistent offline backup of owner-local GS-021 state, confirm no running Codex jobs, validate GS-021 data compatibility in an isolated copy, agree a tested rollback method and approve the guarded restart explicitly. A separate worktree alone does not keep two servers' shared state safe unless `--state-dir` is isolated as above.

## Release boundaries

CI covers mocked CLI model flags, durable profiles, invalid/malicious model IDs, group-versus-direct scoping, Co-work setting propagation, Windows/Linux regressions, and actual Chromium 390px + desktop interactions. It **cannot** certify a real provider entitlement, iPhone Safari rendering, external Administrator dependency, or safe public-user machine execution.

GS-026 remains a private owner-only improvement; public multi-user operations stay blocked under GS-025 safeguards.
