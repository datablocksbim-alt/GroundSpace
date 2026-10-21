# GS-010 — Coordinator-first local group chats (prototype)

**Status:** review branch based on GS-008; not merged or Windows-live verified.

## Behaviour

- In group chats an unaddressed message goes to **Coordinator**, identified by name, using the group's first registered local Ollama model as its language engine.
- `@Qwen`, `@qwen3.5:4b`, etc. route to matching installed group members; two mentions yield two separately attributed replies, processed sequentially. Unknown and unconnected providers (ChatGPT/Claude) are rejected, with no API fallback.
- `/goal <description>` creates three *proposed* structured local task cards (scope, implementation proposal, independent review). Coordinator discusses the goal but does not dispatch the cards by submitting the goal.
- `/milestone` remains a saved planning note discussed by Coordinator. It does not create a worker assignment.
- An **Approve read/propose** button explicitly submits one named task through the existing Administrator queue. Tasks with dependencies cannot start until predecessors complete. Clicking approval only enables *tool-free written proposals*, never project-file reads/writes or shell execution.
- Task cards and their approval state survive application restarts in private `coordinator_proposals.json`. Existing group/project metadata and conversations remain unchanged.

## Important limitations

- This is a safe first-stage Python Coordinator, **not** autonomous repository/file work. Structured card titles are initial fixed planning stages; the local model adds its own goal-specific explanation in chat. More sophisticated task decomposition and separate reviewer enforcement are future work.
- The Coordinator is powered by the group's first registered Ollama model; it is not a new locally downloaded LLM. An offline model cannot generate a reply.
- ChatGPT/Claude providers remain disconnected and paid API spending stays at AUD $0.
- Approval is scoped to the local Ground Space server session (localhost and existing CSRF checks); access from another device requires the existing private network setup, not a public listener.
- Do not merge GS-008 or GS-010 until Windows and live Ollama tests pass.

## QA

### GitHub CI (OS-independent smoke)
`python -m compileall -q ground_space tests`
`python -m unittest -v tests.test_gs010_coordinator tests.test_gs008_planning tests.test_gs007_ui`
`node --check web/public/app.js`

### ASUS laptop (required before release)

```powershell
cd "D:\000_AI Project\002 Datablocks Ground Space"
git fetch origin
git switch feature/gs-010-coordinator-routing
py -3 -m unittest discover -s tests -v
.\tools\start_ground_space.ps1
```

Create a group with Qwen models and select your local Pyrene project. Test an ordinary message (Coordinator answers), `@Qwen` (specialist answers), `/goal Finish the Codex tablet` (three pending task cards), and approve the first card (only a proposal should run). Check that duplicate approval is rejected and third-task approval is blocked until dependencies finish. Confirm no project files are modified, and that turning Ollama off shows a failed/unavailable response rather than pretending completion. Switch back to `main` when finished; this branch is unreleased.
