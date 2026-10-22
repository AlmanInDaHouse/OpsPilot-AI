"""Bounded documentary fitness checks, not runtime or full schema validation."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "AGENTS.md", "README.md", "docs/product/PRD.md", "docs/product/SCOPE.md",
    "docs/product/NFR_SLO.md", "docs/architecture/ARCHITECTURE.md",
    "docs/architecture/C4.md", "docs/architecture/DATA_MODEL.md",
    "docs/architecture/WORKFLOW_ENGINE.md", "docs/architecture/AGENT_RUNTIME.md",
    "docs/architecture/API_CONTRACTS.md", "docs/security/THREAT_MODEL.md",
    "docs/security/CONTROL_MATRIX.md", "docs/engineering/CONSTITUTION.md",
    "docs/engineering/HARNESS.md", "docs/engineering/SDD.md",
    "docs/engineering/QUALITY_GATES.md", "docs/engineering/TEST_STRATEGY.md",
    "docs/engineering/SOURCES.md", "docs/decisions/README.md",
    "docs/roadmap/ROADMAP_8_SESSIONS.md", "docs/roadmap/SESSION_01_REVIEW.md",
    "docs/roadmap/SESSION_02_SPEC.md", "docs/roadmap/HANDOFF.md", "docs/roadmap/RISKS.md",
    "specs/TEMPLATE.md", "specs/002-platform/spec.md", "specs/002-platform/plan.md",
    "specs/002-platform/tasks.md", "specs/002-platform/checklist.md",
    "specs/traceability.json", "contracts/workflow-v1.json",
    "contracts/platform.openapi.json", "contracts/event-v1.schema.json",
    "contracts/proposal-v1.schema.json", ".github/workflows/harness.yml",
)
ROADMAP_FIELDS = (
    "Objetivo", "Alcance", "Especificaciones", "Dependencias", "Componentes", "Cambios",
    "Tests", "Security gates", "Quality gates", "Evidencias", "Riesgos", "GO / NO-GO",
)
IGNORED = {".git", ".venv", "__pycache__", "node_modules", "artifacts"}


def files(root):
    return sorted((p for p in root.rglob("*") if p.is_file()
                   and not any(part in IGNORED for part in p.relative_to(root).parts)),
                  key=lambda p: p.relative_to(root).as_posix())


def local_path(root, base, target):
    path = (base / unquote(target)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {target}")
    return path


def check_links(root, path, content):
    errors = []
    # Strip fenced code; only inline Markdown links are in this checker's scope.
    if len(re.findall(r"^```", content, re.M)) % 2:
        errors.append(f"{path.name}: unbalanced code fences")
    prose = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", content, flags=re.M | re.S)
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", prose):
        target = target.strip("<>")
        split = urlsplit(target)
        if split.scheme or split.netloc or not split.path:
            continue
        try:
            resolved = local_path(root, path.parent, split.path)
            if not resolved.exists():
                errors.append(f"{path.name}: broken link {target}")
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def check_refs(root, path, data):
    errors = []

    def walk(value):
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str):
                split = urlsplit(ref)
                if not split.scheme:
                    try:
                        source = path if not split.path else local_path(root, path.parent, split.path)
                        obj = json.loads(source.read_text(encoding="utf-8"))
                        if split.fragment:
                            if not split.fragment.startswith("/"):
                                raise ValueError("only JSON Pointer fragments supported")
                            for key in split.fragment[1:].split("/"):
                                key = unquote(key).replace("~1", "/").replace("~0", "~")
                                obj = obj[int(key)] if isinstance(obj, list) else obj[key]
                    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                        errors.append(f"{path.name}: invalid $ref {ref}: {exc}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return errors


def check_workflow(data, diagram):
    errors = []
    states = set(data["states"])
    terminals = set(data["terminal"])
    transitions = data["transitions"]
    if len(states) != len(data["states"]) or not terminals <= states:
        errors.append("workflow: duplicate states or unknown terminals")
    if set(transitions) != states or data["initial"] not in states:
        errors.append("workflow: incomplete transitions or invalid initial")
    for source, targets in transitions.items():
        if not set(targets) <= states or len(targets) != len(set(targets)):
            errors.append(f"workflow: unknown/duplicate target from {source}")
        if source in terminals and targets:
            errors.append(f"workflow: terminal has outgoing transitions: {source}")
    reachable = {data["initial"]}
    pending = [data["initial"]]
    while pending:
        for target in transitions.get(pending.pop(), []):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    if reachable != states:
        errors.append("workflow: unreachable states")
    can_finish = set(terminals)
    while True:
        expanded = can_finish | {source for source, targets in transitions.items()
                                 if set(targets) & can_finish}
        if expanded == can_finish:
            break
        can_finish = expanded
    if not states <= can_finish:
        errors.append("workflow: states without path to terminal")
    if transitions.get("OUTCOME_UNKNOWN") != ["VERIFYING", "NEEDS_OPERATOR"]:
        errors.append("workflow: UNKNOWN must not directly retry or dispatch")
    blocks = re.findall(r"```mermaid\s*\n(stateDiagram-v2.*?)```", diagram, re.S)
    if len(blocks) != 1:
        return errors + ["workflow: expected one state diagram"]
    edges = set(re.findall(r"^\s+([A-Z_]+) --> ([A-Z_]+)\s*$", blocks[0], re.M))
    expected = {(source, target) for source, targets in transitions.items() for target in targets}
    if edges != expected:
        errors.append("workflow: Mermaid/JSON edges differ")
    if set(re.findall(r"^\s+\[\*\] --> ([A-Z_]+)\s*$", blocks[0], re.M)) != {data["initial"]}:
        errors.append("workflow: Mermaid initial differs")
    if set(re.findall(r"^\s+([A-Z_]+) --> \[\*\]\s*$", blocks[0], re.M)) != terminals:
        errors.append("workflow: Mermaid terminals differ")
    return errors


def check_roadmap(content):
    parts = re.split(r"^## Sesión (\d{2})[^\n]*\n", content, flags=re.M)
    if parts[1::2] != [f"{number:02d}" for number in range(1, 9)]:
        return ["roadmap: expected exactly sessions 01..08"]
    errors = []
    for number, body in zip(parts[1::2], parts[2::2]):
        for index, field in enumerate(ROADMAP_FIELDS, 1):
            if not re.search(rf"^{index}\. {re.escape(field)}:\s*\S", body, re.M):
                errors.append(f"roadmap {number}: missing {field}")
    return errors


def check_traceability(root, rows):
    errors = []
    seen = set()
    states = {"PROPUESTO", "IMPLEMENTADO", "PROBADO", "VALIDADO"}
    for row in rows:
        req = row.get("requirement", "")
        if not re.fullmatch(r"REQ-[A-Z]+-\d{2}", req) or req in seen:
            errors.append(f"trace: invalid/duplicate requirement {req}")
        seen.add(req)
        if row.get("status") not in states:
            errors.append(f"trace {req}: invalid status")
        for field in ("spec", "design", "task", "code", "test", "evidence"):
            values = row.get(field)
            if not isinstance(values, list) or (field != "evidence" and not values):
                errors.append(f"trace {req}: missing {field} mapping")
                continue
            must_exist = field in {"spec", "design", "task"} or row.get("status") != "PROPUESTO"
            for value in values:
                try:
                    target = local_path(root, root, value.split("#")[0])
                    if must_exist and not target.is_file():
                        errors.append(f"trace {req}: missing {field} file {value}")
                except (ValueError, AttributeError) as exc:
                    errors.append(f"trace {req}: {exc}")
        if row.get("status") in {"PROBADO", "VALIDADO"} and not row.get("evidence"):
            errors.append(f"trace {req}: tested status without evidence")
    return errors


def check_openapi(data):
    errors = []
    expected = {"/health/live", "/health/ready", "/v1/me", "/v1/audit-events"}
    if set(data.get("paths", {})) != expected:
        errors.append("OpenAPI: session 02 platform scope differs")
    if data.get("security") != [{"bearerAuth": []}]:
        errors.append("OpenAPI: missing default bearer authentication")
    operation_ids = []
    for path, methods in data.get("paths", {}).items():
        for method, operation in methods.items():
            if method != "get":
                errors.append(f"OpenAPI: unexpected method {method}")
                continue
            operation_ids.append(operation.get("operationId"))
            if path.startswith("/v1/") and operation.get("security", data.get("security")) != [{"bearerAuth": []}]:
                errors.append(f"OpenAPI: unauthenticated protected route {path}")
            if path.startswith("/v1/") and not {"401", "403", "503"} <= operation.get("responses", {}).keys():
                errors.append(f"OpenAPI: missing protected errors {path}")
    if None in operation_ids or len(set(operation_ids)) != len(operation_ids):
        errors.append("OpenAPI: missing/duplicate operationId")
    return errors


def validate(root):
    errors = []
    inventory = files(root)
    for name in REQUIRED:
        path = root / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"required: missing/empty {name}")
    parsed = {}
    for path in inventory:
        if path.suffix in {".md", ".py", ".json", ".yml"}:
            content = path.read_text(encoding="utf-8")
            if not content.endswith("\n"):
                errors.append(f"format: missing final newline {path.name}")
            if any(line.rstrip() != line for line in content.splitlines()):
                errors.append(f"format: trailing whitespace {path.name}")
        if path.suffix == ".md":
            errors.extend(check_links(root, path, path.read_text(encoding="utf-8")))
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                parsed[path.relative_to(root).as_posix()] = data
                errors.extend(check_refs(root, path, data))
            except (ValueError, OSError) as exc:
                errors.append(f"JSON {path.name}: {exc}")
    try:
        errors.extend(check_workflow(parsed["contracts/workflow-v1.json"],
                                     (root / "docs/architecture/C4.md").read_text(encoding="utf-8")))
        errors.extend(check_roadmap((root / "docs/roadmap/ROADMAP_8_SESSIONS.md").read_text(encoding="utf-8")))
        rows = parsed["specs/traceability.json"]
        errors.extend(check_traceability(root, rows))
        product_ids = set(re.findall(r"\| (REQ-[A-Z]+-\d{2}) \|", (root / "docs/product/PRD.md").read_text(encoding="utf-8")))
        if product_ids != {row["requirement"] for row in rows}:
            errors.append("trace: PRD/manifest requirement set differs")
        errors.extend(check_openapi(parsed["contracts/platform.openapi.json"]))
        transition = parsed["contracts/event-v1.schema.json"]["properties"]["payload"]["properties"]["transition"]["properties"]
        for endpoint in ("from", "to"):
            if set(transition[endpoint]["enum"]) != set(parsed["contracts/workflow-v1.json"]["states"]):
                errors.append("events: transition state enum differs from workflow")
    except (KeyError, TypeError, OSError, ValueError) as exc:
        errors.append(f"structured input missing/invalid: {exc}")
    # This gate must be deliberately retired when session 02 is authorized.
    if (root / "src").exists() or (root / "infra").exists():
        errors.append("scope: session 01 must not implement product src/infra")
    return errors, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    errors, inventory = validate(ROOT)
    # Runtime evidence/handoff/review excluded to avoid a self-referential digest.
    digest = hashlib.sha256()
    excluded = {"docs/roadmap/SESSION_01_REVIEW.md", "docs/roadmap/HANDOFF.md"}
    for path in inventory:
        relative = path.relative_to(ROOT).as_posix()
        if relative not in excluded:
            digest.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    result = {
        "verdict": "FAIL" if errors else "PASS",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "files": len(inventory),
        "input_sha256": digest.hexdigest(),
        "digest_excludes": [".git", "artifacts", "__pycache__", ".venv", "node_modules", *sorted(excluded)],
        "checks": ["required documents", "whitespace and final newline", "Markdown links/fences", "JSON local refs",
                   "workflow graph and Mermaid parity", "eight sessions/twelve fields",
                   "traceability and PRD parity", "OpenAPI auth/scope", "session 01 scope"],
        "errors": errors,
        "limitations": "Not runtime, full OpenAPI/JSON Schema, secret scanning or Mermaid rendering validation.",
    }
    print(json.dumps(result, indent=2, ensure_ascii=True))
    if args.report:
        destination = args.report.resolve()
        allowed = (ROOT / "artifacts").resolve()
        if not destination.is_relative_to(allowed) or destination.suffix != ".json":
            parser.error("reports must be JSON files within this repository's artifacts/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
