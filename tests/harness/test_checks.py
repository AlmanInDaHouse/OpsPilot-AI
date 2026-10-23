"""Negative fixtures prove the documentary gates reject material inconsistencies."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("checks", ROOT / "scripts/check_repository.py")
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)


class HarnessChecks(unittest.TestCase):
    def setUp(self):
        self.workflow = json.loads(
            (ROOT / "contracts/workflow-v1.json").read_text(encoding="utf-8")
        )
        self.diagram = (ROOT / "docs/architecture/C4.md").read_text(encoding="utf-8")

    def test_broken_markdown_link_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            errors = CHECKS.check_links(root, root / "a.md", "[missing](missing.md)")
            self.assertTrue(any("broken link" in error for error in errors))

    def test_inventory_order_is_case_sensitive_and_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.py", "Z.md", "B.json"):
                (root / name).write_text("content\n", encoding="utf-8")
            self.assertEqual(["B.json", "Z.md", "a.py"], [p.name for p in CHECKS.files(root)])

    def test_link_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(CHECKS.check_links(root, root / "a.md", "[outside](../private.md)"))

    def test_code_example_links_are_not_treated_as_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                [], CHECKS.check_links(root, root / "a.md", "```text\n[demo](absent.md)\n```\n")
            )

    def test_unclosed_code_fence_fails(self):
        self.assertTrue(CHECKS.check_links(ROOT, ROOT / "a.md", "```text\nexample\n"))

    def test_json_pointer_missing_member_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "a.json"
            path.write_text('{"definitions": {}}', encoding="utf-8")
            self.assertTrue(CHECKS.check_refs(root, path, {"$ref": "#/definitions/Missing"}))

    def test_json_pointer_escape_and_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.json").write_text('{"a/b": {"~": 1}}', encoding="utf-8")
            self.assertEqual(
                [], CHECKS.check_refs(root, root / "a.json", {"$ref": "b.json#/a~1b/~0"})
            )

    def test_json_reference_outside_repository_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(CHECKS.check_refs(root, root / "a.json", {"$ref": "../private.json"}))

    def test_terminal_outgoing_transition_fails(self):
        self.workflow["transitions"]["SUCCEEDED"] = ["EXECUTING"]
        self.assertTrue(
            any(
                "terminal has outgoing" in e
                for e in CHECKS.check_workflow(self.workflow, self.diagram)
            )
        )

    def test_unknown_cannot_dispatch(self):
        self.workflow["transitions"]["OUTCOME_UNKNOWN"].append("EXECUTING")
        self.assertTrue(
            any("UNKNOWN must not" in e for e in CHECKS.check_workflow(self.workflow, self.diagram))
        )

    def test_unreachable_state_fails(self):
        self.workflow["states"].append("ORPHAN")
        self.workflow["transitions"]["ORPHAN"] = []
        self.assertTrue(
            any("unreachable" in e for e in CHECKS.check_workflow(self.workflow, self.diagram))
        )

    def test_mermaid_edge_mismatch_fails(self):
        diagram = self.diagram.replace("  QUEUED --> INVESTIGATING\n", "")
        self.assertTrue(
            any("edges differ" in e for e in CHECKS.check_workflow(self.workflow, diagram))
        )

    def test_trap_state_without_terminal_path_fails(self):
        self.workflow["transitions"]["OUTCOME_UNKNOWN"] = ["OUTCOME_UNKNOWN"]
        self.assertTrue(
            any(
                "without path to terminal" in e
                for e in CHECKS.check_workflow(self.workflow, self.diagram)
            )
        )

    def test_mermaid_terminal_mismatch_fails(self):
        diagram = self.diagram.replace("  SUCCEEDED --> [*]\n", "")
        self.assertTrue(
            any("terminals differ" in e for e in CHECKS.check_workflow(self.workflow, diagram))
        )

    def test_ninth_session_fails(self):
        roadmap = (ROOT / "docs/roadmap/ROADMAP_8_SESSIONS.md").read_text(encoding="utf-8")
        self.assertTrue(CHECKS.check_roadmap(roadmap + "\n## Sesión 09 — extra\n"))

    def test_roadmap_missing_security_gate_fails(self):
        roadmap = (ROOT / "docs/roadmap/ROADMAP_8_SESSIONS.md").read_text(encoding="utf-8")
        self.assertTrue(
            any(
                "Security gates" in e
                for e in CHECKS.check_roadmap(roadmap.replace("8. Security gates:", "8. Other:", 1))
            )
        )

    def test_tested_requirement_requires_evidence(self):
        row = {"requirement": "REQ-TEST-01", "status": "PROBADO", "evidence": []}
        for key in ("spec", "design", "task", "code", "test"):
            row[key] = ["README.md"]
        self.assertTrue(
            any("without evidence" in e for e in CHECKS.check_traceability(ROOT, [row]))
        )

    def test_implemented_requirement_requires_existing_code(self):
        row = {"requirement": "REQ-TEST-01", "status": "IMPLEMENTADO", "evidence": []}
        for key in ("spec", "design", "task", "test"):
            row[key] = ["README.md"]
        row["code"] = ["absent.py"]
        self.assertTrue(
            any("missing code file" in e for e in CHECKS.check_traceability(ROOT, [row]))
        )

    def test_duplicate_requirement_fails(self):
        rows = json.loads((ROOT / "specs/traceability.json").read_text(encoding="utf-8"))
        row = copy.deepcopy(rows[0])
        self.assertTrue(any("duplicate" in e for e in CHECKS.check_traceability(ROOT, [row, row])))

    def test_auth_removed_from_protected_route_fails(self):
        api = json.loads((ROOT / "contracts/platform.openapi.json").read_text(encoding="utf-8"))
        api["paths"]["/v1/me"]["get"]["security"] = []
        self.assertTrue(any("unauthenticated protected" in e for e in CHECKS.check_openapi(api)))

    def test_business_endpoint_in_platform_contract_fails(self):
        api = json.loads((ROOT / "contracts/platform.openapi.json").read_text(encoding="utf-8"))
        api["paths"]["/v1/incidents"] = {"post": {}}
        self.assertTrue(any("platform scope" in e for e in CHECKS.check_openapi(api)))

    def test_future_command_is_explicit_failure(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/dev.py"), "eval"],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("NOT_IMPLEMENTED", result.stderr)

    def test_report_path_cannot_overwrite_repository_document(self):
        before = (ROOT / "README.md").read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/check_repository.py"),
                "--report",
                str(ROOT / "README.md"),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual(before, (ROOT / "README.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
