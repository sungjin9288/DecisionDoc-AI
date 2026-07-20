from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.count_readme_metrics import collect_metrics


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_fixture_repo(root: Path) -> None:
    (root / "tests").mkdir()
    (root / "app" / "routers").mkdir(parents=True)
    (root / "app" / "services").mkdir()
    (root / "app" / "storage").mkdir()
    (root / "app" / "middleware").mkdir()

    (root / ".env.example").write_text(
        "\n".join(
            [
                "DECISIONDOC_PROVIDER=mock",
                "# COMMENTED_OUT=value",
                "OPENAI_API_KEY=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_sample.py").write_text(
        "\n".join(
            [
                "def test_real():",
                "    pass",
                "",
                "async def test_async_real():",
                "    pass",
                "",
                "def helper():",
                "    return 'def test_not_real(): pass'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "app" / "routers" / "sample.py").write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "",
                "router = APIRouter()",
                "",
                "@router.get('/items')",
                "def list_items():",
                "    return []",
                "",
                "@router.post('/items')",
                "async def create_item():",
                "    return {}",
                "",
                "collection_router = APIRouter()",
                "",
                "@collection_router.delete('/items/{item_id}')",
                "def delete_item(item_id: str):",
                "    return {'item_id': item_id}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for package in ("services", "storage", "middleware"):
        (root / "app" / package / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")


def test_collect_metrics_counts_source_definitions_without_string_matches(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)

    metrics = collect_metrics(tmp_path)

    assert metrics["test_functions"] == 2
    assert metrics["test_files"] == 1
    assert metrics["route_decorators"] == 3
    assert metrics["env_keys"] == 2
    assert metrics["router_files"] == 1
    assert metrics["service_files"] == 1
    assert metrics["storage_files"] == 1
    assert metrics["middleware_files"] == 1


def test_count_readme_metrics_cli_outputs_json_and_single_field(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)
    script = REPO_ROOT / "scripts" / "count_readme_metrics.py"

    json_result = subprocess.run(
        [sys.executable, str(script), "--repo", str(tmp_path), "--json"],
        check=True,
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )
    field_result = subprocess.run(
        [sys.executable, str(script), "--repo", str(tmp_path), "--field", "test_functions"],
        check=True,
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )

    assert json.loads(json_result.stdout)["test_functions"] == 2
    assert field_result.stdout.strip() == "2"


def test_readme_and_development_plan_counts_match_source() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    plan = (REPO_ROOT / "docs" / "development-plan.md").read_text(encoding="utf-8")

    metrics = collect_metrics(REPO_ROOT)
    test_functions_command = "python3 scripts/count_readme_metrics.py --field test_functions"
    test_files_command = "python3 scripts/count_readme_metrics.py --field test_files"
    route_command = "python3 scripts/count_readme_metrics.py --field route_decorators"
    env_command = "python3 scripts/count_readme_metrics.py --field env_keys"

    assert f"테스트 함수는 **{metrics['test_functions']:,}개**, **{metrics['test_files']}개 파일**" in readme
    assert f"{test_functions_command}  # → {metrics['test_functions']}" in readme
    assert f"{test_files_command}      # → {metrics['test_files']}" in readme
    assert f"FastAPI 라우트는 **{metrics['route_decorators']}개**" in readme
    assert f"{route_command}  # → {metrics['route_decorators']}" in readme
    assert f"`.env.example`에 **{metrics['env_keys']}개** 키가 정의돼 있습니다." in readme
    assert f"{env_command}  # → {metrics['env_keys']}" in readme
    assert (
        f"라우트 {metrics['route_decorators']} · 테스트 {metrics['test_functions']:,} "
        f"· env 키 {metrics['env_keys']}"
    ) in readme

    assert f"# → {metrics['router_files']} (top-level 라우터 파일)" in plan
    assert f"# → {metrics['service_files']} (서비스)" in plan
    assert f"# → {metrics['storage_files']} (top-level storage modules)" in plan
    assert f"# → {metrics['middleware_files']} (미들웨어)" in plan
    assert f"# → {metrics['route_decorators']} (라우트)" in plan
    assert "python3 scripts/count_readme_metrics.py --field router_files" in plan
    assert "python3 scripts/count_readme_metrics.py --field route_decorators" in plan

    stale_metric_commands = (
        "grep -rE " + '"def test_" tests',
        "find tests -name " + '"*.py"',
        "ls " + "app/routers",
        "ls " + "app/services",
        "ls " + "app/storage",
        "ls " + "app/middleware",
        "grep -rE " + '"@(app|router)',
    )
    for stale_command in stale_metric_commands:
        assert stale_command not in readme
        assert stale_command not in plan
