"""Portable OpsPilot harness: preserve S01 documentary checks, run S02 real gates."""

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUTURE = {
    "eval": "04: approved provider and golden dataset",
}


def run(commands):
    for command in commands:
        print("RUN " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "doctor",
            "check",
            "docs",
            "test",
            "install",
            "infra",
            "migrate",
            "up",
            "logs",
            "stop",
            *FUTURE,
        ],
    )
    parser.add_argument("--report", type=Path, help="check only: JSON evidence file")
    parser.add_argument(
        "--suite", choices=["all", "local", "integration", "harness"], default="all"
    )
    args = parser.parse_args()
    if args.report and args.command not in {"check", "docs"}:
        parser.error("--report is supported only for check/docs")
    if args.command == "doctor":
        print(
            json.dumps(
                {
                    "os": platform.platform(),
                    "python": platform.python_version(),
                    "tools": {
                        name: shutil.which(name)
                        for name in ("git", "uv", "docker", "wsl", "node", "specify", "openspec")
                    },
                    "note": "Passive inventory; no daemon, network or infrastructure validation.",
                },
                indent=2,
            )
        )
        return 0 if sys.version_info >= (3, 11) else 1
    if args.command in FUTURE:
        print(
            f"NOT_IMPLEMENTED: session {FUTURE[args.command]}. "
            "See docs/roadmap/SESSION_02_SPEC.md. No action performed.",
            file=sys.stderr,
        )
        return 2
    if args.command in {"check", "docs"}:
        cmd = [sys.executable, str(ROOT / "scripts/check_repository.py")]
        if args.report:
            cmd += ["--report", str(args.report)]
        commands = [cmd]
        if args.command == "check":
            commands += [
                ["uv", "lock", "--check"],
                ["uv", "run", "--frozen", "ruff", "format", "--check", "."],
                ["uv", "run", "--frozen", "ruff", "check", "."],
                [
                    "uv",
                    "run",
                    "--frozen",
                    "pymarkdown",
                    "--config",
                    ".pymarkdown.json",
                    "--strict-config",
                    "scan",
                    "-r",
                    "AGENTS.md",
                    "README.md",
                    "docs",
                    "specs",
                ],
                ["uv", "run", "--frozen", "mypy", "src"],
                ["uv", "run", "--frozen", "python", "scripts/check_architecture.py"],
                ["uv", "run", "--frozen", "bandit", "-r", "src", "-q"],
                ["uv", "run", "--frozen", "python", "scripts/check_secrets.py"],
                ["uv", "run", "--frozen", "pip-audit"],
            ]
        return run(commands)
    if args.command == "install":
        return run([["uv", "sync", "--frozen"]])
    if args.command == "test" and args.suite != "harness":
        command = ["uv", "run", "--frozen", "pytest"]
        if args.suite == "local":
            command += ["-m", "not integration"]
        elif args.suite == "integration":
            command += ["tests/integration"]
        print(
            f"TEST SCOPE: {args.suite}; only 'all' includes every required integration gate.",
            flush=True,
        )
        return run([command])
    if args.command == "test":
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests/harness", "-v"]
        return run([cmd])
    if args.command == "logs":
        return run(
            [["docker", "compose", "-f", "infra/compose.yaml", "logs", "--tail", "100", "api"]]
        )
    lab = ["uv", "run", "--frozen", "python", "scripts/lab.py"]
    if args.command == "infra":
        return run(
            [
                [*lab, action]
                for action in ("init", "postgres", "bootstrap", "migrate", "identity", "provision")
            ]
        )
    return run([[*lab, args.command]])


if __name__ == "__main__":
    sys.exit(main())
