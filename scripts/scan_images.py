"""Fail-closed image gate: isolated non-root scanner and allowlisted diagnostics."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCANNER = "ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c"
LOCAL = ROOT / "artifacts/local/image-scans"
EVIDENCE = ROOT / "artifacts/session-02/scanner-remediation"
IMAGES = {
    "postgres": "opspilot-postgres:18.6-s02",
    "keycloak": "opspilot-keycloak:26.8.1-s02",
    "api": "opspilot-ai:0.2.0",
}
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
REASONS = {
    "PERMISSION_DENIED": "Scanner output or filesystem access denied",
    "CACHE_UNWRITABLE": "Scanner cache is not writable",
    "INPUT_UNREADABLE": "Image archive is not readable",
    "SCANNER_RUNTIME_ERROR": "Scanner or Docker runtime failed; inspect private log by hash",
    "SCAN_TIMEOUT": "Scanner exceeded its deadline",
    "INVALID_REPORT": "Scanner report missing, corrupt or incomplete",
    "VULNERABILITIES_FOUND": "HIGH/CRITICAL vulnerabilities found",
    "IMAGE_ID_MISMATCH": "Inspect, archive config and report image identity differ",
}
# Fixed script; only numeric facts and booleans leave the container.
PROBE = r"""
printf 'uid=%s\ngid=%s\n' "$(id -u)" "$(id -g)"
for pair in input:/input/image.tar output:/output cache:/cache; do
  key=${pair%%:*}; path=${pair#*:}
  printf '%s_stat=%s\n' "$key" "$(stat -c '%u:%g:%a' "$path")"
done
if head -c 1 /input/image.tar >/dev/null 2>&1; then echo input_readable=1; else echo input_readable=0; fi
if touch /output/.probe 2>/dev/null; then rm /output/.probe; echo output_writable=1; else echo output_writable=0; fi
if touch /cache/.probe 2>/dev/null; then rm /cache/.probe; echo cache_writable=1; else echo cache_writable=0; fi
if touch /input/image.tar 2>/dev/null; then echo input_readonly=0; else echo input_readonly=1; fi
if test ! -e /lab && test ! -e /run/secrets && test ! -e /scan && test ! -e /var/run/docker.sock; then echo lab_inaccessible=1; else echo lab_inaccessible=0; fi
"""


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def provenance() -> dict:
    """Bind evidence to HEAD and actual uncommitted executable/configuration inputs."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()
    filenames = (
        subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    digest = hashlib.sha256()
    for name in sorted(set(filter(None, filenames))):
        if name.startswith(
            ("scripts/", "src/", "tests/", "infra/", "contracts/", "migrations/", ".github/")
        ) or name in {"Dockerfile", "uv.lock", "pyproject.toml"}:
            digest.update(name.encode() + b"\0" + (ROOT / name).read_bytes() + b"\0")
    return {"head": head, "input_sha256": digest.hexdigest()}


def scanner_user() -> str:
    if os.name == "nt":
        return "10001:10001"  # Desktop mapping must pass actual I/O below.
    uid, gid = os.geteuid(), os.getegid()
    if uid == 0 or gid == 0:
        raise PermissionError("Scanner requires a non-root host UID and GID")
    return f"{uid}:{gid}"


def stage_paths(stage: Path, name: str) -> tuple[Path, Path, Path]:
    """All writable mounts are fresh staging children; no laboratory mounts."""
    if name not in IMAGES or stage.is_symlink():
        raise ValueError("Invalid scanner staging scope")
    stage = stage.resolve(strict=True)
    directory = stage / name
    directory.mkdir(mode=0o700)
    archive, output, cache = directory / "image.tar", directory / "output", stage / "cache"
    output.mkdir(mode=0o700)
    cache.mkdir(mode=0o700, exist_ok=True)
    (cache / "tmp").mkdir(mode=0o700, exist_ok=True)
    archive.touch(mode=0o600, exist_ok=False)
    return archive, output, cache


def container_command(archive: Path, output: Path, cache: Path, user: str, name: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--user",
        user,
        "--cpus",
        "1",
        "--memory",
        "768m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--env",
        "TMPDIR=/cache/tmp",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
        "--mount",
        f"type=bind,source={archive.resolve()},target=/input/image.tar,readonly",
        "--mount",
        f"type=bind,source={output.resolve()},target=/output",
        "--mount",
        f"type=bind,source={cache.resolve()},target=/cache",
    ]


def preflight(command: list[str], log=None) -> dict:
    result = subprocess.run(
        [*command, "--network", "none", "--entrypoint", "/bin/sh", SCANNER, "-c", PROBE],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if log is not None:
        log.write(result.stdout.decode(errors="replace"))
        log.write(result.stderr.decode(errors="replace"))
        log.flush()
    facts = {"exit_code": result.returncode}
    for line in result.stdout.decode(errors="replace").splitlines():
        key, _, value = line.partition("=")
        if key in {"uid", "gid"} and value.isdecimal():
            facts[key] = int(value)
        elif key in {"input_stat", "output_stat", "cache_stat"} and re.fullmatch(
            r"\d+:\d+:[0-7]{3,4}", value
        ):
            facts[key] = value
        elif key in {
            "input_readable",
            "output_writable",
            "cache_writable",
            "input_readonly",
            "lab_inaccessible",
        } and value in {"0", "1"}:
            facts[key] = value == "1"
    return facts


def preflight_failure(facts: dict, user: str) -> str | None:
    if facts.get("exit_code") != 0 or (facts.get("uid"), facts.get("gid")) != tuple(
        map(int, user.split(":"))
    ):
        return "SCANNER_RUNTIME_ERROR"
    if facts.get("input_readable") is not True:
        return "INPUT_UNREADABLE"
    if facts.get("output_writable") is not True:
        return "PERMISSION_DENIED"
    if facts.get("cache_writable") is not True:
        return "CACHE_UNWRITABLE"
    if facts.get("input_readonly") is not True or facts.get("lab_inaccessible") is not True:
        return "PERMISSION_DENIED"
    return None


def runtime_failure(code: int | None, log: str, timed_out: bool = False) -> str | None:
    text = log.lower()
    if timed_out or "context deadline exceeded" in text or "timeout exceeded" in text:
        return "SCAN_TIMEOUT"
    if "permission denied" in text or "read-only file system" in text:
        if "/cache" in text:
            return "CACHE_UNWRITABLE"
        if "/input/image.tar" in text:
            return "INPUT_UNREADABLE"
        return "PERMISSION_DENIED"
    return "SCANNER_RUNTIME_ERROR" if code not in {0, 1} or "fatal" in text else None


def summarize(
    raw: Path,
    code: int | None,
    image: str,
    *,
    failure: str | None = None,
    source_id: str | None = None,
    config_id: str | None = None,
    source_verified: bool = False,
) -> dict:
    result = {
        "image": image,
        "scanner": SCANNER,
        "exit_code": code,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "vulnerabilities": [],
        "report_exists": raw.is_file(),
        "report_valid": False,
        "archive_config_matches": False,
        "docker_image_id": source_id,
        "archive_config_id": config_id,
        "archive_source_matches": source_verified,
    }
    reason = failure
    try:
        result["raw_sha256"] = sha256(raw)
        report = json.loads(raw.read_text(encoding="utf-8"))
        if (
            not isinstance(report, dict)
            or report.get("SchemaVersion") != 2
            or report.get("ArtifactType") != "container_image"
        ):
            raise ValueError("Invalid image report envelope")
        identity = report.get("Metadata", {}).get("ImageID")
        if (
            not isinstance(identity, str)
            or not IMAGE_ID.fullmatch(identity)
            or not isinstance(report.get("Results"), list)
        ):
            raise ValueError("Incomplete image report")
        findings = []
        for target in report["Results"]:
            vulnerabilities = target.get("Vulnerabilities", [])
            if vulnerabilities is None:
                vulnerabilities = []
            if not isinstance(vulnerabilities, list):
                raise ValueError("Invalid findings")
            for item in vulnerabilities:
                if not isinstance(item, dict) or item.get("Severity") not in {"HIGH", "CRITICAL"}:
                    raise ValueError("Invalid severity")
                # No descriptions, URLs, paths or log excerpts in public diagnostics.
                finding = {}
                for key in (
                    "VulnerabilityID",
                    "PkgName",
                    "InstalledVersion",
                    "FixedVersion",
                    "Severity",
                    "Status",
                ):
                    value = item.get(key, "")
                    if not isinstance(value, str) or not re.fullmatch(
                        r"[A-Za-z0-9_.:+~@()<> =,/-]{0,200}", value
                    ):
                        raise ValueError("Unsafe finding field")
                    finding[key] = value
                if not finding["VulnerabilityID"] or not finding["PkgName"]:
                    raise ValueError("Incomplete finding")
                findings.append(finding)
        result.update(report_valid=True, image_id=identity, vulnerabilities=findings)
        matches = (
            config_id == identity
            and source_id is not None
            and (source_id == config_id or source_verified)
        )
        result["archive_config_matches"] = matches
        reason = reason or runtime_failure(code, "")
        if not matches:
            reason = reason or "IMAGE_ID_MISMATCH"
        if not reason and findings:
            reason = "VULNERABILITIES_FOUND"
        if not reason and code != 0:
            reason = "SCANNER_RUNTIME_ERROR"
    except (OSError, ValueError, TypeError, AttributeError):
        reason = reason or runtime_failure(code, "") or "INVALID_REPORT"
    result.update(
        verdict="PASS"
        if reason is None
        else "FAIL"
        if reason == "VULNERABILITIES_FOUND"
        else "BLOCKED",
        reason=reason,
        diagnostic=REASONS.get(reason, "Valid image report; no HIGH/CRITICAL findings"),
    )
    return result


class ImageIdentityError(ValueError):
    """The saved config cannot be bound to the inspected Docker identity."""


def archive_identity(archive: Path, source_id: str | None = None) -> str:
    with tarfile.open(archive) as saved:
        manifest = json.load(saved.extractfile("manifest.json"))
        if len(manifest) != 1:
            raise ValueError("Ambiguous image archive")
        member = saved.getmember(manifest[0]["Config"])
        if not member.isfile() or member.size > 16 * 1024 * 1024:
            raise ValueError("Invalid image config")
        config_id = "sha256:" + hashlib.sha256(saved.extractfile(member).read()).hexdigest()
        if source_id is None or source_id == config_id:
            return config_id

        def read_blob(identity):
            if not isinstance(identity, str) or not IMAGE_ID.fullmatch(identity):
                raise ImageIdentityError("Invalid OCI digest")
            try:
                blob = saved.getmember("blobs/sha256/" + identity.split(":")[1])
            except KeyError as error:
                raise ImageIdentityError("Missing inspected OCI identity") from error
            if not blob.isfile() or blob.size > 16 * 1024 * 1024:
                raise ImageIdentityError("Invalid OCI blob")
            data = saved.extractfile(blob).read()
            if "sha256:" + hashlib.sha256(data).hexdigest() != identity:
                raise ImageIdentityError("OCI digest mismatch")
            return json.loads(data)

        # Docker's classic store returns a config ID. Its containerd store can
        # return a manifest/index ID; verify every content-addressed hop instead.
        descriptor = read_blob(source_id)
        if "manifests" in descriptor:
            candidates = [
                item
                for item in descriptor["manifests"]
                if item.get("platform") == {"os": "linux", "architecture": "amd64"}
            ]
            if len(candidates) != 1:
                raise ImageIdentityError("Ambiguous OCI platform")
            descriptor = read_blob(candidates[0]["digest"])
        if descriptor.get("config", {}).get("digest") != config_id:
            raise ImageIdentityError("Inspected OCI image does not reference saved config")
        return config_id


def scan(name: str, stage: Path, private: Path, revision: dict) -> dict:
    image, source_id, config_id, code, failure = IMAGES[name], None, None, None, None
    facts = {}
    raw, log_path = private / f"{name}.raw.json", private / f"{name}.log"
    container_name = f"opspilot-s02-scan-{name}-{uuid4().hex[:12]}"
    with log_path.open("x", encoding="utf-8") as log:
        try:
            user = scanner_user()
            archive, output, cache = stage_paths(stage, name)
            source_id = json.loads(
                subprocess.run(
                    ["docker", "image", "inspect", image],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
            )[0]["Id"]
            subprocess.run(
                ["docker", "image", "save", "--output", str(archive), image],
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
            config_id = archive_identity(archive, source_id)
            if config_id:
                command = container_command(archive, output, cache, user, container_name)
                facts = preflight(command, log)
                failure = preflight_failure(facts, user)
                log.write(json.dumps(facts) + "\n")
                log.flush()
                if failure is None:
                    code = subprocess.run(
                        [
                            *command,
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
                            "/output/report.json",
                            "--input",
                            "/input/image.tar",
                        ],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=False,
                        timeout=1500,
                    ).returncode
                    if (output / "report.json").is_file():
                        shutil.copyfile(output / "report.json", raw)
        except subprocess.TimeoutExpired:
            failure = "SCAN_TIMEOUT"  # Killed Docker CLI cannot tell us Trivy's exit code.
        except PermissionError:
            failure = "PERMISSION_DENIED"
        except ImageIdentityError:
            failure = "IMAGE_ID_MISMATCH"
        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            IndexError,
            tarfile.TarError,
            subprocess.CalledProcessError,
        ) as error:
            log.write(f"\n{error!r}\n")
            failure = "SCANNER_RUNTIME_ERROR"
        finally:
            try:
                subprocess.run(
                    ["docker", "rm", "--force", container_name],
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                failure = failure or "SCANNER_RUNTIME_ERROR"
    failure = failure or runtime_failure(
        code, log_path.read_text(encoding="utf-8", errors="replace")
    )
    result = summarize(
        raw,
        code,
        image,
        failure=failure,
        source_id=source_id,
        config_id=config_id,
        source_verified=config_id is not None,
    )
    result.update(
        **revision,
        preflight=facts,
        host={
            "platform": os.name,
            "uid": os.geteuid() if os.name != "nt" else None,
            "gid": os.getegid() if os.name != "nt" else None,
        },
        log={"raw_sha256": sha256(log_path)},
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=list(IMAGES), default=list(IMAGES))
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    run_id = uuid4().hex
    destination = args.evidence_dir or EVIDENCE / run_id
    destination.mkdir(parents=True, exist_ok=False)
    private = LOCAL / run_id
    private.mkdir(mode=0o700, parents=True, exist_ok=False)
    revision = provenance()
    results = []
    with tempfile.TemporaryDirectory(prefix="opspilot-s02-scanner-") as temporary:
        for name in dict.fromkeys(args.only):
            result = scan(name, Path(temporary), private, revision)
            (destination / f"{name}-cves.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            results.append(result)
            print(
                f"{name}: {result['verdict']} ({result['reason'] or 'OK'}; Trivy exit={result['exit_code']}; {result['diagnostic']})",
                flush=True,
            )
    return int(any(row["verdict"] != "PASS" for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
