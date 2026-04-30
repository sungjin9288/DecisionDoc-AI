from __future__ import annotations

from pathlib import Path

from scripts import create_pilot_handoff as create_pilot_handoff_script
from scripts.create_pilot_handoff import (
    build_pilot_handoff_markdown,
    build_pilot_handoff_payload,
    create_pilot_handoff,
    parse_uat_summary,
)


def test_parse_uat_summary_reads_ready_fields(tmp_path):
    summary_file = tmp_path / "uat-summary.md"
    summary_file.write_text(
        """# UAT Final Summary — business-uat

- overall_status: **READY_FOR_PILOT**

## Summary

- recorded_entries: `10`
- scenario_count: `5`
- pass_count: `2`
- blocker_count: `0`
- follow_up_count: `0`
""",
        encoding="utf-8",
    )

    parsed = parse_uat_summary(summary_file)

    assert parsed["session_title"] == "business-uat"
    assert parsed["overall_status"] == "READY_FOR_PILOT"
    assert parsed["recorded_entries"] == "10"
    assert parsed["blocker_count"] == "0"


def test_build_pilot_handoff_payload_ready():
    payload = build_pilot_handoff_payload(
        uat_summary={"overall_status": "READY_FOR_PILOT"},
        preflight_payload={
            "ready": True,
            "latest_report": {"status": "passed", "file": "post-deploy-20260422T004726Z.json"},
            "health": {
                "provider": "claude,gemini,openai",
                "provider_routes": {
                    "default": "claude,gemini,openai",
                    "generation": "claude,openai,gemini",
                    "attachment": "gemini,claude,openai",
                    "visual": "openai",
                },
                "provider_policy_checks": {"quality_first": "ok"},
            },
        },
    )

    assert payload["pilot_status"] == "READY_FOR_PILOT"


def test_build_pilot_handoff_payload_follow_up_required():
    payload = build_pilot_handoff_payload(
        uat_summary={"overall_status": "FOLLOW_UP_REQUIRED"},
        preflight_payload={
            "ready": True,
            "latest_report": {"status": "passed"},
            "health": {},
        },
    )

    assert payload["pilot_status"] == "FOLLOW_UP_REQUIRED"


def test_create_pilot_handoff_writes_markdown(tmp_path, monkeypatch):
    summary_file = tmp_path / "uat-summary.md"
    summary_file.write_text(
        """# UAT Final Summary — business-uat

- overall_status: **READY_FOR_PILOT**

## Summary

- recorded_entries: `10`
- scenario_count: `5`
- pass_count: `2`
- blocker_count: `0`
- follow_up_count: `0`
""",
        encoding="utf-8",
    )

    def _fake_preflight(*, base_url, report_dir):  # noqa: ANN001
        return {
            "ready": True,
            "base_url": base_url,
            "latest_report": {"status": "passed", "file": "post-deploy-20260422T004726Z.json"},
            "health": {
                "provider": "claude,gemini,openai",
                "provider_routes": {
                    "default": "claude,gemini,openai",
                    "generation": "claude,openai,gemini",
                    "attachment": "gemini,claude,openai",
                    "visual": "openai",
                },
                "provider_policy_checks": {"quality_first": "ok"},
            },
        }

    monkeypatch.setattr("scripts.create_pilot_handoff.build_uat_preflight_payload", _fake_preflight)

    payload, output_path = create_pilot_handoff(
        summary_file=summary_file,
        base_url="https://admin.decisiondoc.kr",
        report_dir=tmp_path / "reports" / "post-deploy",
        output_dir=tmp_path / "reports" / "pilot",
    )

    assert payload["pilot_status"] == "READY_FOR_PILOT"
    markdown = output_path.read_text(encoding="utf-8")
    assert "pilot_status: **READY_FOR_PILOT**" in markdown
    assert "Go decision: `GO`" in markdown
    assert "generation: `claude,openai,gemini`" in markdown


def test_create_pilot_handoff_main_explicit_base_url_does_not_require_env_file(tmp_path, monkeypatch, capsys):
    summary_file = tmp_path / "uat-summary.md"
    summary_file.write_text(
        """# UAT Final Summary — business-uat

- overall_status: **READY_FOR_PILOT**
""",
        encoding="utf-8",
    )
    captured_args = {}

    def _fake_create_pilot_handoff(*, summary_file, base_url, report_dir, output_dir):  # noqa: ANN001
        captured_args["summary_file"] = summary_file
        captured_args["base_url"] = base_url
        captured_args["report_dir"] = report_dir
        captured_args["output_dir"] = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "pilot-handoff.md"
        output_path.write_text("# Pilot Handoff\n", encoding="utf-8")
        return {"pilot_status": "READY_FOR_PILOT"}, output_path

    monkeypatch.setattr(
        create_pilot_handoff_script,
        "create_pilot_handoff",
        _fake_create_pilot_handoff,
    )

    result = create_pilot_handoff_script.main(
        [
            "--summary-file",
            str(summary_file),
            "--env-file",
            str(tmp_path / "missing.env"),
            "--base-url",
            "https://admin.decisiondoc.kr",
            "--report-dir",
            str(tmp_path / "reports" / "post-deploy"),
            "--output-dir",
            str(tmp_path / "reports" / "pilot"),
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert captured_args["base_url"] == "https://admin.decisiondoc.kr"
    assert captured_args["summary_file"] == summary_file
    assert "Pilot status: READY_FOR_PILOT" in captured
