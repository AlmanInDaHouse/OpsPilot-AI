"""Worker composition must stay independent of identity, shell and API startup."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_worker_has_no_shell_oidc_or_api_dependency():
    tree = ast.parse((ROOT / "src/opspilot/entrypoints/worker.py").read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)
    assert not any(
        any(
            word in name
            for word in ("subprocess", "oidc", "identity", "entrypoints.api", "provision", "httpx")
        )
        for name in imports
    )


def test_api_does_not_launch_worker():
    for path in (ROOT / "src/opspilot/entrypoints/api").glob("*.py"):
        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module.endswith("worker") or node.module.endswith("jobs"))
            for node in ast.walk(tree)
        )
