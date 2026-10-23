"""AST dependency fitness tests including relative imports and module cycles."""

import ast
from pathlib import Path


def violations(root: Path) -> list[str]:
    modules = {
        ".".join(path.relative_to(root).with_suffix("").parts).removesuffix(".__init__"): path
        for path in root.rglob("*.py")
    }
    graph: dict[str, set[str]] = {name: set() for name in modules}
    errors = []
    protected = {
        "fastapi",
        "sqlalchemy",
        "psycopg",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "subprocess",
    }
    for name, path in modules.items():
        parts = name.split(".")
        layer = parts[1] if len(parts) > 1 else ""
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                parent = name.split(".") if path.name == "__init__.py" else name.split(".")[:-1]
                if node.level:
                    base = ".".join(parent[: len(parent) - node.level + 1])
                    target = ".".join(filter(None, (base, node.module)))
                else:
                    target = node.module or ""
                targets = [target, *[f"{target}.{alias.name}" for alias in node.names]]
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
            ):
                errors.append(f"{name}: dynamic import prohibited")
            for target in targets:
                if target in modules:
                    graph[name].add(target)
                elif any(target.startswith(module + ".") for module in modules):
                    ancestor = max(
                        (module for module in modules if target.startswith(module + ".")), key=len
                    )
                    graph[name].add(ancestor)
                external = target.split(".")[0]
                if layer not in {"adapters", "entrypoints"} and external in protected:
                    errors.append(f"{name}: forbidden infrastructure import {target}")
                if layer not in {"adapters", "entrypoints"} and target.startswith("importlib"):
                    errors.append(f"{name}: dynamic import prohibited")
                if not target.startswith("opspilot."):
                    continue
                dest = target.split(".")
                dest_layer = dest[1]
                if layer == "shared" and dest_layer != "shared":
                    errors.append(f"{name}: shared depends on {target}")
                if layer in {"identity", "audit"}:
                    if dest_layer not in {layer, "shared"}:
                        errors.append(f"{name}: module boundary to {target}")
                    if "domain" in parts and "application" in dest:
                        errors.append(f"{name}: domain depends on application")
                if layer == "adapters" and dest_layer == "entrypoints":
                    errors.append(f"{name}: adapter depends on entrypoint")
    visiting, visited = set(), set()

    def walk(name: str) -> None:
        if name in visiting:
            errors.append(f"cycle: {name}")
            return
        if name in visited:
            return
        visiting.add(name)
        for child in graph[name] - {name}:
            walk(child)
        visiting.remove(name)
        visited.add(name)

    for name in modules:
        walk(name)
    return sorted(set(errors))


if __name__ == "__main__":
    found = violations(Path(__file__).resolve().parents[1] / "src")
    print("\n".join(found) if found else "Architecture PASS")
    raise SystemExit(bool(found))
