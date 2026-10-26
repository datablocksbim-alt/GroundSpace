"""External AI provider discovery without reading or storing credentials."""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


PROVIDERS = (
    {"id": "anthropic", "label": "Claude", "direct_cli": "claude",
     "setup": "npm install -g @anthropic-ai/claude-code  then run: claude"},
    {"id": "google", "label": "Gemini", "direct_cli": "gemini",
     "setup": "npm install -g @google/gemini-cli  then run: gemini"},
    {"id": "xai", "label": "Grok", "direct_cli": "grok",
     "setup": "opencode auth login xai --method key"},
    {"id": "openrouter", "label": "OpenRouter", "direct_cli": None,
     "setup": "opencode auth login openrouter --method key"},
    {"id": "deepseek", "label": "DeepSeek", "direct_cli": None,
     "setup": "opencode auth login deepseek --method key"},
)

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _opencode_accounts(run: Any = subprocess.run) -> tuple[bool, str]:
    executable = shutil.which("opencode")
    if not executable:
        return False, ""
    try:
        completed = run(
            [executable, "auth", "list"], capture_output=True, text=True,
            timeout=8, shell=False, check=False, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return True, ""
    output = ANSI.sub("", (completed.stdout or "") + "\n" + (completed.stderr or ""))
    return True, output.casefold()


def provider_catalog(run: Any = subprocess.run) -> list[dict[str, Any]]:
    """Report capability state only; never return credential values or paths."""
    opencode_installed, accounts = _opencode_accounts(run)
    records = []
    for definition in PROVIDERS:
        direct = bool(definition["direct_cli"] and shutil.which(str(definition["direct_cli"])))
        via_opencode = opencode_installed and bool(re.search(
            r"(?<![a-z0-9])" + re.escape(str(definition["id"])) + r"(?![a-z0-9])", accounts
        ))
        # Installation is not authentication. Only OpenCode's account listing
        # is a stable, non-secret connected-state signal shared by these providers.
        connected = via_opencode
        records.append({
            "id": definition["id"], "label": definition["label"],
            "status": "connected" if connected else "login_required",
            "cli_installed": direct, "opencode_installed": opencode_installed,
            "connection": "opencode" if via_opencode else None,
            "setup_command": definition["setup"],
            "credentials_stored_by_ground_space": False,
            "full_write_option": connected,
            "execution_adapter": "qualification_required",
        })
    return records
