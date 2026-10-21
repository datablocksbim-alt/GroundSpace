# Data Blocks Ground Space

Ground Space is the communication layer for the existing Data Blocks Administrator and local agents. GS-001 reuses the Administrator's persistent queue and adds structured task messages plus a deterministic read-only Python worker.

See [docs/GS-001.md](docs/GS-001.md) for architecture, safety boundaries, and validation commands.
