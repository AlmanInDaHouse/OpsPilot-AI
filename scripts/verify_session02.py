"""Execute reproducible local gates and record sanitized provenance, never credentials."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

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
            "opspilot-keycloak:26.8.1-s02",
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


def current_revision() -> dict:
    spec = importlib.util.spec_from_file_location(
        "scan_provenance", ROOT / "scripts/scan_images.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.provenance()


def write_manifest() -> None:
    files = [
        {
            "path": path.relative_to(EVIDENCE).as_posix(),
            "hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in sorted(EVIDENCE.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]
    json_file(
        "manifest.json",
        {
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **current_revision(),
            "scope": "Actual executable/configuration inputs; HEAD alone does not identify uncommitted edits",
            "session_03": "NO-GO",
            "files": files,
        },
    )


def verification_summary(
    runs: list, images: dict, image_results: dict, revision: dict | None = None
) -> dict:
    """Report local checks without granting acceptance to unverified global gates."""
    required_images = {"postgres", "keycloak", "api"}
    revision = current_revision() if revision is None else revision
    passed = (
        bool(runs)
        and all(row["exit_code"] == 0 for row in runs)
        and set(images) == set(image_results) == required_images
        and all(
            row["verdict"] == "PASS"
            and row["exit_code"] == 0
            and row.get("archive_config_matches") is True
            and row.get("docker_image_id") == images[name]["id"]
            and row.get("report_valid") is True
            and row.get("archive_source_matches") is True
            and row.get("image_id") == row.get("archive_config_id")
            and row.get("head") == revision["head"]
            and row.get("input_sha256") == revision["input_sha256"]
            for name, row in image_results.items()
        )
    )
    return {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        **revision,
        "state": "COMPLETE",
        "runs": runs,
        "image_gates": {
            name: {
                "verdict": value["verdict"],
                "exit_code": value["exit_code"],
                "image_id_matches": value.get("docker_image_id") == images.get(name, {}).get("id"),
                "archive_config_matches": value.get("archive_config_matches"),
            }
            for name, value in image_results.items()
        },
        "local_gates": "PASS" if passed else "FAIL",
        "session_03": "NO-GO",
        "acceptance_limit": (
            "Local checks do not approve S03: matching recovery/fresh-PG evidence "
            "and successful remote CI of the final revision are required."
        ),
        "remote_ci": "NOT_RUN",
    }


def main() -> int:
    global EVIDENCE, LOCAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    run_id = uuid4().hex
    EVIDENCE = args.evidence_dir or EVIDENCE / "scanner-remediation" / ("verification-" + run_id)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.manifest_only:
        write_manifest()
        return 0  # Integrity inventory only; never an acceptance gate.
    LOCAL = LOCAL / run_id
    LOCAL.mkdir(parents=True, exist_ok=True)
    commands = [
        ("frozen", ["uv", "sync", "--frozen"]),
        (
            "docs",
            [
                sys.executable,
                "scripts/check_repository.py",
                "--report",
                str(EVIDENCE / "docs-final.json"),
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
                "--cov-report=json:" + str(EVIDENCE / "coverage-windows.json"),
                "--junitxml=" + str(EVIDENCE / "tests-windows.xml"),
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
                str(EVIDENCE / "bandit.json"),
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
                str(EVIDENCE / "pip-audit.json"),
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
    image_results = {}
    for name in ("postgres", "keycloak", "api"):
        try:
            image_results[name] = json.loads((EVIDENCE / "scans" / f"{name}-cves.json").read_text())
        except (OSError, ValueError):
            pass  # Missing or corrupt scans remain absent; summary fails closed.
    summary = verification_summary(runs, images, image_results)
    json_file("verification.json", summary)
    write_manifest()
    return 0 if summary["local_gates"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
