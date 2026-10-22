# GS-012 — Ground Space private iPhone access with Tailscale Serve

**Development pilot only.** This adds no public exposure, no cloud AI connection, and no Pyrene or Codex write permission.

## Why Ground Space needs a server change

Ground Space already binds to `127.0.0.1:8765`; this is the correct private boundary. Its POST requests also check an exact `Origin` plus an existing CSRF cookie/header pair. Without GS-012, the iPhone could load the page through a Tailscale HTTPS proxy, but most chat actions would fail with HTTP 403. Never disable CSRF to make remote access work.

GS-012 allows **one explicitly configured Tailscale HTTPS origin** while preserving localhost and all existing CSRF checks. There is no trust in arbitrary Host or X-Forwarded headers, and no wildcard provider host. Accepted origins are `https://device.tailnet.ts.net` and `https://device.tailnet.ts.net:8443` (no trailing slash). Invalid configuration fails startup instead of weakening security.

## First, inspect existing ASUS connections

In PowerShell on ASUS, with Tailscale installed and logged into the same tailnet as your iPhone:

```powershell
tailscale status
tailscale serve status
Test-NetConnection -ComputerName 127.0.0.1 -Port 8765
```

**Do not overwrite an existing Serve port 443 route** used by the Data Blocks dashboard. GS-012 uses port **8443** on the same device to avoid changing the existing dashboard. If 8443 is already in use, stop and choose a separate deployment arrangement; do not override it.

## Start Ground Space with the exact tailnet hostname

From the Ground Space checkout on branch `feature/gs-012-mobile-tailnet-access`, substitute the **real HTTPS host shown by Tailscale** (the sample host below will not work).

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
$env:GROUND_SPACE_TAILSCALE_ORIGIN = "https://YOUR-ASUS.YOUR-TAILNET.ts.net:8443"
.\tools\start_ground_space.ps1
```

The environment variable must be set before launching the server; restart Ground Space after changing it. Ground Space continues to listen on `127.0.0.1:8765`, not on a public interface.

In a separate PowerShell window (do not close Ground Space), start the private Tailscale reverse proxy:

```powershell
tailscale serve --bg --https=8443 8765
tailscale serve status
```

If Tailscale asks to enable HTTPS for your tailnet, follow its sign-in and certificate setup. Do not use `tailscale funnel`: Funnel exposes services to the public internet.

## iPhone verification

1. Confirm that iPhone and ASUS are connected to the same Tailscale tailnet.
2. In iPhone Safari, visit the configured `https://YOUR-ASUS.YOUR-TAILNET.ts.net:8443`.
3. Open Ground Space Chat and submit `/goal Confirm mobile chat access`. It should appear as a planning note, not dispatch any coding agent.
4. Refresh the page and confirm the note persists.
5. Switch Tailscale off on the iPhone and confirm this *private* URL no longer opens.
6. Confirm the existing Data Blocks dashboard still works independently.

To remove **only this separate Ground Space Serve route** (rather than resetting every other Serve application), use:

```powershell
tailscale serve --https=8443 off
```

## Security and acceptance boundaries

- The HTTPS link is restricted to devices/users authorized in the tailnet. Review Tailscale ACLs before sharing the URL. Ground Space does **not** yet provide per-user accounts or independent login; this pilot is not suitable for public accounts or untrusted tailnet members.
- The local HTTP port remains bound to loopback. Do not expose port 8765 via Windows firewall rules or a public router.
- The strict Origin allowlist and the CSRF cookie/header check remain in place. Unconfigured remote Origin requests get HTTP 403.
- This is **browser access**, not desktop mirroring and not an authorization for AI workers to modify project files.
- No Codex worker pilot, provider billing, online fallback, or Pyrene changes are enabled in GS-012.

Run the local unit suite before approving deployment:

```powershell
& "D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe" -m unittest discover -v
```

Relevant Tailscale docs: https://tailscale.com/docs/reference/tailscale-cli/serve and https://tailscale.com/docs/reference/examples/serve
