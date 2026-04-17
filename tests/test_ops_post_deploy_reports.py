from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.ops.service import OpsInvestigationService


def _create_client(tmp_path: Path, monkeypatch, *, report_dir: Path) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "ops-secret")
    monkeypatch.setenv("DECISIONDOC_POST_DEPLOY_REPORT_DIR", str(report_dir))
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    import app.main as main_module

    monkeypatch.setattr(main_module, "get_ops_service", lambda: OpsInvestigationService())
    return TestClient(main_module.create_app())


def _write_report_history(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_payload = {
        "status": "passed",
        "base_url": "https://admin.decisiondoc.kr",
        "started_at": "2026-04-14T04:09:00+00:00",
        "finished_at": "2026-04-14T04:10:00+00:00",
        "skip_smoke": False,
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
            {"name": "smoke", "status": "passed", "exit_code": 0},
        ],
    }
    previous_payload = {
        "status": "failed",
        "base_url": "https://admin.decisiondoc.kr",
        "started_at": "2026-04-14T03:09:00+00:00",
        "finished_at": "2026-04-14T03:10:00+00:00",
        "skip_smoke": True,
        "error": "docker compose ps failed with exit code 17",
        "checks": [
            {"name": "health", "status": "passed"},
            {"name": "smoke", "status": "failed", "exit_code": 17},
        ],
    }
    index_payload = {
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
                "provider_route_checks": {
                    "default": "ok",
                    "generation": "ok",
                    "attachment": "ok",
                    "visual": "degraded",
                },
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
    (report_dir / "latest.json").write_text(json.dumps(latest_payload), encoding="utf-8")
    (report_dir / "post-deploy-20260414T041000Z.json").write_text(json.dumps(latest_payload), encoding="utf-8")
    (report_dir / "post-deploy-20260414T031000Z.json").write_text(json.dumps(previous_payload), encoding="utf-8")
    (report_dir / "index.json").write_text(json.dumps(index_payload), encoding="utf-8")


def test_ops_post_deploy_reports_requires_admin_or_ops_key(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "reports" / "post-deploy"
    _write_report_history(report_dir)
    client = _create_client(tmp_path, monkeypatch, report_dir=report_dir)

    response = client.get("/ops/post-deploy/reports")

    assert response.status_code == 401
    assert response.json()["detail"] == "인증이 필요합니다."


def test_ops_post_deploy_reports_returns_summary_for_ops_key(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "reports" / "post-deploy"
    _write_report_history(report_dir)
    client = _create_client(tmp_path, monkeypatch, report_dir=report_dir)

    response = client.get(
        "/ops/post-deploy/reports",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        params={"limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latest_report"] == "post-deploy-20260414T041000Z.json"
    assert len(body["reports"]) == 1
    assert body["reports"][0]["file"] == "post-deploy-20260414T041000Z.json"
    assert body["reports"][0]["provider_routes"]["generation"] == "claude,gemini,openai"
    assert body["latest_details"] is None


def test_ops_post_deploy_reports_returns_latest_details(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "reports" / "post-deploy"
    _write_report_history(report_dir)
    client = _create_client(tmp_path, monkeypatch, report_dir=report_dir)

    response = client.get(
        "/ops/post-deploy/reports",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        params={"latest": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latest_details"]["status"] == "passed"
    assert body["latest_details"]["provider_route_checks"]["visual"] == "degraded"
    assert body["latest_details"]["checks"][2]["name"] == "smoke"
    assert body["latest_details"]["checks"][2]["exit_code"] == 0


def test_ops_post_deploy_reports_returns_404_when_missing(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "reports" / "post-deploy"
    client = _create_client(tmp_path, monkeypatch, report_dir=report_dir)

    response = client.get(
        "/ops/post-deploy/reports",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Post-deploy report history not found."


def test_ops_post_deploy_report_detail_returns_selected_file(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "reports" / "post-deploy"
    _write_report_history(report_dir)
    client = _create_client(tmp_path, monkeypatch, report_dir=report_dir)

    response = client.get(
        "/ops/post-deploy/reports/post-deploy-20260414T031000Z.json",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report_file"] == "post-deploy-20260414T031000Z.json"
    assert body["details"]["status"] == "failed"
    assert body["details"]["error"] == "docker compose ps failed with exit code 17"
    assert body["details"]["checks"][1]["exit_code"] == 17


def test_ops_post_deploy_report_detail_rejects_unknown_file(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "reports" / "post-deploy"
    _write_report_history(report_dir)
    client = _create_client(tmp_path, monkeypatch, report_dir=report_dir)

    response = client.get(
        "/ops/post-deploy/reports/not-listed.json",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Requested post-deploy report not found."
