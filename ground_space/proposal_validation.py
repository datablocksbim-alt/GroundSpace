"""Explicit, offline QW-002 candidate evaluation; NEVER execute code on host.

Owner-invoked CLI only; no chat endpoint, no automatic assignment or write access.
Docker is defense in depth, not an adequate isolation boundary for hostile
public-user scripts. A hardened, disposable VM is required before public use.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

IMAGE = "python:3.11-alpine"  # Must already exist locally. Never pull on demand.
MAX_SOURCE_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 12000
TIMEOUT_SECONDS = 30
CONTRACT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "gs011_scheduler_contract.py"


def result(status: str, reason: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **details}


def validate_proposal(source_path: Path, *, image: str = IMAGE) -> dict[str, Any]:
    """Evaluate a proposed QW-002 Python file, failing closed without Docker.

    The trusted test contract is bundled with Ground Space. No arbitrary test
    path is accepted and candidate modules are NEVER imported by this process.
    """
    source_path = Path(source_path)
    try:
        if not source_path.is_file() or source_path.stat().st_size > MAX_SOURCE_BYTES:
            return result("blocked", "Source must be a readable Python file <= 64 KiB")
        content = source_path.read_bytes()
        if len(content) > MAX_SOURCE_BYTES:
            return result("blocked", "Source exceeds 64 KiB")
        source = content.decode("utf-8")
        tree = ast.parse(source, filename="schedule_tasks.py")  # Parse only, never run.
        if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == "schedule_tasks" for node in tree.body):
            return result("failed", "No top-level schedule_tasks function found")
    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        return result("failed", f"Could not parse proposal: {type(exc).__name__}: {exc}")

    docker = shutil.which("docker")
    if docker is None:
        return result("blocked", "Docker not installed. Untrusted code was NOT executed")
    try:
        check = subprocess.run([docker, "image", "inspect", image], capture_output=True,
                               text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return result("blocked", f"Local Docker unavailable: {type(exc).__name__}")
    if check.returncode != 0:
        return result("blocked", f"Docker image {image} is not cached locally; no pull attempted")

    with tempfile.TemporaryDirectory(prefix="groundspace-qw002-") as scratch:
        work = Path(scratch)
        # The temporary bind mount contains ONLY proposal code and trusted tests.
        (work / "schedule_tasks.py").write_bytes(content)
        (work / "test_benchmark.py").write_bytes(CONTRACT.read_bytes())
        if os.name != "nt":
            # Docker container UID 65534 must be able to traverse this temp directory.
            work.chmod(0o755)
            (work / "schedule_tasks.py").chmod(0o644)
            (work / "test_benchmark.py").chmod(0o644)
        container_name = "gs-qw002-" + secrets.token_hex(8)
        command = [
            docker, "run", "--name", container_name, "--rm", "--pull", "never",
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "64",
            "--memory", "256m", "--cpus", "1", "--user", "65534:65534",
            "--tmpfs", "/tmp:rw,nosuid,noexec,size=16m",
            "--mount", f"type=bind,source={work.resolve()},target=/work,readonly",
            "--workdir", "/work", image,
            "python", "-I", "-B", "-m", "unittest", "discover", "-s", "/work",
            "-p", "test_benchmark.py", "-v",
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       timeout=TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            # Killing the Docker client does not necessarily stop its container.
            try:
                subprocess.run([docker, "rm", "-f", container_name],
                               capture_output=True, text=True, timeout=5, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
            return result("blocked", "Container exceeded time limit; forced cleanup attempted")
        except OSError as exc:
            return result("blocked", f"Container could not start: {type(exc).__name__}")
        output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-MAX_OUTPUT_CHARS:]
        # Require a real successful test invocation and a zero container exit code.
        passed = completed.returncode == 0 and "Ran 9 tests" in output and "\nOK" in output
        return result("passed" if passed else "failed",
                      "QW-002 contract passed in container" if passed
                      else "QW-002 contract did not pass; see test output",
                      exit_code=completed.returncode, output=output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate QW-002 code without host execution")
    parser.add_argument("source", type=Path, help="Path to an owner-supplied schedule_tasks.py")
    args = parser.parse_args(argv)
    report = validate_proposal(args.source)
    print(json.dumps(report, indent=2))
    return {"passed": 0, "failed": 1, "blocked": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
