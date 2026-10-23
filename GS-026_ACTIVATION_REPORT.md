# GS-026 activation report

**Prepared:** 2026-10-23 (Australia/Sydney)  
**Release branch:** `feature/gs-026-mobile-agent-model-controls`  
**Activation status:** Not deployed. Production remains GS-021.

## 1. Current ASUS deployment inventory

- Production checkout: `D:\000_AI Project\002 Datablocks Ground Space`
- Production branch/commit: `feature/gs-021-codex-execution` at `be56cae`
- Live process: PID 39392, `ground_space.webapp --port 8765 --no-browser`
- Live identity: `backend_release: GS-021`, loopback `127.0.0.1:8765`
- Private state: `%LOCALAPPDATA%\DataBlocks\GroundSpace\private`
- State inventory: 2 projects, 2 groups, 9 conversation threads, 39 queue tasks,
  11 Codex jobs, 3 registered Ollama models, 0 running Codex jobs at validation.
- Private Tailscale route is healthy and unchanged:
  `https://administrator.tailcd2042.ts.net:8443` proxies to loopback port 8765.
- A separate pre-existing GS-026 preview process was observed on loopback port
  8766. It was not stopped or reused.
- Windows scheduled task `DataBlocks Local Services Recovery` starts Ollama,
  Open WebUI, the legacy dashboard, and Administrator queue recovery at sign-in.
  It does **not** start Ground Space. Ground Space therefore does not currently
  recover automatically after a reboot. A reboot is not required for GS-026.

## 2. Git verification

- Preview checkout: `D:\000_AI Project\GroundSpace-GS026-Preview`
- Fetched handover commit: `7e8326b95dd083f30ebcd31bcf151222ce1b8705`
- Draft PR: #26 (existing; not merged)
- GS-022 through GS-026 are present only in the feature branch and are not loaded
  by the GS-021 production process.
- No changes were made to `main`, Pyrene, Tailscale, firewall settings, or the
  GS-021 checkout/state.

## 3. Validation results

| Gate | Result |
|---|---|
| Focused GS-026/GS-025/security/approval tests | 65 passed |
| Entire ASUS Python + Administrator suite | 147 passed |
| JavaScript syntax | Passed |
| PowerShell script parsing | Passed |
| Chromium mobile 390×844 workflow | Passed |
| Chromium desktop 1280×800 workflow | Passed |
| GS-021 live identity/no-running-job gate | Passed |
| Private Tailscale Serve read-only check | Passed |
| Physical iPhone Safari | Pending owner test |

The full test suite can emit a background traceback after the intentionally
offline Ollama test removes its temporary directory. The test itself passes;
this is test-cleanup noise rather than a production-state mutation.

## 4. Bugs found and fixed

1. The Windows full-suite gate compared an 8.3 temporary path (`KARLDA~1`)
   against the same canonical long path (`Karl Dale`) as different strings.
   The assertion now compares resolved paths.
2. An unsupported Codex model was rejected by the CLI without fallback, but the
   UI categorized the error as a sandbox failure because CLI diagnostics also
   contained `sandbox: read-only`. Unsupported-model classification now takes
   precedence and states that Ground Space did not switch models.
3. Local browser validation had a Playwright package but no downloaded bundled
   Chromium. The test runner now accepts an explicit Playwright module and an
   installed Chrome/Edge executable; the ASUS gate discovers the bundled Codex
   Playwright module and installed browser without adding project dependencies.

## 5. GS-021 → GS-026 compatibility

A consistency-checked backup was restored into an isolated state directory and
started twice as GS-026 on loopback port 8767. Production port 8765 was queried
afterward and still reported GS-021.

Loaded from the restored copy:

- 2 projects
- 2 groups
- 9 conversation threads
- 39 queue task records
- 11 Codex job records

Existing Codex approval defaults and two project overrides were identical after
restart. A new direct Codex model profile (`gpt-6.1-sol`, High) persisted across
the simulated restart. The new `agent_model_profiles.json` is additive; the
original GS-021 state was never opened by GS-026.

## 6. Backup and rollback readiness

`tools/backup_ground_space_state.ps1` performs an optimistic consistent
snapshot without stopping production:

1. verifies the exact live release and zero running Codex jobs;
2. hashes every durable source file;
3. copies to a unique owner-local backup directory;
4. hashes the source again and rejects any copy window containing a change;
5. verifies every copied hash and parses every JSON/JSONL record;
6. writes `BACKUP_MANIFEST.json` outside the source state.

Verified backup:

`%LOCALAPPDATA%\DataBlocks\GroundSpace-Backups\GS-021-20261023-145122`

An earlier independently created backup was restored and booted successfully as
the compatibility test. Backups and compatibility state remain owner-local and
are not committed or uploaded.

Rollback is supported by retaining the untouched GS-021 checkout and verified
backup. Rollback requires the GS-026 process to be stopped first, restoring the
backup while no Ground Space process is accessing the state, then starting the
GS-021 checkout. Do not overwrite live state while either version is running.

## 7. Mobile UI and Codex models

Automated Chromium confirmed on iPhone-sized and desktop viewports:

- Groups and Projects are primary navigation.
- Private AI chats are compact/collapsible.
- Task labels are shortened and full detail remains accessible.
- Chat uses the available viewport without horizontal task/model overflow.
- Project selection, group chat, Co-work, approvals, and navigation work.
- Claude is disabled and labelled **Not connected**.

