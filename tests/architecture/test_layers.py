"""TEST-02-ARCH: runtime source and deliberately invalid dependency graphs."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("arch", ROOT / "scripts/check_architecture.py")
arch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arch)


def test_real_source_has_no_forbidden_dependencies():
    assert arch.violations(ROOT / "src") == []


@pytest.mark.parametrize(
    "source",
    [
        "import sqlalchemy",
        "from httpx import Client",
        "from ...adapters.postgres import models",
        "from ..application import service",
        "import importlib",
        "__import__('httpx')",
    ],
)
def test_forbidden_imports_fail_including_relative(tmp_path, source):
    file = tmp_path / "opspilot/identity/domain/model.py"
    file.parent.mkdir(parents=True)
    file.write_text(source, encoding="utf-8")
    assert arch.violations(tmp_path)


def test_relative_cycle_detected(tmp_path):
    package = tmp_path / "opspilot/shared"
    package.mkdir(parents=True)
    (package / "a.py").write_text("from . import b", encoding="utf-8")
    (package / "b.py").write_text("from . import a", encoding="utf-8")
    assert any("cycle" in error for error in arch.violations(tmp_path))


def test_shared_and_adapter_boundaries(tmp_path):
    for name, source in (
        ("shared/a.py", "import opspilot.identity.domain.principal"),
        ("adapters/b.py", "import opspilot.entrypoints.api.app"),
    ):
        path = tmp_path / "opspilot" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    assert len(arch.violations(tmp_path)) >= 2
