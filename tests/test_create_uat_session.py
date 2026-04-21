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


def test_create_uat_session_writes_markdown_with_ready_status(tmp_path: Path, monkeypatch, capsys) -> None:
    script = _load_script_module("decisiondoc_create_uat_session_ready", "scripts/create_uat_session.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"
    output_dir = tmp_path / "reports" / "uat"
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

    monkeypatch.setattr(script._uat_preflight.request, "urlopen", _fake_urlopen)

    result = script.main(
        [
            "--env-file",
            str(env_file),
            "--report-dir",
            str(report_dir),
            "--output-dir",
            str(output_dir),
            "--session-name",
            "proposal-uat",
            "--owner",
            "qa-user",
        ]
    )

    captured = capsys.readouterr().out
    files = sorted(output_dir.glob("uat-session-*-proposal-uat.md"))
    assert result == 0
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Preflight 상태: **READY**" in content
    assert "- 담당자: qa-user" in content
    assert "POST /generate/with-attachments (auth) -> 200 files=1 docs=4" not in content
    assert "Created UAT session:" in captured
    assert "Preflight status: READY" in captured


def test_create_uat_session_writes_markdown_even_when_blocked(tmp_path: Path, monkeypatch, capsys) -> None:
    script = _load_script_module("decisiondoc_create_uat_session_blocked", "scripts/create_uat_session.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"
    output_dir = tmp_path / "reports" / "uat"
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

    monkeypatch.setattr(script._uat_preflight.request, "urlopen", _fake_urlopen)

    result = script.main(
        [
            "--env-file",
            str(env_file),
            "--report-dir",
            str(report_dir),
            "--output-dir",
            str(output_dir),
            "--session-name",
            "blocked-uat",
        ]
    )

    captured = capsys.readouterr().out
    files = sorted(output_dir.glob("uat-session-*-blocked-uat.md"))
    assert result == 1
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Preflight 상태: **BLOCKED**" in content
    assert "quality-first routing gap" in content
    assert "- status: `failed`" in content
    assert "- skip_smoke: `yes`" in content
    assert "Preflight status: BLOCKED" in captured
