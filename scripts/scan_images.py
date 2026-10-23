"""Image CVE gate with a digest-pinned scanner, no host socket inside containers."""

import argparse
import hashlib
import json
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCANNER = "ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c"
LOCAL = ROOT / "artifacts/local/image-scans"
EVIDENCE = ROOT / "artifacts/session-02"


def summarize(raw: Path, code: int, image: str) -> dict:
    result = {
        "image": image,
        "scanner": SCANNER,
        "exit_code": code,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "vulnerabilities": [],
    }
    if not raw.exists():
        return {**result, "verdict": "BLOCKED", "reason": "Scanner did not produce a report"}
    report = json.loads(raw.read_text(encoding="utf-8"))
    result["raw_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
    result["raw_report"] = raw.resolve().relative_to(ROOT).as_posix()
    result["image_id"] = report.get("Metadata", {}).get("ImageID")
    for target in report.get("Results", []):
        for finding in target.get("Vulnerabilities", []):
            result["vulnerabilities"].append(
                {
                    key: finding.get(key)
                    for key in (
                        "VulnerabilityID",
                        "PkgName",
                        "InstalledVersion",
                        "FixedVersion",
                        "Severity",
                        "PrimaryURL",
                        "Status",
                    )
                }
            )
    if code not in {0, 1}:
        result["verdict"] = "BLOCKED"
    elif result["vulnerabilities"]:
        result["verdict"] = "FAIL"
    else:
        result["verdict"] = "PASS" if code == 0 else "BLOCKED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        nargs="+",
        choices=["postgres", "keycloak", "api"],
        default=["postgres", "keycloak", "api"],
    )
    args = parser.parse_args()
    print("IMAGE SCAN SCOPE: " + ",".join(args.only), flush=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    cache = ROOT / "artifacts/local/trivy-cache"
    cache.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results = []
    for name, image in (
        ("postgres", "opspilot-postgres:18.6-s02"),
        (
            "keycloak",
            "quay.io/keycloak/keycloak:26.8.1@sha256:79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244",
        ),
        ("api", "opspilot-ai:0.2.0"),
    ):
        if name not in args.only:
            continue
        raw = LOCAL / f"{name}-{uuid4().hex[:12]}.raw.json"
        archive = LOCAL / f"{name}.tar"
        source_id = json.loads(
            subprocess.run(
                ["docker", "image", "inspect", image], check=True, capture_output=True, text=True
            ).stdout
        )[0]["Id"]
        subprocess.run(["docker", "image", "save", "--output", str(archive), image], check=True)
        with tarfile.open(archive) as saved:
            manifest = json.load(saved.extractfile("manifest.json"))
            config_name = Path(manifest[0]["Config"]).name.removesuffix(".json")
            config_id = "sha256:" + config_name
        container_name = f"opspilot-s02-scan-{name}-{uuid4().hex[:8]}"
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--user",
            "10001:10001",
            "--cpus",
            "1",
            "--memory",
            "768m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=bind,source={LOCAL},target=/scan",
            "--mount",
            f"type=bind,source={cache},target=/cache",
            SCANNER,
            "image",
            "--cache-dir",
            "/cache",
            "--no-progress",
            "--timeout",
            "20m",
            "--scanners",
            "vuln",
            "--severity",
            "HIGH,CRITICAL",
            "--exit-code",
            "1",
            "--format",
            "json",
            "--output",
            f"/scan/{raw.name}",
        ]
        command += ["--input", f"/scan/{name}.tar"]
        with (LOCAL / f"{name}.log").open("w", encoding="utf-8") as log:
            try:
                code = subprocess.run(
                    command, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=1500
                ).returncode
            except subprocess.TimeoutExpired:
                subprocess.run(["docker", "stop", container_name], check=False, capture_output=True)
                code = 124
        result = summarize(raw, code, image)
        result["docker_image_id"] = source_id
        result["archive_config_matches"] = config_id == result.get("image_id")
        if not result["archive_config_matches"]:
            result.update(
                verdict="BLOCKED", reason="Image archive/config mismatch or incomplete report"
            )
        (EVIDENCE / f"{name}-cves.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        results.append(result)
        detail = (
            "scan incomplete"
            if result["verdict"] == "BLOCKED"
            else f"{len(result['vulnerabilities'])} high/critical"
        )
        print(f"{name}: {result['verdict']} ({detail})", flush=True)
    return int(any(row["verdict"] != "PASS" for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
