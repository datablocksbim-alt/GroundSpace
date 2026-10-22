# GS-020 Design — Continue with ChatGPT for Ground Space

**Status:** Product design, not an implemented login. Do not display a working Connect button until there is a verified OAuth client, callback, and user session.

## Product requirement

Users should be able to open **Agents → Add AI → ChatGPT / Codex → Continue with ChatGPT**, authenticate with OpenAI in a browser, explicitly consent to optional ChatGPT-plan usage, and return to Ground Space with a connection card identifying the connected account and its permissions. No password, copied browser cookie, API key, or Codex auth.json file is entered in Ground Space.

Official integration references:
- [Sign in with ChatGPT quickstart](https://developers.openai.com/siwc/quickstart)
- [Open-source app implementation cookbook](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt)
- [Codex app-server integration guide](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
- [Codex app-server overview](https://learn.chatgpt.com/docs/app-server)

## Required separation of permissions

1. **Ground Space sign-in** — verify OpenAI-issued identity with OIDC, PKCE, nonce, issuer, audience, signature and stable subject; create a local Ground Space account and a separate first-party session. Do not use email string alone as identity.
2. **ChatGPT plan use** — request the optional permission separately. Signed-in does not imply plan usage; clearly display whether the plan-usage scope was granted and handle ineligible accounts.
3. **Codex agent registration** — allow authenticated user to add Codex as an agent in specific groups, using that user's own connected account.
4. **Workspace write permissions** — separately choose a registered local project; default to Ask me; enforce scope at the server, OS sandbox and task queue, not merely in prompts. Even with Approve for me, keep irreversible deletion and dangerous actions gated by an explicit, attributable owner policy.

## Implementation for public multi-user Ground Space

Ground Space is currently a single-owner Python HTTP server. It does **not** have account sessions or tenant isolation. Do not expose owner Codex auth or the current writable CLI endpoint to public users. Implement the following *before* offering ChatGPT sign-in:

- Introduce account/session lifecycle with authenticated user ID, CSRF protection, secure HttpOnly session cookies, origin and redirect-URI allowlists, session expiration and logout.
- Use the official Sign in with ChatGPT open-source SDK/devkit where supported. Keep the OIDC/OAuth flow and tokens in a trusted server/native process, not frontend JavaScript or stored conversation records.
- Register a client per app installation following the official host ID/client ID requirements. Authenticate via OpenAI's authorization endpoint with state, nonce and PKCE. Verify ID tokens before provisioning a user. Store scoped credentials in the OS credential store or an encrypted vault with per-account isolation. Never serialize tokens into /api/bootstrap, browser logs, Git or agent task payloads.
- On an iPhone connecting through Tailscale to an ASUS server, the browser's localhost is the *phone*, not the ASUS. Avoid a redirect back to `localhost` that only works on desktop. Use an approved callback/redirect strategy or properly verified device authorization flow; validate security against the official SDK and registered redirect URIs.
- If ChatGPT-plan usage is granted, use the documented token-sharing/app-server or Responses integration. Do **not** scrape consumer ChatGPT browser sessions or copy CLI credential files across users. Refresh or revoke tokens through documented methods.
- Create explicit Connect, Connected, Manage usage, Switch account and Disconnect states. If the user disconnects or switches accounts, stop/deny their in-flight work as appropriate and revoke credentials according to the actual provider semantics.
- Associate every project, group membership, Codex task, approval, process, and audit event with the authenticated Ground Space user. Require a strong sandbox isolation boundary per user; a raw workspace-write CLI process running as the Ground Space desktop owner is not safe for public multi-user file modification.
- Integrate usage status and limits; do not promise unlimited free access. Codex requests may consume ChatGPT plan allowance or billable credits, depending on account and connected scopes.

## Test gates

1. Browser login and successful callback on **the actual iPhone-to-ASUS private route**, plus the desktop browser.
2. Cross-account isolation: user A cannot see or execute user B projects, tokens, agent tasks, or approvals.
3. Denial and cancellation: declining plan usage does not silently authorize model calls; disconnect invalidates sessions.
4. OAuth state/nonce/PKCE/redirect validation, CSRF and session rotation tests.
5. Retry after expiry/refresh and failed network/sandbox test; errors must not expose secrets.
6. Disposable-project Codex create/edit/run/delete tests, plus explicit owner approval and data recovery/rollback.

## Immediate private-owner workaround

For the existing single-owner pilot, signing into the official Codex CLI with `codex login` is supported and already stores credentials locally; Ground Space should merely check `codex login status` and use the installed CLI. Fixing the subprocess command and surfacing safe diagnostics is GS-019. The longer-term user-facing `Continue with ChatGPT` feature is GS-020, a separate milestone.

**DO NOT ship a cosmetic sign-in button that impersonates OpenAI or appears connected without completing real authorization.**
