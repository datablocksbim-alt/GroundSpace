# GS-017 — Approve for me and custom group bot approvals

Ground Space now supports approval settings **for each local AI bot in each group chat**, plus a clearer **Approve for me** label for Codex's existing automatic **read-only** mode.

## Group chat: Members → Approval settings

In a group chat, tap **Members** (or **+ New** to make a group). Every selected AI model has a separate approval selector:

| Setting | Behavior |
| --- | --- |
| **Ask me** | The model's routed read/propose message is created with *pending* owner approval. Tap **Approve reply** or **Reject** beneath that message. No inference is dispatched until approval. |
| **Approve for me** | The model's read/propose message is allowed to run automatically when Coordinator or an `@mention` routes a response to it. |
| **Off** | The model remains registered, but requests routed to it are rejected. It can be re-enabled in Members. |

The existing group behavior was automatically dispatched within read/propose limits. **Groups created before GS-017 keep that same behavior by default**. A newly added model starts in Approve for me unless the owner changes its setting. Choices persist across browser and Ground Space restarts.

The mode is **per group and per model**, not global. For example, one group can set Qwen to Approve for me and Granite to Ask me; a second group can reverse these choices. Coordinator is a *role* served by a local group model, so the underlying model's setting applies to its Coordinator messages too.

When a message addresses more than one model, the backend checks all routed models before creating tasks. Approved bot replies run under Ground Space's existing sequential GPU dispatch lock. Waiting replies cannot be processed until explicitly approved.

**Security boundaries:** The server enforces approval choices independently of browser inputs. All group tasks are still limited to **read** and **propose** permissions. The owner decision endpoint rejects tasks outside the specified group, tasks that are already decided, tasks whose model is no longer a member, and any task with different permissions (including `write`). Cross-origin requests still require a valid CSRF cookie/header and the configured private Tailscale origin. This feature never grants agent access to project files, terminal commands, deployment, Codex workspace writes, or cloud providers.

## Codex: Approve for me

The Codex tab now displays **Approve for me — read-only reviews**. This is the existing `auto_read_only` setting with clearer wording; saved preferences remain compatible. It only allows text review in Codex's explicit read-only sandbox, not code modifications. Codex may consume the owner's ChatGPT plan allowance or API credits.

## Owner-only limitation

This is a **single-owner Tailscale pilot**. Ground Space still does not authenticate individual users or provide per-person roles. Every choice belongs to this owner instance. Before a public multi-user app, add authenticated identities, tenant-level isolation, separate approval ownership, stronger OS-level worker sandboxes, billing limits, and auditing.

## ASUS deployment

After confirming the current working tree is clean, in PowerShell:

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git status --short
git fetch origin
git switch feature/gs-017-group-approval-controls
git pull --ff-only
```

GS-017 modifies Python server code, so **restart only Ground Space** after installing this branch, using the guarded GS-016 preflight/restart helper or manually restarting that single process. The helper in this branch already checks for GS-017. Run `\.\\tools\\restart_gs016_codex.ps1` for a read-only preflight, then explicitly `\.\\tools\\restart_gs016_codex.ps1 -Restart` when satisfied. The script verifies the running process before stopping it. Keep the existing Tailscale Serve `:8443` mapping, previous dashboard, Ollama and Administrator unchanged.

On the iPhone, refresh Ground Space, open group chat → **Members**, set Qwen/Granite modes, save, and send an @mention to each bot to verify the chosen behavior. Approving a pending reply should show it move to approved/queued, then completed (or an error if the model is offline). Rejecting a pending reply should permanently prevent that queued reply from running.

CI verifies isolated group policy persistence, safe owner decisions, denied foreign/write task decisions, default group compatibility, Codex and Coordinator regression, and headless Chromium clicks on simulated mobile and desktop layouts. Live ASUS linked Administrator queue and iPhone Safari still require verification before release.
