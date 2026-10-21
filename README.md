# Data Blocks Ground Space

Ground Space is the communication layer for the existing Data Blocks Administrator and local agents. GS-001 reuses the Administrator's persistent queue and adds structured task messages plus a deterministic read-only Python worker.

See [docs/GS-001.md](docs/GS-001.md) for architecture, safety boundaries, and validation commands.

GS-002 adds explicitly approved, proposal-only live inference through local Ollama and `qwen2.5-coder:3b`. See [docs/GS-002.md](docs/GS-002.md).

GS-003 provides the first local browser chat, agent registry, and task dashboard. Start it with `tools\start_ground_space.ps1`; see [docs/GS-003.md](docs/GS-003.md).

GS-003 local chat now auto-dispatches permitted read-only/proposal tasks with no owner-token approval popup. Other callers of the Administrator bridge still default to pending approval.

GS-004 adds full-response copying, a persisted multi-model Ollama registry (add/remove installed models through Agents), per-message Fast/Balanced/Detailed generation settings, and measured response speed when available. ChatGPT and Claude remain clearly labeled as unconnected future providers. See [docs/GS-004.md](docs/GS-004.md).

GS-006 softens chat bubbles and adds periwinkle `/goal` and `/milestone` planning annotations with a slash suggestion menu. These are conversation notes, not executable Administrator tasks. See [docs/GS-006.md](docs/GS-006.md).

GS-007 adds private group chats with up to six registered local AI models, per-model sequential responses, and local project-folder selection through restricted roots. Folder association is metadata-only; AI file access is not enabled. See [docs/GS-007.md](docs/GS-007.md).
