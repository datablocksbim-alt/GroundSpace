# GS-031 Community Edition Foundation

## Baseline and protection

- Source snapshot `backup/gs030-pre-gs031-20261024` exists on the private
  remote and resolves to `bae6a37760b78878afdbbb7b71decc97fc44dc9d`.
- The production HTTP bootstrap reported `GS-030` before work began. The
  listener remained on `127.0.0.1:8765`; this work did not restart it.
- Untouched GS-030 baseline: 191 Python tests passed on Windows. Offline-model
  tests emit known late daemon-thread teardown traces after their temporary
  directories close; the suite exits successfully, but thread lifecycle remains
  a reliability item for a later work package.
- A fresh, consistency-checked private-state backup was created without a
  restart at
  `GroundSpace-Backups/GS-030-20261024-110334`. Its contents remain private and
  are not part of Git.

## Architecture and dependency change

Ground Space remains a local modular monolith:

```text
Browser on localhost
        |
GroundSpaceApp (HTTP, CSRF, owner policies)
        |
AdministratorAdapter -> ground_space.task_queue -> private/queue/*.json
        |                         |
OrchestratorAdapter          private/audit/*.jsonl
        |
isolated worker subprocess -> Ollama / deterministic worker

CodexPilot -> optional Codex CLI -> one registered project workspace
```

Through GS-030, `AdministratorAdapter` dynamically loaded
`D:\000_AI Project\AI Agents Datablocks\orchestrator\task_queue.py`. GS-031
owns the compatible implementation in `ground_space/task_queue.py`; no runtime
module imports or reads the external Administrator tree. The adapter retains
its first constructor argument temporarily so older callers do not break, but
the value is ignored and new application construction passes `None`.

The durable schema remains JSON schema version 1. Existing fields and unknown
extension fields are preserved. New submissions add an integer `priority`
defaulting to zero. Ordering is descending priority, then `created_at`, file
creation order and task ID for a deterministic FIFO tie-break. Existing records
without priority behave as priority zero and require no migration.

Claims use exclusive `.claims/<task-id>.claim` files. A task is claimable only
when its state is `queued` or `retry_pending` and approval is `approved`.
Retries retain the existing attempt budget, retry timestamp and failure audit.
On application startup, orphaned claimed/running tasks transition through the
same failure path to `retry_pending` or `failed`, preventing silent loss after a
crash. Terminal tasks remain idempotent in the Orchestrator.

HTTP APIs and UI architecture are unchanged in this work package. Existing
approval, group, task, Codex and chat endpoints keep their GS-030 contracts.

## Portable configuration

`ground_space.config` owns installation defaults:

- Windows state: `%LOCALAPPDATA%\DataBlocks\GroundSpace`
- Linux state: `$XDG_DATA_HOME/datablocks/ground-space`, falling back to
  `~/.local/share/datablocks/ground-space`
- Explicit state override: `GROUND_SPACE_STATE_DIR`
- Ollama endpoint: `GROUND_SPACE_OLLAMA_ENDPOINT`, defaulting to
  `http://127.0.0.1:11434`; credentials embedded in the URL are rejected.
- Optional `ollama` and `codex` programs are discovered from `PATH`.
- Project roots default to the user's home directory, explicit
  `GROUND_SPACE_ALLOWED_PROJECT_ROOTS`, and parents of already registered
  projects. The last rule preserves existing installations without granting
  agents filesystem tools.

The default HTTP listener remains hardcoded to loopback in `create_server`.
The source-development launcher now prefers a future bundled runtime under the
application directory, then discovers `python`/`py` from `PATH`; it contains no
ASUS runtime path.

Every state root contains its own private projects, groups, models,
conversations, approvals, queue, audit and Codex settings. Credentials are
never packaged or committed.

## Queue contract verification

`tests/test_gs031_standalone_queue.py` covers:

- real side-by-side contract execution against the installed legacy queue on
  the ASUS;
- reading an existing GS-030 record without migration;
- priority/FIFO selection;
- exclusive concurrent claims and duplicate ID rejection;
- pending/rejected approval enforcement;
- retries, lease timeout and startup crash recovery;
- an adapter started with a nonexistent Administrator root;
- portable paths, optional executable discovery and endpoint validation.

The GitHub workflow runs the complete Python suite on Windows and Ubuntu, plus
compile, JavaScript and source portability checks. This gives the replacement
a clean-machine gate that the external queue could not pass.

## Windows Community Edition packaging plan

Recommended next packaging slice:

1. Build a versioned virtual environment from a locked Python 3.11/3.12
   dependency manifest. Runtime code currently uses only the standard library.
2. Bundle the Python interpreter, `ground_space` package and `web/public`
   assets with PyInstaller in one-directory mode first. One-file mode should be
   considered only after startup and antivirus behaviour are measured.
3. Produce a per-user installer with WiX Toolset or Inno Setup. Install under
   `%LOCALAPPDATA%\Programs\Data Blocks Ground Space`; never request
   administrator rights for the normal path.
4. Create Start Menu/Desktop shortcuts for Start, Stop, Open, Backup and
   Uninstall. Use a single-instance lock and graceful local shutdown endpoint or
   tray process before enabling automatic startup.
5. On first run, show an onboarding check for Ollama service availability and
   installed models. Link to official Ollama installation instructions; do not
   silently install or download models.
6. Show Codex CLI as optional and disconnected until detected and explicitly
   registered. Never include its authentication directory or tokens.
7. Back up only the user's private Ground Space state with a manifest and
   restore validation. Models and registered project contents stay outside the
   backup.
8. Sign the installer and binaries, generate checksums/SBOM, test install,
   upgrade, uninstall-with-data-preserved, rollback and Windows SmartScreen
   behaviour on clean VMs before distribution.

Dependency inventory for the planned binary: CPython, Ground Space source and
static assets. Ollama and Codex CLI are optional external integrations detected
at runtime. Playwright and developer test tools are not runtime dependencies.

## Security and reliability findings

Implemented now:

- local-only binding and existing CSRF/rate limits remain unchanged;
- queue claims independently enforce approval status;
- duplicate task IDs cannot overwrite durable records;
- atomic task writes flush file data before replacement;
- worker leases are recovered automatically after restart;
- existing project registrations remain bounded while new installations use
  portable roots;
- no unrestricted Codex or Ollama filesystem authority was added.

Remaining risks and follow-up work:

- The queue is designed for one Ground Space server per state directory, not a
  distributed multi-host cluster. A Community installer needs a process-level
  single-instance lock.
- Graceful shutdown does not yet await every daemon conversation thread. Queue
  recovery protects durable task state, but child-process lifecycle should be
  made explicit before installer release.
- JSONL audit append is durable but not a database transaction with task-file
  replacement. Recovery/audit reconciliation should be added before multi-user
  support.
- Conversation, workspace, agent and Codex persistence use several local
  atomic-write helpers. They reject corruption, but a unified backup/restore
  service and fault-injection suite remain desirable.
- PyInstaller asset discovery, code signing, installer upgrade, antivirus and
  clean-VM validation are designs only; no installer is produced or published.

## Recommended completion sequence

1. Merge the standalone queue only after Windows and Ubuntu CI pass.
2. Add single-instance and graceful worker shutdown controls.
3. Consolidate portable configuration and backup/restore behind owner UI.
4. Build an unsigned internal PyInstaller artifact and validate clean Windows
   VM install/start/stop/upgrade/uninstall flows.
5. Add signed installer/release engineering only after those gates pass.

GS-031 is not approved for production activation by this document. The ASUS
GS-030 installation remains the working predecessor until a separate cutover.
