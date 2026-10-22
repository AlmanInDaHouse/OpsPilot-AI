"""Portable session-01 harness entrypoint; no product or infrastructure actions."""

import argparse
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FUTURE = {
    "install": "02: locked dependencies",
    "infra": "02: local PostgreSQL and IdP",
    "migrate": "02: reviewed Alembic migrations",
    "up": "02: platform services",
    "logs": "02: redacted service logs",
    "eval": "04: approved provider and golden dataset",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["doctor", "check", "test", *FUTURE])
    parser.add_argument("--report", type=Path, help="check only: JSON evidence file")
    args = parser.parse_args()
    if args.report and args.command != "check":
        parser.error("--report is supported only for check")
    if args.command == "doctor":
        print(json.dumps({
            "os": platform.platform(),
            "python": platform.python_version(),
            "tools": {name: shutil.which(name) for name in
                      ("git", "uv", "docker", "wsl", "node", "specify", "openspec")},
            "note": "Passive inventory; no daemon, network or infrastructure validation.",
        }, indent=2))
        return 0 if sys.version_info >= (3, 11) else 1
    if args.command in FUTURE:
        print(f"NOT_IMPLEMENTED: session {FUTURE[args.command]}. "
              "See docs/roadmap/SESSION_02_SPEC.md. No action performed.", file=sys.stderr)
        return 2
    if args.command == "check":
        cmd = [sys.executable, str(ROOT / "scripts/check_repository.py")]
        if args.report:
            cmd += ["--report", str(args.report)]
    else:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests/harness", "-v"]
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
