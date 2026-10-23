"""Offline secret detection over tracked/untracked source and every local Git revision.

Only hashed findings are written. Private lab data and generated caches are excluded.
This heuristic scanner cannot prove the absence of secrets.
"""

import hashlib
import json
import logging
import subprocess
import xml.etree.ElementTree as ET
from contextlib import chdir
from pathlib import Path

from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import default_settings

ROOT = Path(__file__).resolve().parents[1]


def scan_tree_and_history(root: Path) -> dict:
    logging.getLogger("detect_secrets").setLevel(logging.ERROR)
    filenames = (
        subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    with default_settings() as settings:
        tree = SecretsCollection(root=str(root))
        for filename in filter(None, filenames):
            if filename == ".secrets-allowlist.json":
                continue  # Contains only scanner hashes, validated as closed records below.
            if (root / filename).is_file():
                tree.scan_file(filename)
        history = SecretsCollection(root=str(root))
        diff = subprocess.run(
            ["git", "log", "--all", "--format=", "--patch", "--no-ext-diff", "--no-renames"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8")
        with chdir(root):
            settings.disable_filters("detect_secrets.filters.common.is_invalid_file")
            history.scan_diff(diff)
    allowlist = json.loads((root / ".secrets-allowlist.json").read_text(encoding="utf-8"))
    import re

    for row in allowlist:
        if (
            set(row) != {"filename", "type", "hashed_secret", "reason"}
            or not re.fullmatch(r"[0-9a-f]{40}", row["hashed_secret"])
            or not row["reason"]
            or not (root / row["filename"]).is_file()
        ):
            raise ValueError("Invalid secret-scan exception record")
    approved = {(row["filename"], row["type"], row["hashed_secret"]) for row in allowlist}
    baseline_record_hashes = {
        hashlib.sha1(row["hashed_secret"].encode(), usedforsecurity=False).hexdigest()
        for row in allowlist
    }

    def baseline_record(filename, row):
        return (
            filename.replace("\\", "/") == ".secrets-allowlist.json"
            and row["type"] in {"Hex High Entropy String", "Secret Keyword"}
            and row["hashed_secret"] in baseline_record_hashes
        )

    def checksum_record(filename, row):
        # Only public digests/revision and container hostname in generated evidence;
        # other high-entropy values remain findings, including elsewhere in artifacts/.
        relative = filename.replace("\\", "/")
        if row["type"] != "Hex High Entropy String" or not relative.startswith(
            "artifacts/session-"
        ):
            return False
        if not (root / relative).is_file():
            return False
        if relative.endswith(".xml"):
            # Pytest reports the public Docker container hostname (12 hex digits).
            suites = ET.parse(root / relative).iter("testsuite")
            return any(
                re.fullmatch(r"[0-9a-f]{12}", suite.get("hostname", ""))
                and hashlib.sha1(suite.get("hostname").encode(), usedforsecurity=False).hexdigest()
                == row["hashed_secret"]
                for suite in suites
            )
        lines = (root / relative).read_text(encoding="utf-8").splitlines()
        if not 0 < row["line_number"] <= len(lines):
            return False
        return bool(
            re.fullmatch(
                r'\s*"(?:input_sha256|raw_sha256|lock_sha256|tree_sha256|hash)": "[0-9a-f]{64}",?',
                lines[row["line_number"] - 1],
            )
            or re.fullmatch(r'\s*"head": "[0-9a-f]{40}",?', lines[row["line_number"] - 1])
        )

    def unreviewed(findings):
        return {
            filename: rows
            for filename, all_rows in findings.items()
            if (
                rows := [
                    row
                    for row in all_rows
                    if (filename.replace("\\", "/"), row["type"], row["hashed_secret"])
                    not in approved
                    and not baseline_record(filename, row)
                    and not checksum_record(filename, row)
                ]
            )
        }

    return {
        "files": len(list(filter(None, filenames))),
        "tree_findings": tree.json(),
        "history_findings": history.json(),
        "unreviewed_tree": unreviewed(tree.json()),
        "unreviewed_history": unreviewed(history.json()),
        "allowlist": allowlist,
        "verification": "offline, no credentials sent to providers",
    }


def main() -> int:
    results = scan_tree_and_history(ROOT)
    print(json.dumps(results, indent=2))
    return int(bool(results["unreviewed_tree"] or results["unreviewed_history"]))


if __name__ == "__main__":
    raise SystemExit(main())
