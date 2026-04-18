from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_show_post_deploy_reports_lists_recent_entries(tmp_path: Path, capsys) -> None:
    viewer = _load_script_module("decisiondoc_show_post_deploy_reports_list", "scripts/show_post_deploy_reports.py")
    report_dir = tmp_path / "reports" / "post-deploy"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest.json").write_text(
        json.dumps({"status": "passed", "checks": [{"name": "health", "status": "passed"}]}),
        encoding="utf-8",
    )
    (report_dir / "index.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-04-14T04:10:00+00:00",
                "latest": "latest.json",
                "latest_report": "post-deploy-20260414T041000Z.json",
                "reports": [
                    {
                        "file": "post-deploy-20260414T041000Z.json",
                        "status": "passed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T04:09:00+00:00",
                        "finished_at": "2026-04-14T04:10:00+00:00",
                        "skip_smoke": False,
                        "provider_routes": {
                            "default": "claude,gemini,openai",
                            "generation": "claude,gemini,openai",
                            "attachment": "gemini,claude,openai",
                            "visual": "openai,claude,gemini",
                        },
                        "smoke_response_code": "PROVIDER_FAILED",
                        "provider_error_code": "insufficient_quota",
                    },
                    {
                        "file": "post-deploy-20260414T031000Z.json",
                        "status": "failed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T03:09:00+00:00",
                        "finished_at": "2026-04-14T03:10:00+00:00",
                        "skip_smoke": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = viewer.main(["--report-dir", str(report_dir), "--limit", "1"])

    captured = capsys.readouterr().out
    assert result == 0
    assert "Report directory:" in captured
    assert "Latest report: post-deploy-20260414T041000Z.json" in captured
    assert "Recent reports (limit=1)" in captured
    assert "post-deploy-20260414T041000Z.json" in captured
    assert "provider_routes: generation=claude,gemini,openai" in captured
    assert "smoke_failure: code=PROVIDER_FAILED | provider_error_code=insufficient_quota" in captured
    assert "post-deploy-20260414T031000Z.json" not in captured


def test_show_post_deploy_reports_prints_latest_details(tmp_path: Path, capsys) -> None:
    viewer = _load_script_module("decisiondoc_show_post_deploy_reports_latest", "scripts/show_post_deploy_reports.py")
    report_dir = tmp_path / "reports" / "post-deploy"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "base_url": "https://admin.decisiondoc.kr",
                "started_at": "2026-04-14T04:09:00+00:00",
                "finished_at": "2026-04-14T04:10:00+00:00",
                "skip_smoke": False,
                "error": "deployed smoke failed with exit code 1 (smoke_response_code=PROVIDER_FAILED; provider_error_code=insufficient_quota)",
                "checks": [
                    {"name": "health", "status": "passed"},
                    {
                        "name": "health provider routing",
                        "status": "passed",
                        "provider_routes": {
                            "default": "claude,gemini,openai",
                            "generation": "claude,gemini,openai",
                            "attachment": "gemini,claude,openai",
                            "visual": "openai,claude,gemini",
                        },
                        "provider_route_checks": {
                            "default": "ok",
                            "generation": "ok",
                            "attachment": "ok",
                            "visual": "degraded",
                        },
                    },
                    {
                        "name": "deployed smoke",
                        "status": "failed",
                        "exit_code": 1,
                        "smoke_response_code": "PROVIDER_FAILED",
                        "provider_error_code": "insufficient_quota",
                        "smoke_message": "AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "index.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-04-14T04:10:00+00:00",
                "latest": "latest.json",
                "latest_report": "post-deploy-20260414T041000Z.json",
                "reports": [
                    {
                        "file": "post-deploy-20260414T041000Z.json",
                        "status": "failed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T04:09:00+00:00",
                        "finished_at": "2026-04-14T04:10:00+00:00",
                        "skip_smoke": False,
                        "smoke_response_code": "PROVIDER_FAILED",
                        "provider_error_code": "insufficient_quota",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = viewer.main(["--report-dir", str(report_dir), "--latest"])

    captured = capsys.readouterr().out
    assert result == 0
    assert "Latest report details" in captured
    assert "- error=deployed smoke failed with exit code 1 (smoke_response_code=PROVIDER_FAILED; provider_error_code=insufficient_quota)" in captured
    assert "- provider_routes=default:claude,gemini,openai generation:claude,gemini,openai attachment:gemini,claude,openai visual:openai,claude,gemini" in captured
    assert "- provider_route_checks=default:ok generation:ok attachment:ok visual:degraded" in captured
    assert "- smoke_failure: code=PROVIDER_FAILED | provider_error_code=insufficient_quota | message=AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요." in captured
    assert "- [passed] health" in captured
    assert "- [failed] deployed smoke exit_code=1" in captured


def test_show_post_deploy_reports_prints_json_summary(tmp_path: Path, capsys) -> None:
    viewer = _load_script_module("decisiondoc_show_post_deploy_reports_json", "scripts/show_post_deploy_reports.py")
    report_dir = tmp_path / "reports" / "post-deploy"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "index.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-04-14T04:10:00+00:00",
                "latest": "latest.json",
                "latest_report": "post-deploy-20260414T041000Z.json",
                "reports": [
                    {
                        "file": "post-deploy-20260414T041000Z.json",
                        "status": "passed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T04:09:00+00:00",
                        "finished_at": "2026-04-14T04:10:00+00:00",
                        "skip_smoke": False,
                    },
                    {
                        "file": "post-deploy-20260414T031000Z.json",
                        "status": "failed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T03:09:00+00:00",
                        "finished_at": "2026-04-14T03:10:00+00:00",
                        "skip_smoke": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = viewer.main(["--report-dir", str(report_dir), "--limit", "1", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["report_dir"] == str(report_dir)
    assert payload["latest_report"] == "post-deploy-20260414T041000Z.json"
    assert payload["updated_at"] == "2026-04-14T04:10:00+00:00"
    assert len(payload["reports"]) == 1
    assert payload["reports"][0]["file"] == "post-deploy-20260414T041000Z.json"
    assert "latest_details" not in payload


def test_show_post_deploy_reports_prints_json_with_latest_details(tmp_path: Path, capsys) -> None:
    viewer = _load_script_module("decisiondoc_show_post_deploy_reports_json_latest", "scripts/show_post_deploy_reports.py")
    report_dir = tmp_path / "reports" / "post-deploy"
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_payload = {
        "status": "failed",
        "base_url": "https://admin.decisiondoc.kr",
        "started_at": "2026-04-14T04:09:00+00:00",
        "finished_at": "2026-04-14T04:10:00+00:00",
        "skip_smoke": False,
        "error": "deployed smoke failed with exit code 1 (smoke_response_code=PROVIDER_FAILED; provider_error_code=insufficient_quota)",
        "checks": [
            {"name": "health", "status": "passed"},
            {
                "name": "health provider routing",
                "status": "passed",
                "provider_routes": {
                    "default": "claude,gemini,openai",
                    "generation": "claude,gemini,openai",
                    "attachment": "gemini,claude,openai",
                    "visual": "openai,claude,gemini",
                },
                "provider_route_checks": {
                    "default": "ok",
                    "generation": "ok",
                    "attachment": "ok",
                    "visual": "ok",
                },
            },
            {
                "name": "deployed smoke",
                "status": "failed",
                "exit_code": 1,
                "smoke_response_code": "PROVIDER_FAILED",
                "provider_error_code": "insufficient_quota",
            },
        ],
    }
    (report_dir / "latest.json").write_text(json.dumps(latest_payload), encoding="utf-8")
    (report_dir / "index.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-04-14T04:10:00+00:00",
                "latest": "latest.json",
                "latest_report": "post-deploy-20260414T041000Z.json",
                "reports": [
                    {
                        "file": "post-deploy-20260414T041000Z.json",
                        "status": "failed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T04:09:00+00:00",
                        "finished_at": "2026-04-14T04:10:00+00:00",
                        "skip_smoke": False,
                        "smoke_response_code": "PROVIDER_FAILED",
                        "provider_error_code": "insufficient_quota",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = viewer.main(["--report-dir", str(report_dir), "--json", "--latest"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["latest_details"]["status"] == "failed"
    assert payload["latest_details"]["error"] == "deployed smoke failed with exit code 1 (smoke_response_code=PROVIDER_FAILED; provider_error_code=insufficient_quota)"
    assert payload["latest_details"]["provider_routes"]["generation"] == "claude,gemini,openai"
    assert payload["latest_details"]["provider_route_checks"]["visual"] == "ok"
    assert payload["latest_details"]["provider_error_code"] == "insufficient_quota"
    assert payload["latest_details"]["checks"][2]["exit_code"] == 1


def test_show_post_deploy_reports_loads_without_app_ops_package_import(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "app.ops", types.ModuleType("app.ops"))
    viewer = _load_script_module(
        "decisiondoc_show_post_deploy_reports_no_app_ops_import",
        "scripts/show_post_deploy_reports.py",
    )
    report_dir = tmp_path / "reports" / "post-deploy"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "index.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-04-14T04:10:00+00:00",
                "latest": "latest.json",
                "latest_report": "post-deploy-20260414T041000Z.json",
                "reports": [
                    {
                        "file": "post-deploy-20260414T041000Z.json",
                        "status": "passed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T04:09:00+00:00",
                        "finished_at": "2026-04-14T04:10:00+00:00",
                        "skip_smoke": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = viewer.main(["--report-dir", str(report_dir), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["latest_report"] == "post-deploy-20260414T041000Z.json"
