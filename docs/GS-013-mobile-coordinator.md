# GS-013 — Ground Space Coordinator + private iPhone access

**Pilot: owner-only, inside Tailscale. Not a public multi-user launch.**

This branch is built directly on the existing **GS-010 Coordinator chat** branch. It retains the current Ground Space interface, including its soft chat bubbles, `/goal` and `/milestone` notes, group routing, and project selector. Only the explicitly configured private HTTPS origin is added to CSRF validation; the server still binds to **127.0.0.1**.

## Verified before deployment

- ASUS local server `http://127.0.0.1:8765/` responded with HTTP 200 and returned the Ground Space UI.
- The ASUS checkout was on `feature/gs-010-coordinator-chat-routing`, remote `https://github.com/datablocksbim-alt/GroundSpace.git`, with a clean working tree at the owner's last screenshot.
- `tailscale serve status` showed existing owner-only `https://administrator.tailcd2042.ts.net` routes: `/` to port 8080 and `/dashboard` to port 8090.
- This branch proposes a **separate** `https://administrator.tailcd2042.ts.net:8443` for Ground Space only, routing to 127.0.0.1:8765. **It is not yet active or verified from Safari.**

## Step 1 — retrieve and test the integrated branch on ASUS

Run these commands in PowerShell (do not run them against the Pyrene folder):

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git status --short
git fetch origin
git switch feature/gs-013-coordinator-tailnet-mobile
git pull --ff-only
& "D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe" -m unittest tests.test_gs013_mobile_tailnet tests.test_gs010_coordinator tests.test_gs008_planning -v
```

Do not switch branches if `git status --short` shows unsaved local changes. GitHub CI is useful, but the Windows/live integration gate still matters.

## Step 2 — stop only the running Ground Space process and restart with the approved origin

The existing process listening on 8765 must be restarted to load the updated code and opt-in HTTPS origin. **In the terminal that is running Ground Space**, press Ctrl+C and wait for it to stop. Do not stop the Administrator, existing dashboard, or Tailscale.

In a new PowerShell window:

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
$env:GROUND_SPACE_TAILSCALE_ORIGIN = "https://administrator.tailcd2042.ts.net:8443"
.\tools\start_ground_space.ps1 -NoBrowser
```

Keep that window open, or use an independently managed startup task later. If the server raises a bind error, find the remaining process on port 8765 rather than killing unrelated apps.

## Step 3 — expose only Ground Space on dedicated Tailscale HTTPS port

In **another** PowerShell window, inspect existing routes first:

```powershell
tailscale serve status
```

If `8443` is already configured, **STOP**; do not overwrite any route. If unused:

```powershell
tailscale serve --bg --https=8443 8765
tailscale serve status
```

Do not run `tailscale serve reset`, `tailscale serve off` without a port, or `tailscale funnel`. Those commands could disrupt the existing dashboard or expose services publicly.

## Step 4 — test iPhone Safari

1. Connect iPhone and ASUS to the same owner tailnet.
2. On iPhone open **https://administrator.tailcd2042.ts.net:8443**. Confirm the **Ground Space** chat UI (not the older blue Data Blocks dashboard).
3. Send `/goal Verify private iPhone access` in **Administrator** chat. It must appear as a planning note without executing a development task. Refresh and confirm it persists.
4. Check the Coordinator group conversation and Tasks/Agents views. Chat execution remains proposal-only; do not assign development writes during the network pilot.
5. Open **https://administrator.tailcd2042.ts.net/dashboard** and confirm the existing dashboard still works.
6. Turn Tailscale **off** on the iPhone and confirm the port-8443 URL stops working. Turn it back on.

## Rollback

Remove **only** the Ground Space proxy:

```powershell
tailscale serve --https=8443 off
```

Stop the Ground Space process and restart the previous GS-010 branch if needed. Do **not** remove the other Tailscale routes or any existing Administrator/state files.

## Constraints

- The prototype is not ready for the public: no separate end-user account system or tenant isolation exists. Restrict tailnet access to trusted personal devices only.
- Local `127.0.0.1:8765` stays loopback-only. Explicit allowed HTTPS origin + CSRF cookie/header are both required for mutating requests; arbitrary Host/forwarded headers cannot grant trust.
- No Pyrene code or repo changes, no Codex worker, no paid APIs, no production task permissions.
- Before merging, run the **full Windows tests** (and investigate failures rather than overriding tests), then repeat Safari and desktop UI smoke tests.
- Source repos can be publicly visible without exposing the laptop's local service; public app hosting and multi-user auth are future, separate milestones.

Further reference: https://tailscale.com/docs/reference/examples/serve
