# GS-031 — Community Edition foundation (architecture decision 001)

**Status:** Development only. No production deploy, user data migration, public release, or main-branch merge has occurred.

## Product decision

Ground Space Community Edition is a **publicly downloadable, self-hosted app**, starting with Windows 10/11. Each installation owns its local data, private task queue and optional AI provider credentials. No shared hosted service, public tenant database or user accounts are required for this edition.

### Repository policy

- **Development repository:** `datablocksbim-alt/GroundSpace` for existing feature branches, ASUS pilot code, historical evidence and private integration experiments.
- **Distribution repository:** planned `datablocksbim-alt/GroundSpace-Community` to be **created privately first**, populated by an independently audited source-export allowlist, then deliberately made public after all release gates pass.
- Never automatically mirror all commit history, `evidence/`, `runtime_state/`, `logs/`, private state, credentials, proprietary/third-party tool binaries, model weights, or machine-specific paths to the distribution repository.
- No provider API tokens, Codex CLI auth state or local private chat data may ship with the installer. Authentication to Codex is owned by each user's installed CLI.
- The development GitHub repository was already publicly visible when this decision was made. A second repository is **not** a remedy for already published data; separately audit the existing history for secrets and sensitive material before changing visibility.
- GitHub connection currently provides no repository-creation operation; public repo creation and visibility require explicit owner action. **Do not publicize the new repo yet.**

## Source baseline and local data backup

- **GS-030 feature baseline:** `bae6a37760b78878afdbbb7b71decc97fc44dc9d` from draft PR #30.
- **Code preservation branch:** `backup/gs030-pre-gs031-20261024`, created directly at that SHA.
- **GS-031 branch:** `feature/gs031-community-foundation`, branched from the same snapshot.
- This GitHub branch preserves **repository source only**. It does **not** back up the owner's active ASUS production checkout or private state.
- The separate `tools/backup_gs031_current.ps1` performs **read-only health/queue checks** against the live instance, calls the established verified state-backup helper, validates the manifest and stored SHA-256 hashes, and prints the local destination. It doesn't restart the service, rewrite project folders, or publish data to Git.
- Current production release must be **discovered at runtime**; do not assume GS-030 is live just because its feature branch exists.
- The backup can be considered complete **only after the owner runs this script on the ASUS and sees its verified success output**. Keep a second encrypted copy on a separate drive for disaster recovery.

## Observed architectural blockers (from GS-030 read-only audit)

| Risk | Current implementation | GS-031 gate |
| --- | --- | --- |
| Hard-coded workstation dependency | `ground_space/legacy.py` loads `orchestrator/task_queue.py` from outside this repo | Package compatible queue implementation in Ground Space and test exact status/lease/retry semantics |
| Host-specific admin root | `ground_space/webapp.py` defaults `ADMIN_ROOT` to a D: Data Blocks path | User home/app-data defaults with optional explicit integration |
| Host-specific launch | `tools/start_ground_space.ps1` requires private Python executable path | Bundled launcher/installer; no developer prerequisites |
| Disconnected JSON transactions | Chats, projects, approvals, tasks, models and jobs stored separately | Transactional persistence/migration strategy and atomic task lifecycle |
| Unsafe state-loading fallback | Conversation parser can return empty on corrupt data | Never overwrite unreadable history; verified restore path |
| Shared host code execution | Codex subprocess inherits owner's user context | Explicit local owner guard, least-privilege write policy; no untrusted remote public execution |
| Full-state 2.5-second refresh | `web/public/app.js` polls `/api/bootstrap` | Incremental state endpoint and stable UI signals; preserve existing API during migration |
| Version drift | Running Python routes may differ from static UI assets | Versioned assets and runtime capability contract |
| Missing packaging/legal controls | No current app package metadata or explicit LICENSE identified | Choose copyright/license, SBOM, installer, checksums and release workflow |

## Implementation milestones

1. **GS-031.0 Safety baseline:** preserve source SHA; verified owner-local private backup; automated portability/readiness inventory; leave live production untouched.
2. **GS-031.1 Queue independence:** build an in-repository queue adapter with contract tests for claims, leases, retries, approvals and durability. Existing adapter remains default during parallel verification.
3. **GS-031.2 Config and bootstrap:** portable app paths, per-install local state and project roots; detect/install Ollama; optional user-managed Codex CLI; no baked-in owner identities.
4. **GS-031.3 Reliability:** corruption-safe read/write, migrations and crash tests, backup/restore tests, bounded scheduling.
5. **GS-031.4 Windows packaging:** reproducible signed/reproducibly hashed installer, one-click start/stop, loopback-only security, no admin privileges unless required by OS.
6. **GS-031.5 Public repository export:** license selection, explicit file allowlist and manual secrets/license audit; create private repo; first release candidate; then make public by owner approval.

All existing APIs, approvals, task identities and compact GS-030 UI behaviour are **compatibility requirements**. Each step needs a test-first migration plan. No automatic public hosting, Tailscale Funnel or multi-user server mode.

## Distribution quality gate

- Clean Windows VM install and uninstall tested (no Data Blocks folder and no extra Python installation).
- Ollama absent/offline path explained without crashes; user can add installed local models.
- User-chosen local project folders and no arbitrary default file-writing by models.
- Queue survives kill/restart, does not execute duplicates, and honors manual approvals.
- Chats/projects persist and survive interrupted saves and backup/restore.
- Local CSRF/origin and privileged action controls, dependency/secret/license scans and a private release candidate tested before publishing.
- Installer and archived binaries generated from tagged commits with checksums, no bundled credentials.
- No silent bridge between users' installations or exposure of localhost AI ports to the network.

## Release posture

**No new public repository has been created or made public.**
**No production ASUS backup or service change has been executed remotely.**
GS-031 can evolve independently of the live GS-029/GS-030 installation and Pyrene Mini.
