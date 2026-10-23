"""Execute reproducible local gates and record sanitized provenance, never credentials."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/session-02"
LOCAL = ROOT / "artifacts/local/verification"


def json_file(name, value):
    (EVIDENCE / name).write_text(
        json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def metadata() -> dict:
    packages = []
    for package in sorted(
        importlib.metadata.distributions(), key=lambda item: item.metadata["Name"].lower()
    ):
        license_name = (
            package.metadata.get("License-Expression")
            or package.metadata.get("License")
            or "Not declared in wheel metadata"
        )
        packages.append(
            {
                "name": package.metadata["Name"],
                "version": package.version,
                "license_metadata": license_name.splitlines()[0][:200],
            }
        )
    docker = subprocess.run(
        ["docker", "info", "--format", "{{json .}}"], capture_output=True, check=True, text=True
    )
    info = json.loads(docker.stdout)
    images = {}
    for name, image in (
        ("postgres", "opspilot-postgres:18.6-s02"),
        ("api", "opspilot-ai:0.2.0"),
        (
            "keycloak",
            "quay.io/keycloak/keycloak:26.8.1@sha256:79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244",
        ),
    ):
        data = json.loads(
            subprocess.run(
                ["docker", "image", "inspect", image], capture_output=True, check=True, text=True
            ).stdout
        )[0]
        images[name] = {
            "reference": image,
            "id": data["Id"],
            "user": data["Config"]["User"],
            "os": data["Os"],
            "architecture": data["Architecture"],
        }
    json_file(
        "environment.json",
        {
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "session_date_madrid": "2026-10-23",
            "os": platform.platform(),
            "python": platform.python_version(),
            "repository": str(ROOT),
            "head": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
            ).stdout.strip(),
            "docker": {
                key: info.get(key)
                for key in (
                    "ServerVersion",
                    "OperatingSystem",
                    "KernelVersion",
                    "NCPU",
                    "MemTotal",
                    "OSType",
                    "Architecture",
                )
            },
            "images": images,
            "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
            "packages": packages,
            "license_limit": "Package metadata only; not a legal license/compliance review",
        },
    )
    workflows = {}
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        assert data["permissions"] == {"contents": "read"}
        for job in data["jobs"].values():
            for step in job["steps"]:
                if "uses" in step:
                    revision = step["uses"].split("@")[-1]
                    assert len(revision) == 40 and all(ch in "0123456789abcdef" for ch in revision)
        workflows[path.name] = {
            "jobs": list(data["jobs"]),
            "yaml_parsed": True,
            "actions_pinned": True,
            "remote_execution": "NOT_RUN",
        }
    json_file("ci-structure.json", workflows)
    return images


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    commands = [
        ("frozen", ["uv", "sync", "--frozen"]),
        (
            "docs",
            [
                sys.executable,
                "scripts/check_repository.py",
                "--report",
                "artifacts/session-02/docs-final.json",
            ],
        ),
        ("format", ["uv", "run", "--frozen", "ruff", "format", "--check", "."]),
        ("lint", ["uv", "run", "--frozen", "ruff", "check", "."]),
        (
            "markdown",
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
        ),
        ("types", ["uv", "run", "--frozen", "mypy", "src"]),
        ("architecture", ["uv", "run", "--frozen", "python", "scripts/check_architecture.py"]),
        (
            "tests",
            [
                "uv",
                "run",
                "--frozen",
                "pytest",
                "--cov=opspilot",
                "--cov-report=json:artifacts/session-02/coverage-windows.json",
                "--junitxml=artifacts/session-02/tests-windows.xml",
                "-q",
                "--tb=short",
            ],
        ),
        (
            "bandit",
            [
                "uv",
                "run",
                "--frozen",
                "bandit",
                "-r",
                "src",
                "-f",
                "json",
                "-o",
                "artifacts/session-02/bandit.json",
            ],
        ),
        (
            "dependencies",
            [
                "uv",
                "run",
                "--frozen",
                "pip-audit",
                "--format",
                "json",
                "--output",
                "artifacts/session-02/pip-audit.json",
            ],
        ),
        ("secrets", ["uv", "run", "--frozen", "python", "scripts/check_secrets.py"]),
        ("compose", ["docker", "compose", "-f", "infra/compose.yaml", "config", "--quiet"]),
        ("diff", ["git", "diff", "--check"]),
    ]
    runs = []
    for name, command in commands:
        started, before = datetime.now(UTC).isoformat(), time.monotonic()
        log = LOCAL / f"{name}.log"
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(
                command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False
            )
        row = {
            "gate": name,
            "command": command,
            "started_at_utc": started,
            "duration_seconds": round(time.monotonic() - before, 2),
            "exit_code": result.returncode,
            "verdict": "PASS" if result.returncode == 0 else "FAIL",
            "raw_log": log.relative_to(ROOT).as_posix(),
            "raw_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }
        runs.append(row)
        print(f"{name}: {row['verdict']}", flush=True)
        json_file("verification.json", {"state": "RUNNING", "runs": runs, "session_03": "NO-GO"})
    images = metadata()
    image_results = {
        name: json.loads((EVIDENCE / f"{name}-cves.json").read_text())
        for name in ("postgres", "keycloak", "api")
    }
    passed = all(row["exit_code"] == 0 for row in runs) and all(
        row["verdict"] == "PASS" and row.get("docker_image_id") == images[name]["id"]
        for name, row in image_results.items()
    )
    json_file(
        "verification.json",
        {
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "state": "COMPLETE",
            "runs": runs,
            "image_gates": {
                name: {
                    "verdict": value["verdict"],
                    "exit_code": value["exit_code"],
                    "image_id_matches": value.get("docker_image_id") == images[name]["id"],
                }
                for name, value in image_results.items()
            },
            "session_03": "GO" if passed else "NO-GO",
            "remote_ci": "NOT_RUN",
        },
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
