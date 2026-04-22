from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _run_sheet_text() -> str:
    return """# Pilot Run Sheet — business-uat

- generated_at: 2026-04-22T00:00:00+00:00
- run_status: **OPEN**
- launch_status: `READY_TO_EXECUTE`
- launch_decision: `START`

## Pilot Context

- base_url: `https://admin.decisiondoc.kr`
- latest_report: `post-deploy-20260422T004726Z.json`
- provider: `claude,openai,gemini`
- quality_first: `ok`

## Pilot Run Log

### Run 1. 기본 문서 생성
- started_at:
- operator:
- business_owner:
- bundle_type:
- input_summary:
- request_id:
- bundle_id:
- export_checked:
- quality_feedback:
- issues:
- stop_decision:

### Run 2. 첨부 기반 문서 생성
- started_at:
- operator:
- business_owner:
- bundle_type:
- attachment_list:
- request_id:
- bundle_id:
- export_checked:
- quality_feedback:
- issues:
- stop_decision:

## Escalation / Stop Log

- [ ] `/health` 이상 없음

### Incident Notes
- 발생 시각:
- 증상:
- request_id:
- temporary action:
- final decision:

## Pilot Close-Out

- overall_result:
- accepted_for_next_batch:
- follow_up_items:
- evidence_paths:
  - post-deploy:
  - uat summary:
  - pilot handoff:
  - launch checklist:
"""


def test_run_pilot_sample_updates_run_sheet(monkeypatch, tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_run_pilot_sample", "scripts/run_pilot_sample.py")
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(), encoding="utf-8")

    def _fake_post_json(base_url: str, *, path: str, api_key: str, payload: dict, timeout_sec: int) -> dict:
        if path == "/generate":
            return {"request_id": "req-run-1", "bundle_id": "bundle-run-1"}
        if path == "/generate/export":
            return {"request_id": "req-export-1", "bundle_id": "bundle-export-1", "files": [{"doc_type": "docx"}]}
        raise AssertionError(path)

    def _fake_post_multipart(
        base_url: str,
        *,
        path: str,
        api_key: str,
        payload: dict,
        filename: str,
        content: bytes,
        content_type: str,
        timeout_sec: int,
    ) -> dict:
        assert path == "/generate/with-attachments"
        assert filename == "pilot-attachment.txt"
        assert content_type == "text/plain"
        assert b"Pilot attachment context" in content
        return {"request_id": "req-run-2", "bundle_id": "bundle-run-2", "docs": [{"doc_type": "proposal"}]}

    monkeypatch.setattr(script, "_post_json", _fake_post_json)
    monkeypatch.setattr(script, "_post_multipart", _fake_post_multipart)
    monkeypatch.setattr(script, "_now_utc_iso", lambda: "2026-04-22T00:00:00Z")

    summary = script.run_pilot_sample(
        run_sheet_file=run_sheet_file,
        base_url="https://admin.decisiondoc.kr",
        api_key="test-key",
        operator="codex",
        business_owner="sungjin",
        bundle_type="proposal_kr",
        timeout_sec=60,
    )

    content = run_sheet_file.read_text(encoding="utf-8")
    assert summary["run1_request_id"] == "req-run-1"
    assert summary["run2_request_id"] == "req-run-2"
    assert "- request_id: req-run-1" in content
    assert "- bundle_id: bundle-run-1" in content
    assert "- export_checked: generate/export 200 files=1" in content
    assert "- attachment_list: pilot-attachment.txt" in content
    assert "- request_id: req-run-2" in content
    assert "- stop_decision: continue" in content


def test_resolve_api_key_uses_environment(monkeypatch) -> None:
    script = _load_script_module("decisiondoc_run_pilot_sample_env", "scripts/run_pilot_sample.py")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "first-key,second-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)

    assert script._resolve_api_key("") == "first-key"
