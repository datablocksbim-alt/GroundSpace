# GS-022 → GS-025: verified development scope and release gates

## GS-022 — Stability

- Repaired Windows path comparison to use `os.path.samefile`, preserving strict path identity while accepting equivalent NTFS 8.3/canonical spellings.
- GitHub CI on Windows and Linux runs the portable unit/behavior suites plus real headless Chromium click-through tests.
- The **entire** GS001–GS025 suite depends on an external `D:\000_AI Project\AI Agents Datablocks\orchestrator\task_queue.py` that does not exist on clean GitHub runners. The full integration gate MUST run on the ASUS using `tools/verify_gs022_local.ps1`; it has not been independently completed by this PR.
- No previous PRs should be merged solely on the basis of the portable subset.

## GS-023 — Supervised AI collaboration

In an existing group with **Qwen Coder**, **Codex**, **Granite**, and a registered project:
1. Enter the project objective in the chat composer and tap **Co-work**.
2. The real Qwen/Administrator queue receives a proposal task under its existing read/propose permission policy.
3. After Qwen completes, tap **Check & advance** to request an actual Codex workspace task. Codex retains the group's **Ask me / Approve for me / Off** policy; the workflow cannot bypass that policy or the operator's writable-mode opt-in.
4. Codex's pending job and approval controls are visible in the same group conversation. File changes only happen if the corresponding task is authorized.
5. After Codex completes, tap **Check & advance** to ask Granite to review its implementation **report**. Granite has no access to the actual project files; its feedback is not an independent security or code-quality audit.
6. Once Granite's proposal task completes, a final advance marks the workflow complete. Run history is durable across server restarts; one active workflow per group prevents accidental duplicates.

This is an intentionally **supervised sequential handoff pilot**, not unrestricted autonomous execution.

## GS-024 — Connect with ChatGPT (owner-only pilot)

- Uses the documented Codex app-server JSON-RPC **chatgptDeviceCode** flow, which is suitable for a remote iPhone where a desktop localhost browser callback would be unreliable.
- In Agents, tap **Continue with ChatGPT**. Ground Space displays the verified `https://auth.openai.com/codex/device` URL and one-time code, and never reads or renders the user's password, access token, API key, or `auth.json`.
- The connected account is owned by **the ASUS Codex CLI service user**. This is NOT user registration for Ground Space, an independent per-person session, or permission to use plan-backed APIs for any arbitrary service.
- Device-code flow requires explicit opt-in `GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED=1` and remains private-Tailscale-only. The CLI may already be logged in; `Check connection` reports authenticated provider and plan category only.
- GitHub CI uses mocked app-server JSON-RPC, not real ChatGPT authorization. The user's actual sign-in is a required hands-on release gate.
- OpenAI's official **Sign in with ChatGPT** SDK for open-source apps is distinct from this owner-only Codex app-server login. A genuine public multi-user ChatGPT sign-in requires verified per-user OAuth/OIDC, first-party sessions, credential vault, user consent for optional plan usage, and supported app registration/callbacks.

## GS-025 — Public-release protection (NOT public readiness)

- Refuses to launch with `GROUND_SPACE_DEPLOYMENT_MODE=public` or any public/multi-user enabling environment flags.
- Continues binding to loopback only, preserving exact Tailscale origin CSRF checks and no-store/clickjacking/security headers. Rate limits owner POST actions to reduce accidental floods. Bursts are *not* user-specific authorization or billing limits.
- Codex workspace-write and owner ChatGPT device login are blocked if a public configuration is attempted.
- Reports `security.public_ready=false`, `multi_user_accounts=false` and `per_user_os_sandbox=false` to the app. A future tenant authorization helper fails closed without a verified user identity.
- **Not yet implemented:** per-user account login, cryptographically verified per-user sessions, tenant-separated projects/approval ownership, Windows job isolation for untrusted code, secure token storage per user, billing limits, backup/restore, public security penetration testing, or a supported public/hosted sign-in plan. **Never enable Tailscale Funnel or expose this owner process on the public internet.**

## ASUS activation (after portable CI passes)

In PowerShell:
```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git status --short
git fetch origin
git switch feature/gs-025-security-boundaries
git pull --ff-only
.\tools\restart_gs016_codex.ps1
```

Stop if the working tree is not clean or the safety preflight detects an active Codex job. When ready for **owner-only** testing:

```powershell
.\tools\restart_gs016_codex.ps1 -Restart -EnableCodexWrite -EnableChatGPTConnect
```

Keep the existing `:8443` private Tailscale Serve route and the old dashboard unchanged. Confirm the running backend reports `backend_release: GS-025` through `/api/bootstrap`.

Then run the entire ASUS-local Administrator+Ground Space test suite:

```powershell
.\tools\verify_gs022_local.ps1
```

On the iPhone: Chat → Group → Co-work; Agents → Connect ChatGPT → one-time device code. Test Qwen proposal/approval, Codex create/edit/run in **Codex Test**, and Granite review. The new connection may consume Codex plan allowance or API credits.

## Release disposition

- **GS-022** portable code and CI gate, full external Administrator-local gate pending.
- **GS-023** working workflow implementation with mocked CI and browser tests; ASUS runtime verification pending.
- **GS-024** implemented owner device-login adapter; actual signed-in ASUS app-server verification pending. Genuine per-user sign-in pending.
- **GS-025** public-release protections implemented and tested; public hosting remains deliberately **blocked** until multi-user auth and hard OS isolation are delivered.

All changes remain on stacked feature branches. Do not silently merge into main or publicize the owner Tailscale endpoint.
