"""TEST-02-SUPPLY: the scanner detects both working-tree and committed secrets."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("secretcheck", ROOT / "scripts/check_secrets.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def test_worktree_and_history_are_scanned(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "--quiet")
    artifact = tmp_path / "artifacts/session-01/checks.json"
    artifact.parent.mkdir(parents=True)
    public_digest = hashlib.sha256(b"documentary input fixture").hexdigest()
    artifact.write_text(json.dumps({"input_sha256": public_digest}, indent=2) + "\n")
    baseline = [
        {
            "filename": "artifacts/session-01/checks.json",
            "type": "Hex High Entropy String",
            "hashed_secret": hashlib.sha1(
                public_digest.encode(), usedforsecurity=False
            ).hexdigest(),
            "reason": "Public documentary checksum",
        }
    ]
    (tmp_path / ".secrets-allowlist.json").write_text(json.dumps(baseline, indent=2) + "\n")
    key = "AKIA" + "QWERTYUIOPASDFGH"
    file = tmp_path / "accidental.txt"
    file.write_text("aws_access_key_id = " + key + "\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Scanner Test",
        "-c",
        "user.email=scanner@opspilot.invalid",
        "commit",
        "--quiet",
        "-m",
        "synthetic scanner fixture",
    )
    result = scanner.scan_tree_and_history(tmp_path)
    assert result["unreviewed_tree"] and result["unreviewed_history"]
    assert set(result["unreviewed_tree"]) == {"accidental.txt"}
    assert set(result["unreviewed_history"]) == {"accidental.txt"}
    assert key not in json.dumps(result)
    file.write_text("clean\n")
    result = scanner.scan_tree_and_history(tmp_path)
    assert not result["unreviewed_tree"] and result["unreviewed_history"]
    file.unlink()
    result = scanner.scan_tree_and_history(tmp_path)
    assert not result["unreviewed_tree"] and result["unreviewed_history"]
