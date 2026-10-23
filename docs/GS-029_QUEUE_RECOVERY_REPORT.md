# GS-029 Qwen Approval and Queue Recovery

## Root cause

The two production records are legacy direct Qwen chat tasks created before the
task payload included a `model` field.  They correctly identify their execution
boundary with `requested_worker: qwen-proposal` and permissions `read,propose`.
The one-time recovery helper incorrectly required both that worker identity and
`payload.model: qwen2.5-coder:3b`, so it rejected both records with a misleading
message about an "unassigned" greeting.

Read-only inspection established that both task IDs belong to the same private
Qwen conversation and to no group or project:

| Task | Request | State | Worker | Conversation |
| --- | --- | --- | --- | --- |
| `GS-697b718134dc4cc3a8fcab18e7fc0703` | `hi qwen` | queued / pending | `qwen-proposal` | `a2bb0818-7a1e-426c-ae4b-4eb50845ae4b` |
| `GS-65cd541bd4b54cd99f855ff74c200f5c` | `are you there` | queued / pending | `qwen-proposal` | `a2bb0818-7a1e-426c-ae4b-4eb50845ae4b` |

Both have attempt count zero, no lease, exactly `read,propose`, and no
`group_id` or `project_id`.  Their task IDs are referenced by persisted user
entries whose agent is Qwen.  They did not originate in a multi-agent chat.

## Fix

- The recovery helper accepts the missing model only for the historic
  `qwen-proposal` worker, verifies the task against persisted conversation
  history, rejects group conversations, and validates any project association
  against the registered project list.
- Ground Space now has an authenticated, CSRF-protected owner decision route
  for direct proposal replies.  It is not a generic task approval endpoint.
  The backend verifies source, task state, original conversation entry,
  non-group origin, registered project, model-to-worker mapping, and exact
  proposal-only permissions before approval or rejection.
- Decisions use the existing Administrator queue and audit trail.  Approval is
  idempotent because only a queued/pending record can be decided; a second
  decision is rejected.  Approved work uses the existing serialized local-GPU
  dispatcher and result-to-conversation recorder.
- Tasks and direct Qwen messages expose compact owner approve/reject controls;
  mobile shows the controls beneath the shortened task title.
- The activation gate now distinguishes awaiting approval,
  approved-but-unprocessed, running/leased, retryable/stalled, rejected, and
  terminal work.  Rejected queued records are retained but are non-executable.

## Production state and safe owner action

The live GS-027 queue was only read during investigation and validation.  After
all release tests passed, the corrected helper applied the owner's explicit
authorization to the two exact task IDs.  Each completed once with attempt count
one.  A final snapshot reported zero executable tasks and zero active Codex
jobs; both registered projects and both groups remained present.

The recovery command used from the GS-029 preview checkout was:

```powershell
& 'D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe' `
  tools\approve_two_qwen_greetings.py --execute
```

It fails closed if the live release, queue population, record contents,
conversation origin, permissions, task state, or local model availability has
changed.  It processes the two tasks serially and stops before the second task
if the first does not complete.

## Verification

- Focused Python authorization and recovery tests: 20 passed.
- Authenticated HTTP decision test: CSRF denial, one approval, and duplicate
  approval denial passed.
- GS-029 cutover-state unit checks passed.
- Headless Chromium: mobile (390 x 844) and desktop owner controls passed.
- Production helper read-only precheck: both exact tasks verified.
- Full Python regression suite: 175 passed.
- Live recovery: 2 completed, 0 duplicated, 0 executable tasks remaining, and
  0 active Codex jobs.  Qwen answered both greetings through the existing
  proposal worker.

## Rollback

No production files are replaced by this patch.  Before a later GS-029
activation, run the existing verified state backup procedure in
`tools/activate_gs029_asus.ps1`.  If the future canary or production health
check fails, use that script's preserved GS-027 checkout and backup restoration
path.  Do not copy live queue files while the service is writing them, and do
not remove rejected or completed task records merely to satisfy the gate.
