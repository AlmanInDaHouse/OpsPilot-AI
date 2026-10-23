"""Exercise scanner permissions and containment with the real pinned Docker image."""

import argparse
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from scan_images import SCANNER, container_command, preflight, preflight_failure, scanner_user


def verify() -> dict:
    rows = []
    user = scanner_user()
    cases = ["valid", "output", "cache", "input"]
    if os.name != "nt":
        cases += ["posix-output", "posix-cache", "posix-input", "original-uid-mismatch"]
    with tempfile.TemporaryDirectory(prefix="opspilot-s02-permissions-") as temporary:
        root = Path(temporary)
        # Sibling sentinel models a laboratory file outside all scanner mounts.
        (root / "lab-sentinel").write_text("synthetic test sentinel\n")
        for case in cases:
            stage = root / case
            stage.mkdir(mode=0o700)
            archive = stage / "image.tar"
            archive.write_bytes(b"synthetic archive for I/O probe only")
            archive.chmod(0o600)
            output, cache = stage / "output", stage / "cache"
            output.mkdir(mode=0o700)
            cache.mkdir(mode=0o700)
            effective = "10001:10001" if case == "original-uid-mismatch" else user
            if case == "original-uid-mismatch":
                archive.chmod(0o644)
                output.chmod(0o755)
                cache.chmod(0o755)
            if case.startswith("posix-"):
                {"posix-output": output, "posix-cache": cache, "posix-input": archive}[case].chmod(
                    0o000 if case == "posix-input" else 0o500
                )
            command = container_command(
                archive, output, cache, effective, "opspilot-s02-probe-" + uuid4().hex[:12]
            )
            if case in {"output", "cache"}:
                command = [
                    item + ",readonly"
                    if item.startswith("type=bind,") and item.endswith("target=/" + case)
                    else item
                    for item in command
                ]
            if case == "input":
                command = [
                    item.replace("target=/input/image.tar", "target=/input/unavailable.tar")
                    for item in command
                ]
            try:
                facts = preflight(command)
                cause = preflight_failure(facts, effective)
                expected = {
                    "valid": None,
                    "output": "PERMISSION_DENIED",
                    "cache": "CACHE_UNWRITABLE",
                    "input": "INPUT_UNREADABLE",
                    "posix-output": "PERMISSION_DENIED",
                    "posix-cache": "CACHE_UNWRITABLE",
                    "posix-input": "INPUT_UNREADABLE",
                    "original-uid-mismatch": "PERMISSION_DENIED",
                }[case]
                rows.append(
                    {
                        "case": case,
                        "expected": expected,
                        "reason": cause,
                        "facts": facts,
                        "verdict": "PASS"
                        if cause == expected and facts.get("lab_inaccessible") is True
                        else "FAIL",
                    }
                )
            finally:
                archive.chmod(0o600)
                output.chmod(0o700)
                cache.chmod(0o700)
    return {
        "scanner": SCANNER,
        "host_uid": os.geteuid() if os.name != "nt" else None,
        "host_gid": os.getegid() if os.name != "nt" else None,
        "user": user,
        "scope": "Real pinned scanner I/O probes, not vulnerability scans; Windows denies via read-only mounts; Linux additionally tests POSIX modes",
        "cases": rows,
        "verdict": "PASS" if all(row["verdict"] == "PASS" for row in rows) else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = verify()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    print("Scanner environment: " + report["verdict"])
    return int(report["verdict"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
