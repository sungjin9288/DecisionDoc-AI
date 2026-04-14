from __future__ import annotations

import importlib.util
import json
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
                "error": "docker compose ps failed with exit code 17",
                "checks": [
                    {"name": "health", "status": "passed"},
                    {"name": "docker compose ps", "status": "failed", "exit_code": 17},
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
    assert "- error=docker compose ps failed with exit code 17" in captured
    assert "- [passed] health" in captured
    assert "- [failed] docker compose ps exit_code=17" in captured


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
        "error": "docker compose ps failed with exit code 17",
        "checks": [
            {"name": "health", "status": "passed"},
            {"name": "docker compose ps", "status": "failed", "exit_code": 17},
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
    assert payload["latest_details"]["error"] == "docker compose ps failed with exit code 17"
    assert payload["latest_details"]["checks"][1]["exit_code"] == 17
