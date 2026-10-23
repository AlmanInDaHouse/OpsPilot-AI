"""Scanner failures, malformed reports, CVEs and mismatched identities fail closed."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("imagegate", ROOT / "scripts/scan_images.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)
IDENTITY = "sha256:" + "a" * 64


def report(tmp_path, count=0):
    raw = tmp_path / "scan.json"
    raw.write_text(
        json.dumps(
            {
                "SchemaVersion": 2,
                "ArtifactType": "container_image",
                "Metadata": {"ImageID": IDENTITY},
                "Results": [
                    {
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-SYNTHETIC",
                                "PkgName": "test-only",
                                "Severity": "CRITICAL",
                            }
                        ]
                        * count
                    }
                ],
            }
        )
    )
    return raw


@pytest.mark.parametrize(
    "code,count,verdict",
    [
        (0, 0, "PASS"),
        (1, 0, "BLOCKED"),
        (2, 0, "BLOCKED"),
        (-9, 0, "BLOCKED"),
        (1, 1, "FAIL"),
        (0, 1, "FAIL"),
    ],
)
def test_scan_exit_and_findings_both_control_acceptance(tmp_path, code, count, verdict):
    result = scanner.summarize(
        report(tmp_path, count), code, "test-only-image", source_id=IDENTITY, config_id=IDENTITY
    )
    assert result["verdict"] == verdict
    assert len(result["vulnerabilities"]) == count
    assert result["exit_code"] == code


def test_missing_scan_report_is_blocked_even_on_exit_zero(tmp_path):
    result = scanner.summarize(tmp_path / "absent.json", 0, "test-only-image")
    assert result["verdict"] == "BLOCKED"
    assert result["reason"] == "INVALID_REPORT"


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "{}",
        "[]",
        '{"SchemaVersion":2}',
        '{"SchemaVersion":2,"ArtifactType":"container_image","Metadata":null}',
        '{"SchemaVersion":2,"ArtifactType":"container_image","Metadata":{"ImageID":"invalid"},"Results":[]}',
    ],
)
def test_corrupt_or_incomplete_reports_block(tmp_path, payload):
    raw = tmp_path / "invalid.json"
    raw.write_text(payload)
    result = scanner.summarize(raw, 0, "test-only-image")
    assert result["verdict"] == "BLOCKED"
    assert result["reason"] == "INVALID_REPORT"


@pytest.mark.parametrize(
    "source,config",
    [("sha256:" + "b" * 64, IDENTITY), (IDENTITY, "sha256:" + "b" * 64), (None, None)],
)
def test_every_image_identity_must_match(tmp_path, source, config):
    result = scanner.summarize(
        report(tmp_path), 0, "test-only-image", source_id=source, config_id=config
    )
    assert result["reason"] == "IMAGE_ID_MISMATCH"
    assert result["verdict"] == "BLOCKED"


@pytest.mark.parametrize(
    "code,log,expected",
    [
        (1, "cache /cache/db: permission denied", "CACHE_UNWRITABLE"),
        (1, "open /input/image.tar: permission denied", "INPUT_UNREADABLE"),
        (1, "open /output/report.json: permission denied", "PERMISSION_DENIED"),
        (1, "context deadline exceeded", "SCAN_TIMEOUT"),
        (125, "unrelated Docker failure", "SCANNER_RUNTIME_ERROR"),
        (1, "FATAL download: network unavailable", "SCANNER_RUNTIME_ERROR"),
    ],
)
def test_normalized_cause_without_arbitrary_log_publication(tmp_path, code, log, expected):
    sentinel = "synthetic-private-lab-value"
    cause = scanner.runtime_failure(code, log + sentinel)
    result = scanner.summarize(tmp_path / "absent.json", code, "test-only", failure=cause)
    assert result["reason"] == expected
    assert result["exit_code"] == code
    assert sentinel not in json.dumps(result)
    assert result["verdict"] == "BLOCKED"


def test_mounts_are_minimal_and_input_readonly(tmp_path):
    archive, output, cache = scanner.stage_paths(tmp_path, "api")
    command = scanner.container_command(archive, output, cache, "10001:10001", "test-only")
    mounts = [item for item in command if item.startswith("type=bind,")]
    assert len(mounts) == 3
    assert mounts[0].endswith("target=/input/image.tar,readonly")
    assert {output.resolve().parent.parent, cache.resolve().parent} == {tmp_path.resolve()}
    assert not any("artifacts/local" in item or "docker.sock" in item for item in command)
    assert "--read-only" in command and "--cap-drop" in command
    assert scanner.SCANNER.endswith(
        "@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c"
    )


@pytest.mark.parametrize("name", ["../escape", "/lab", "other"])
def test_staging_cannot_escape(tmp_path, name):
    with pytest.raises(ValueError):
        scanner.stage_paths(tmp_path, name)


def test_preexisting_stage_subdirectory_is_rejected(tmp_path):
    (tmp_path / "api").mkdir()
    with pytest.raises(FileExistsError):
        scanner.stage_paths(tmp_path, "api")


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("input_readable", "INPUT_UNREADABLE"),
        ("output_writable", "PERMISSION_DENIED"),
        ("cache_writable", "CACHE_UNWRITABLE"),
        ("lab_inaccessible", "PERMISSION_DENIED"),
        ("input_readonly", "PERMISSION_DENIED"),
    ],
)
def test_preflight_denies_invalid_access(fault, expected):
    facts = dict(
        uid=10001,
        gid=10001,
        exit_code=0,
        input_readable=True,
        output_writable=True,
        cache_writable=True,
        lab_inaccessible=True,
        input_readonly=True,
    )
    facts[fault] = False
    assert scanner.preflight_failure(facts, "10001:10001") == expected


def test_timeout_in_execution_is_blocked_and_container_removed(tmp_path, monkeypatch):
    private = tmp_path / "private"
    private.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    calls = []
    monkeypatch.setattr(scanner, "scanner_user", lambda: "10001:10001")
    monkeypatch.setattr(scanner, "archive_identity", lambda *args: IDENTITY)
    monkeypatch.setattr(scanner, "preflight", lambda *args: {})
    monkeypatch.setattr(scanner, "preflight_failure", lambda *args: None)

    def run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, json.dumps([{"Id": IDENTITY}]))
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, 1500)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(scanner.subprocess, "run", run)
    result = scanner.scan("api", stage, private, {})
    assert result["reason"] == "SCAN_TIMEOUT"
    assert result["exit_code"] is None
    assert result["verdict"] == "BLOCKED"
    assert any(command[:3] == ["docker", "rm", "--force"] for command in calls)


@pytest.mark.parametrize(
    "fault", [None, "wrong-source", "tampered-manifest", "wrong-config", "ambiguous"]
)
def test_oci_index_is_cryptographically_bound_to_config(tmp_path, fault):
    import hashlib
    import io
    import tarfile

    config = b'{"architecture":"amd64","os":"linux"}'
    config_id = "sha256:" + hashlib.sha256(config).hexdigest()
    manifest = json.dumps(
        {"config": {"digest": config_id if fault != "wrong-config" else IDENTITY}}
    ).encode()
    manifest_id = "sha256:" + hashlib.sha256(manifest).hexdigest()
    descriptor = {"digest": manifest_id, "platform": {"os": "linux", "architecture": "amd64"}}
    index = json.dumps({"manifests": [descriptor] * (2 if fault == "ambiguous" else 1)}).encode()
    index_id = "sha256:" + hashlib.sha256(index).hexdigest()
    docker_manifest = json.dumps([{"Config": "blobs/sha256/" + config_id.split(":")[1]}]).encode()
    blobs = {
        "manifest.json": docker_manifest,
        "blobs/sha256/" + config_id.split(":")[1]: config,
        "blobs/sha256/" + manifest_id.split(":")[1]: manifest
        if fault != "tampered-manifest"
        else b"{}",
        "blobs/sha256/" + index_id.split(":")[1]: index,
    }
    archive = tmp_path / "image.tar"
    with tarfile.open(archive, "w") as saved:
        for name, data in blobs.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            saved.addfile(member, io.BytesIO(data))
    assert scanner.archive_identity(archive, config_id) == config_id
    if fault is None:
        assert scanner.archive_identity(archive, index_id) == config_id
        assert scanner.archive_identity(archive, manifest_id) == config_id
    else:
        with pytest.raises(scanner.ImageIdentityError):
            scanner.archive_identity(archive, IDENTITY if fault == "wrong-source" else index_id)


def test_falsey_invalid_vulnerability_container_is_not_an_empty_scan(tmp_path):
    raw = report(tmp_path)
    payload = json.loads(raw.read_text())
    payload["Results"][0]["Vulnerabilities"] = 0
    raw.write_text(json.dumps(payload))
    assert (
        scanner.summarize(raw, 0, "test-only-image", source_id=IDENTITY, config_id=IDENTITY)[
            "reason"
        ]
        == "INVALID_REPORT"
    )


def test_root_identity_is_refused(monkeypatch):
    monkeypatch.setattr(scanner.os, "name", "posix")
    monkeypatch.setattr(scanner.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(scanner.os, "getegid", lambda: 1000, raising=False)
    with pytest.raises(PermissionError):
        scanner.scanner_user()
