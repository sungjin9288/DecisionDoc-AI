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


class _FakeResponse:
    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb


def _write_report_fixture(report_dir: Path, *, latest_status: str = "passed", quality_first: str = "ok", skip_smoke: bool = False) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_payload = {
        "status": latest_status,
        "base_url": "https://admin.decisiondoc.kr",
        "started_at": "2026-04-20T14:43:00+00:00",
        "finished_at": "2026-04-20T14:44:00+00:00",
        "skip_smoke": skip_smoke,
        "checks": [
            {"name": "health", "status": "passed"},
            {
                "name": "health provider routing",
                "status": "passed",
                "provider_routes": {
                    "default": "claude,gemini,openai",
                    "generation": "claude,openai,gemini",
                    "attachment": "gemini,claude,openai",
                    "visual": "openai",
                },
                "provider_route_checks": {
                    "default": "ok",
                    "generation": "ok",
                    "attachment": "ok",
                    "visual": "ok",
                },
                "provider_policy_checks": {
                    "quality_first": quality_first,
                },
                "provider_policy_issues": {
                    "quality_first": [] if quality_first == "ok" else ["quality-first routing gap"],
                },
            },
        ],
    }
    index_payload = {
        "updated_at": "2026-04-20T14:44:00+00:00",
        "latest": "latest.json",
        "latest_report": "post-deploy-20260420T144400Z.json",
        "reports": [
            {
                "file": "post-deploy-20260420T144400Z.json",
                "status": latest_status,
                "base_url": "https://admin.decisiondoc.kr",
                "finished_at": "2026-04-20T14:44:00+00:00",
                "skip_smoke": skip_smoke,
            }
        ],
    }
    (report_dir / "latest.json").write_text(json.dumps(latest_payload), encoding="utf-8")
    (report_dir / "post-deploy-20260420T144400Z.json").write_text(json.dumps(latest_payload), encoding="utf-8")
    (report_dir / "index.json").write_text(json.dumps(index_payload), encoding="utf-8")


def test_uat_preflight_reports_ready_state(tmp_path: Path, monkeypatch, capsys) -> None:
    script = _load_script_module("decisiondoc_uat_preflight_ready", "scripts/uat_preflight.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"
    _write_report_fixture(report_dir)

    def _fake_urlopen(url: str, timeout: float = 0.0):
        assert url == "https://admin.decisiondoc.kr/health"
        assert timeout == 10.0
        return _FakeResponse(
            json.dumps(
                {
                    "status": "ok",
                    "provider": "claude,gemini,openai",
                    "provider_routes": {
                        "default": "claude,gemini,openai",
                        "generation": "claude,openai,gemini",
                        "attachment": "gemini,claude,openai",
                        "visual": "openai",
                    },
                    "provider_policy_checks": {"quality_first": "ok"},
                    "provider_policy_issues": {"quality_first": []},
                }
            )
        )

    monkeypatch.setattr(script.request, "urlopen", _fake_urlopen)

    result = script.main(["--env-file", str(env_file), "--report-dir", str(report_dir)])

    captured = capsys.readouterr().out
    assert result == 0
    assert "Overall readiness: READY" in captured
    assert "PASS health (status=ok)" in captured
    assert "PASS quality_first (quality_first=ok)" in captured
    assert "PASS latest_report_status (status=passed)" in captured
    assert "PASS latest_report_smoke_mode (skip_smoke=no)" in captured
    assert "provider_routes=default:claude,gemini,openai generation:claude,openai,gemini" in captured


def test_uat_preflight_reports_blocked_state_when_quality_or_latest_fail(tmp_path: Path, monkeypatch, capsys) -> None:
    script = _load_script_module("decisiondoc_uat_preflight_blocked", "scripts/uat_preflight.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"
    _write_report_fixture(report_dir, latest_status="failed", quality_first="degraded", skip_smoke=True)

    def _fake_urlopen(url: str, timeout: float = 0.0):
        assert url == "https://admin.decisiondoc.kr/health"
        assert timeout == 10.0
        return _FakeResponse(
            json.dumps(
                {
                    "status": "ok",
                    "provider": "claude,gemini,openai",
                    "provider_routes": {
                        "default": "claude,gemini,openai",
                        "generation": "claude,openai,gemini",
                        "attachment": "gemini,claude,openai",
                        "visual": "openai",
                    },
                    "provider_policy_checks": {"quality_first": "degraded"},
                    "provider_policy_issues": {"quality_first": ["quality-first routing gap"]},
                }
            )
        )

    monkeypatch.setattr(script.request, "urlopen", _fake_urlopen)

    result = script.main(["--env-file", str(env_file), "--report-dir", str(report_dir)])

    captured = capsys.readouterr().out
    assert result == 1
    assert "Overall readiness: BLOCKED" in captured
    assert "FAIL quality_first (quality_first=degraded)" in captured
    assert "FAIL latest_report_status (status=failed)" in captured
    assert "FAIL latest_report_smoke_mode (skip_smoke=yes)" in captured
    assert "quality_first_issues=quality-first routing gap" in captured
