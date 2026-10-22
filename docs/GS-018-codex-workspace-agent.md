# GS-018 — Codex as a writable agent inside Ground Space

## Outcome

Codex is **not a separate navigation feature**. It appears under **Agents → Add AI**, alongside Ollama models, when the installed and authenticated `codex` CLI is on the ASUS service user's executable PATH. Selecting Add AI registers it; registration survives server restart. It gains a direct **Codex** chat channel, can be added through any group chat's **Members** selector, and may be addressed with **@Codex**.

Codex supports **creating, editing, testing/running, and deleting files** inside a selected registered project using the Codex CLI `workspace-write` sandbox. Its access is not unrestricted machine access and is not equivalent to running as a separate unprivileged Windows account or container.

Only Codex gains workspace coding functionality; local Ollama models continue to receive no file tools and remain read/propose-only. Coordinator-only or `/goal` planning turns remain read-only, even in a group where Codex is the only agent.

## Approval policy

**Manual / Ask me is the default for Codex** in direct chats and when added to a group, including for new groups. A pending task appears in the same conversation with Approve workspace task and Reject buttons. Approval starts one scoped Codex CLI job.

Group **Approve for me** may start addressed Codex workspace tasks automatically, but only if: Codex was deliberately registered, the group has a selected project, the group Codex member's persisted approval mode is Approve for me, and the operator explicitly enabled the writable pilot on the ASUS. Off blocks routed work. Existing Qwen/Granite settings keep their previous behavior.

The earlier Codex read-only review controls now live **inside Agents**, not in a separate tab. `auto_read_only` remains backward-compatible and **does not authorize writable jobs** by itself. Only an explicit group auto-permission can enable that workflow.

## Safety model and limitations

1. The server picks the Codex executable from the local PATH and the workspace path from a pre-registered project; browser requests never specify arbitrary executable flags or a cwd. The subprocess always uses `shell=False`, `codex exec --sandbox workspace-write --ask-for-approval never` for writable runs. Actual file operations are performed by Codex and its sandbox—not by the browser.
2. Writable mode is **off by default**. Ground Space ignores any browser attempt to override it. The operator must explicitly start the Ground Space server with `GROUND_SPACE_CODEX_WRITE_ENABLED=1` (supported by the guarded restart script below).
3. The project directory must still be under an existing allowed root when execution starts. Only one Codex job may run at a time, and pending jobs are bounded. Group jobs cannot bypass approval through an HTTP `auto_approve` field.
4. **Important**: An AI agent allowed to run code may modify, overwrite or delete work. Codex's workspace sandbox is not the same as a Windows OS account or VM boundary; other locations, linked directories, environment variables, network access, and Windows-specific behavior still require local security testing. Take a backup or use a disposable test project first. Avoid sensitive credentials or projects until an isolated worker account/container or VM is deployed.
5. Codex may consume ChatGPT Codex plan allowance or API credits depending on CLI authentication. Cloud access is not necessarily AUD $0; no credit limit is enforced by this pilot.
6. **Single-owner tailnet pilot only**. Ground Space lacks multi-user authentication, approval ownership and tenant isolation. Never make it accessible via public Funnel or allow untrusted devices into this tailnet. A public multi-user release requires dedicated OS isolation and scoped user credentials.

## ASUS installation

Check the active repo has no local modifications, then retrieve the branch:

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git status --short
git fetch origin
git switch feature/gs-018-codex-workspace-agent
git pull --ff-only
```

Confirm Codex CLI availability and the sandbox options supported by the installed version:

```powershell
Get-Command codex
codex --version
codex login status
codex exec --help
```

Run the guarded read-only preflight:

```powershell
.\tools\restart_gs016_codex.ps1
```

The normal restart **leaves writes disabled**:

```powershell
.\tools\restart_gs016_codex.ps1 -Restart
```

**Only after** testing on a disposable registered project and agreeing to Codex's workspace-write risk, explicitly enable it:

```powershell
.\tools\restart_gs016_codex.ps1 -Restart -EnableCodexWrite
```

The script verifies the running Ground Space process identity and reuses Tailscale port `:8443`, leaving the old dashboard and other services alone. It never runs `tailscale serve reset` or enables public Funnel.

## Mobile Safari verification

Open the existing Ground Space private HTTPS URL with Tailscale on.

1. Go to **Agents → Add AI**. Choose `Codex — OpenAI coding agent (CLI)` and tap Add AI. Verify it appears under registered agents.
2. Return to Chat; a new **Codex** channel should appear under Chats. Select a disposable project, request a small file creation, and confirm the job is pending until manually approved.
3. Approve a task. Confirm it completes, reports exactly what was changed, and that the file exists only in the selected project. Run a small test task and then a delete task for the same disposable file.
4. Create or edit a group; enable Codex and choose **Ask me**. Send `@Codex add a unit test`. Confirm the pending approval in the group conversation.
5. Select **Approve for me** for Codex in **that** group only. After explicit ASUS writable opt-in, another `@Codex` request may run automatically. Changing it to **Off** must block new Codex requests.
6. Confirm Qwen/Granite remain read/propose-only, `/goal` planning is read-only, project browsing and the existing Data Blocks dashboard still work, and Tailscale-off blocks the mobile URL.

## Verification evidence

CI uses a **mocked Codex CLI**, so tests check sandbox command shape, approved-job gating, model registration and persistence, group routing, mobile/desktop browser controls, and existing Coordinator/Tailscale security. CI **cannot prove** the locally installed Windows Codex sandbox, actual file edits/deletes, signed-in account or iPhone Safari. Those remain release gates.
