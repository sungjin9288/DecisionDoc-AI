#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
ROUTE_METHODS = {"get", "post", "put", "delete", "patch"}
METRIC_FIELDS = (
    "env_keys",
    "middleware_files",
    "route_decorators",
    "router_files",
    "service_files",
    "storage_files",
    "test_files",
    "test_functions",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _parse_python(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _count_test_functions(root: Path) -> int:
    count = 0
    for path in _python_files(root / "tests"):
        tree = _parse_python(path)
        count += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
    return count


def _route_owner_names(tree: ast.Module) -> set[str]:
    names = {"app", "router"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
            continue
        if value.func.id not in {"APIRouter", "FastAPI"}:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _is_route_decorator(node: ast.AST, *, owner_names: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in ROUTE_METHODS:
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id in owner_names


def _count_route_decorators(root: Path) -> int:
    count = 0
    for path in _python_files(root / "app"):
        tree = _parse_python(path)
        owner_names = _route_owner_names(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                count += sum(
                    _is_route_decorator(decorator, owner_names=owner_names)
                    for decorator in node.decorator_list
                )
    return count


def _count_env_keys(root: Path) -> int:
    pattern = re.compile(r"^[A-Z0-9_]+=")
    return sum(
        1
        for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
        if pattern.match(line)
    )


def _count_top_level_modules(path: Path) -> int:
    return sum(1 for item in path.glob("*.py") if item.name != "__init__.py")


def collect_metrics(root: Path = ROOT) -> dict[str, int]:
    resolved = root.resolve()
    return {
        "env_keys": _count_env_keys(resolved),
        "middleware_files": _count_top_level_modules(resolved / "app" / "middleware"),
        "route_decorators": _count_route_decorators(resolved),
        "router_files": _count_top_level_modules(resolved / "app" / "routers"),
        "service_files": _count_top_level_modules(resolved / "app" / "services"),
        "storage_files": _count_top_level_modules(resolved / "app" / "storage"),
        "test_files": sum(1 for _ in (resolved / "tests").rglob("test_*.py")),
        "test_functions": _count_test_functions(resolved),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count README metrics from source files using parsers where possible.",
    )
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Print all metrics as JSON.")
    parser.add_argument("--field", choices=METRIC_FIELDS, default=None)
    return parser.parse_args()


def _print_text(metrics: Mapping[str, int]) -> None:
    for key in sorted(metrics):
        print(f"{key}={metrics[key]}")


def main() -> int:
    args = _parse_args()
    metrics = collect_metrics(args.repo)
    if args.field is not None:
        print(metrics[args.field])
    elif args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