Authenticated CLI evidence:

- `codex-cli 0.163.0-alpha.11`
- Login status: ChatGPT authenticated
- Explicit model `gpt-6.1-sol` completed read-only Low, Medium, and High jobs
  through the isolated GS-026 backend.
- Answers: `GS026-low-OK`, `GS026-medium-OK`, `GS026-high-OK`.
- Filesystem manifests before/after each run were identical.
- All jobs remained pending until the manual approval endpoint was called.
- `ground-space-definitely-unsupported-model` failed explicitly with its
  requested model ID retained; no silent model substitution occurred.
- Mocked regression tests additionally confirm direct/group profile separation,
  group `@Codex`, Co-work propagation, CLI argument placement, malformed input
  rejection, and unchanged approval boundaries.

## 8. Remaining blockers and manual acceptance

- Physical iPhone Safari has not been operated during this validation. Record it
  as pending until the owner checks the existing private `:8443` URL after an
  approved cutover.
- Ground Space is not included in the current Windows sign-in recovery task.
  Do not reboot expecting automatic recovery. Adding it is a separate owner-
  approved operational change.
- GS-025/026 security protections are present in the candidate but are not active
  on the currently running GS-021 backend until cutover.
- This remains a single-owner, private-Tailscale service. Public hosting and
  independent user accounts remain blocked.

### Post-validation activation guard correction

During independent release review, the activation helper was found to reject the intentionally detached GS-026 preview worktree. This was a release-blocking mismatch in the *procedure*, not a regression in the running GS-021 server. The helper now requires a separate Git worktree, accepts detached HEAD only when it matches the fetched remote feature branch, and validates that an existing server reports a recognised Ground Space release before attempting any stop.

**The new helper revision has not been live-tested on the ASUS.** Re-run the updated CI and a **non-restarting preflight** on the ASUS before a production cutover. The prior 147-pass and live CLI results apply to the earlier reviewed commit; they do not certify the revised restart helper.

## 9. Owner-approved production activation commands

Run these only in an agreed maintenance window. The final restart command is the
production activation gate and requires explicit owner approval.

```powershell
Set-Location -LiteralPath 'D:\000_AI Project\GroundSpace-GS026-Preview'
$dirty = @(git status --porcelain)
if ($LASTEXITCODE -ne 0 -or ($dirty | Where-Object { $_ })) { throw 'Preview worktree has uncommitted files or Git status failed' }
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
git switch --detach origin/feature/gs-026-mobile-agent-model-controls
if ($LASTEXITCODE -ne 0) { throw 'Cannot check out the verified release commit' }

# Non-disruptive release gate. Must pass while GS-021 remains live.
.\tools\check_gs026_asus.ps1 -AllowLegacyGS021 -Browser

# Consistency-checked, owner-local pre-cutover backup.
$backup = .\tools\backup_ground_space_state.ps1 -ExpectedRelease GS-021
$backup

# Read-only activation preflight: identifies process, route and active jobs.
.\tools\restart_gs016_codex.ps1

# STOP HERE until Karl explicitly approves production activation.
.\tools\restart_gs016_codex.ps1 -Restart -EnableCodexWrite

# Verify identity, preserved record counts and private route after cutover.
$local = Invoke-RestMethod 'http://127.0.0.1:8765/api/bootstrap'
if ($local.backend_release -ne 'GS-026') { throw 'GS-026 activation failed' }
$local.workspaces.projects.Count
$local.workspaces.groups.Count
$local.conversations.PSObject.Properties.Count
$local.tasks.Count
Invoke-WebRequest 'https://administrator.tailcd2042.ts.net:8443/api/bootstrap' -UseBasicParsing
tailscale serve status
```

After activation, physically test iPhone Safari: group navigation, project
selection, model dialog, manual Codex approval, Co-work progress, Tasks detail,
refresh persistence, and keyboard layout.

### Rollback procedure

Rollback is an owner-approved production operation. First capture the failed
GS-026 state separately for diagnosis. Stop only the positively identified
`ground_space.webapp --port 8765` process. With no listener on 8765, move the
current `%LOCALAPPDATA%\DataBlocks\GroundSpace\private` directory to a unique
quarantine name, copy the verified backup contents (excluding
`BACKUP_MANIFEST.json`) into a new `private` directory, then run the guarded
GS-021 restart helper from the untouched production checkout:

```powershell
Set-Location -LiteralPath 'D:\000_AI Project\002 Datablocks Ground Space'
.\tools\restart_gs016_codex.ps1 -Restart -EnableCodexWrite
```

Verify `backend_release: GS-021`, the preserved counts, port 8765, and the
private Tailscale URL. Never restore files over a running process.

## 10. Recommendation

**CONDITIONAL GO pending revalidation of the corrected detached-worktree activation guard and explicit owner approval.**

The candidate passes the complete Python suite, security/model tests, real
Chromium mobile/desktop workflows, live authenticated model checks, consistent
backup creation, and isolated restore/restart compatibility. The predecessor
checkout and state backup are protected.

**NO-GO for unattended deployment or reboot.** Production must not be restarted
without Karl's separate approval, physical iPhone Safari remains pending, and
Ground Space currently has no verified automatic restart after Windows sign-in.
