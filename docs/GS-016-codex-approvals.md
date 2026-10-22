# GS-016 — Codex worker and user-selectable approval settings (pilot)

## What is implemented

A new **Codex** tab in Ground Space permits the local owner to set approvals separately for all projects or any registered project:

| Mode | Effect |
| --- | --- |
| **Ask every time** (default) | A proposed read-only code review remains `pending_approval` until the owner selects Approve or Reject. |
| **Automatic read-only review** | The read-only Codex CLI review starts without a second approval click. |
| **Codex off** | New reviews cannot start; pending reviews in that project cannot be approved. |

Regardless of choice, **the pilot cannot edit files, use a writable sandbox, install packages or perform production task execution.** Approval grants permission to perform *one read-only analysis*, not general development. Existing Ground Space local agent and Administrator task permissions remain unchanged.

Preferences are persisted in private local app state (`codex_approval.json`) and the review queue in `codex_jobs.json`. No Codex keys or session tokens are saved by Ground Space. Existing Codex CLI authentication on the ASUS is reused. Every mutating HTTP request uses the existing CSRF protection and exact allowed Tailscale origin. The backend chooses the Codex binary and workspace path; the browser cannot supply executable flags, shell commands, or arbitrary local paths.

**Identity limitation:** This is a **single-owner private-tailnet pilot**. Ground Space does not yet have individual account logins, so it cannot safely offer independent per-person preferences. The design is project-scoped now and can become truly per-user only after an authenticated multi-tenant identity layer is built. Do not make the current endpoint public or invite untrusted tailnet users.

**Usage limitation:** Codex uses its signed-in ChatGPT plan/allowance or API credits depending on the CLI login. Unlike local Ollama, Codex is not guaranteed free.

## On the ASUS (before enabling)

1. Ensure `codex` is installed and can be found by the Windows user running Ground Space.
2. In PowerShell, run `Get-Command codex`, `codex --version`, and `codex login status`. Sign in using the **Codex CLI** if prompted. A signed-in Codex desktop app does not necessarily mean the CLI is installed or has a working session.
3. Inspect `codex exec --help` and confirm the installed version supports `--sandbox read-only` and `--ask-for-approval never`. The background worker will fail safely if your local CLI version does not support its hard-coded arguments.
4. Open the registered project folder. File paths must stay within Ground Space's existing allowed roots.

## Switch to this development branch (ASUS PowerShell)

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git status --short
git fetch origin
git switch feature/gs-016-codex-approval-pilot
git pull --ff-only
.\tools\restart_gs016_codex.ps1
```

The last command is a **read-only preflight**, confirming the correct repo branch, local service, Tailscale hostname and route without stopping anything. After confirming its output, explicitly restart **only** the validated Ground Space Python process:

```powershell
.\tools\restart_gs016_codex.ps1 -Restart
```

**Do not** run `tailscale serve reset`, `tailscale funnel` or restart the Data Blocks Administrator/dashboard. The GS-016 script only restarts the Ground Space Python HTTP service on 127.0.0.1:8765; existing Tailscale Serve port 8443 and the legacy dashboard remain untouched. If the safety checks refuse, investigate rather than disabling them.

## iPhone Safari functional check

Open the same private Ground Space HTTPS `:8443` address using Tailscale.

1. Open the **Codex** tab. The app should show whether Codex CLI is detected on the ASUS. If not, review requests are disabled, but approval settings remain adjustable.
2. Choose a project and **Ask every time**, then Save. Request a code review. It should appear as **pending approval**, and Codex should not be invoked until Approve is tapped.
3. Tap Reject on a pending job and confirm it becomes **rejected**.
4. Request another review and tap Approve. It should progress from **running** to **completed** (or show an actionable CLI failure).
5. Select **Automatic read-only review** for one project; that project's next review may run without a second click, but still cannot write files.
6. Set **Codex off** for that project and confirm subsequent requests are rejected. Verify other projects still obey the owner default.
7. Refresh Safari and verify the chosen approval mode and existing job history persist; test regular Qwen/Granite chat, Group, Agents, Tasks and the existing Data Blocks dashboard.

## Safety and rollback

- Always default to manual; do not automatically promote Codex plans into Administrator project-write permission.
- The pilot sends your review instructions and repository context to the connected Codex service. Avoid sensitive projects until data-handling and account controls are agreed.
- Only enable `auto_read_only` for projects you trust; as with all AI-assisted tools, sandbox mechanisms and Windows local environment support should be verified on the target device.
- The process permits up to 50 recorded review jobs and uses a 180-second time limit per invocation. In-flight jobs interrupted by app restart are recorded as **interrupted** rather than silently reported as completed.
- If problems occur, use **Codex off** immediately. If a code rollback is needed, switch back to the working `feature/gs-015-functional-controls` branch with a clean working tree and restart Ground Space while preserving the Tailscale Serve mapping.
- Separate authenticating users, plan-level spending controls, dedicated OS isolation, writable Codex task execution, and per-user approval policies are **future milestones** and not present in GS-016.

## Automation evidence

`python -m unittest tests.test_gs016_codex -v` tests permission boundaries, default/manual/automatic/disabled decisions, persistent project overrides, unknown projects, missing CLI, rejection and restart recovery.

CI also runs the existing Coordinator/Tailscale/mobile checks on Windows and Linux and a real headless Chromium browser click-through covering project selection, policy saving, a pending review, owner approval, and mobile responsiveness. **CI does not use a live ChatGPT account**, so local CLI authentication and actual Codex code review results must still be verified on the ASUS.
