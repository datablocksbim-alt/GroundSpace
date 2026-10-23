"""Read-only Community Edition packaging readiness inventory.

This is intentionally diagnostic, not a deploy/release gate until --strict is used.
It must never inspect, print or upload the owner's private project/chat state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect_repository(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    specs = [
        (
            "standalone_queue",
            not (
                (root / "ground_space" / "legacy.py").exists()
                and "administrator_root.resolve()"
                in (root / "ground_space" / "legacy.py").read_text(encoding="utf-8")
            ),
            "Task queue must ship in the app; external Administrator path is not portable.",
        ),
        (
            "portable_launcher",
            (
                (root / "tools" / "start_ground_space.ps1").exists()
                and "D:\\000_AI Project" not in
                (root / "tools" / "start_ground_space.ps1").read_text(encoding="utf-8")
            ),
            "Launcher must run on a new Windows machine without a fixed Data Blocks path.",
        ),
        (
            "python_package",
            any((root / name).exists() for name in
                ("pyproject.toml", "setup.cfg", "setup.py")),
            "Publish package metadata and reproducible dependency installation.",
        ),
        (
            "public_license",
            any((root / name).exists() for name in
                ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")),
            "Owner must choose a license before public source distribution.",
        ),
        (
            "distribution_allowlist",
            (root / "distribution" / "ALLOWLIST.txt").is_file(),
            "Distribution must use an explicit source allowlist, not copy all old evidence.",
        ),
        (
            "public_mode_off",
            (
                (root / "ground_space" / "security.py").exists()
                and "assert_private_owner_mode"
                in (root / "ground_space" / "security.py").read_text(encoding="utf-8")
            ),
            "Community Edition must remain local-owner only by default.",
        ),
    ]
    return [
        {"check": name, "status": "ready" if ok else "blocked", "detail": detail}
        for name, ok, detail in specs
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true",
                        help="Nonzero exit while any public distribution blocker remains.")
    args = parser.parse_args()
    checks = inspect_repository(args.root)
    print(json.dumps({"readiness": checks,
                      "blockers": sum(x["status"] == "blocked" for x in checks)},
                     indent=2))
    return int(args.strict and any(x["status"] == "blocked" for x in checks))


if __name__ == "__main__":
    raise SystemExit(main())
