"""Local success must not approve remote CI or S03; stale scans fail closed."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "verification", Path(__file__).resolve().parents[2] / "scripts/verify_session02.py"
)
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


@pytest.mark.parametrize("fault", [None, "stale", "missing", "archive", "scanner", "checks"])
def test_only_current_complete_local_evidence_passes_without_approving_s03(fault):
    images = {name: {"id": f"test-only-{name}"} for name in ("postgres", "keycloak", "api")}
    scans = {
        name: {
            "verdict": "PASS",
            "exit_code": 0,
            "archive_config_matches": True,
            "docker_image_id": image["id"],
        }
        for name, image in images.items()
    }
    runs = [{"exit_code": 0}]
    if fault == "stale":
        scans["keycloak"]["docker_image_id"] = "test-only-old-image"
    elif fault == "missing":
        del scans["keycloak"]
    elif fault == "archive":
        scans["keycloak"]["archive_config_matches"] = False
    elif fault == "scanner":
        scans["keycloak"]["exit_code"] = 2
    elif fault == "checks":
        runs = []
    report = verification.verification_summary(runs, images, scans)
    assert report["local_gates"] == ("PASS" if fault is None else "FAIL")
    assert report["session_03"] == "NO-GO"
    assert report["remote_ci"] == "NOT_RUN"
