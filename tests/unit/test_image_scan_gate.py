"""A crashed scanner or an empty stale report must never produce a green gate."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("imagegate", ROOT / "scripts/scan_images.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


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
def test_scan_exit_and_findings_both_control_acceptance(
    tmp_path, monkeypatch, code, count, verdict
):
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    raw = tmp_path / "scan.json"
    raw.write_text(
        json.dumps(
            {
                "Metadata": {},
                "Results": [
                    {
                        "Vulnerabilities": [
                            {"VulnerabilityID": "CVE-SYNTHETIC", "Severity": "HIGH"}
                        ]
                        * count
                    }
                ],
            }
        )
    )
    result = scanner.summarize(raw, code, "test-only-image")
    assert result["verdict"] == verdict
    assert len(result["vulnerabilities"]) == count


def test_missing_scan_report_is_blocked_even_on_exit_zero(tmp_path):
    assert scanner.summarize(tmp_path / "absent.json", 0, "test-only-image")["verdict"] == "BLOCKED"
