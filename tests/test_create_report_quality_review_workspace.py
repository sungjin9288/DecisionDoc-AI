from __future__ import annotations

import importlib.util
import json
import shlex
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_PACK_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
APPLY_SCRIPT_PATH = REPO_ROOT / "scripts/apply_report_quality_review_decisions.py"
WORKSPACE_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_review_workspace.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _create_pack(tmp_path: Path, *, reviewer: str = "pm-reviewer") -> tuple[Path, dict]:
    create_script = _load_module(CREATE_PACK_SCRIPT_PATH, "create_report_quality_pack_for_workspace")
    result = create_script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-workspace",
        output_root=tmp_path,
        sample_count=3,
        reviewer=reviewer,
    )
    return Path(result["output_dir"]), result


def _embedded_payload(workspace: str) -> dict:
    start_marker = '<script id="review-decision-template" type="application/json">'
    start = workspace.index(start_marker) + len(start_marker)
    end = workspace.index("</script>", start)
    return json.loads(workspace[start:end])


def test_pilot_pack_creates_source_bound_browser_workspace(tmp_path):
    pack_dir, result = _create_pack(tmp_path)

    workspace_path = Path(result["review_workspace_path"])
    workspace = workspace_path.read_text(encoding="utf-8")
    embedded = _embedded_payload(workspace)
    decisions = json.loads(Path(result["review_decisions_path"]).read_text(encoding="utf-8"))

    assert workspace_path == pack_dir / "HUMAN_REVIEW_WORKSPACE.html"
    assert "Report Quality Pilot 검수" in workspace
    assert "review_decisions.browser-draft.json" in workspace
    assert "training authorization 없음" in workspace
    assert "교정 전" in workspace
    assert "교정 후" in workspace
    assert "검토 대상 claim" in workspace
    assert "사람 검토 결정 기록" in workspace
    assert "종합 품질 점수 입력" in workspace
    assert 'data-tone="pending">not ready' in workspace
    assert embedded["decision_file"] == decisions
    assert embedded["decision_file"]["training_authorized"] is False
    assert embedded["minimum_overall_score"] == 0.8
    assert embedded["minimum_dimension_scores"]["visual_design"] == 0.7
    assert embedded["minimum_dimension_scores"]["export_readiness"] == 0.8
    commands = embedded["review_commands"]
    assert shlex.split(commands["validate"])[2] == str(pack_dir)
    assert shlex.split(commands["validate"])[-1] == "--dry-run"
    assert shlex.split(commands["validate_ready"])[-2:] == [
        "--dry-run",
        "--require-ready",
    ]
    assert shlex.split(commands["apply"])[2] == str(pack_dir)
    assert shlex.split(commands["apply_ready"])[-1] == "--require-ready"
    assert 'data-copy-review-command="validate"' in workspace
    assert 'data-copy-review-command="apply"' in workspace
    assert 'data-review-command-preview="validate"' in workspace
    assert 'data-review-command-preview="apply"' in workspace
    assert 'data-copy-review-command="validate" disabled' in workspace
    assert 'data-copy-review-command="apply" disabled' in workspace
    assert "let downloadedDraftAccepted = null" in workspace
    assert "draft.decisions.every(decision => decision.decision === \"accepted\")" in workspace
    assert 'group.addEventListener("input", markDownloadedDraftStale)' in workspace
    assert 'group.addEventListener("change", markDownloadedDraftStale)' in workspace
    assert "검토 입력이 바뀌었습니다. 명령을 복사하기 전에 Draft를 다시 다운로드하세요." in workspace
    assert "document.execCommand(\"copy\")" in workspace
    assert len(embedded["decision_file"]["decisions"]) == 3
    assert "fetch(" not in workspace
    assert "XMLHttpRequest" not in workspace


def test_workspace_shell_quotes_pack_path_for_review_commands(tmp_path):
    quoted_root = tmp_path / "receiver's review packs"
    pack_dir, result = _create_pack(quoted_root)
    workspace = Path(result["review_workspace_path"]).read_text(encoding="utf-8")
    commands = _embedded_payload(workspace)["review_commands"]

    for command in commands.values():
        arguments = shlex.split(command)
        assert arguments[:2] == [
            "python3",
            "scripts/apply_report_quality_review_decisions.py",
        ]
        assert arguments[2] == str(pack_dir)
        assert arguments[3:5] == [
            "--browser-draft",
            "$HOME/Downloads/review_decisions.browser-draft.json",
        ]


def test_workspace_escapes_html_and_script_content(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "create_evidence_decisions_for_workspace")
    workspace_script = _load_module(WORKSPACE_SCRIPT_PATH, "create_escaped_report_quality_workspace")
    attack = '</script><img src=x onerror="alert(1)">'
    pack_dir, _ = _create_pack(tmp_path, reviewer=attack)
    first_draft_path = pack_dir / "drafts" / "pilot-rqc-workspace_sample_001.json"
    first_draft = json.loads(first_draft_path.read_text(encoding="utf-8"))
    first_draft["before"]["planning_summary"] = attack
    first_draft["quality_baseline"]["dimension_scores"].pop("logic")
    first_draft_path.write_text(
        json.dumps(first_draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    decisions_path = pack_dir / "review_decisions.evidence.json"
    apply_script.create_review_decision_template(
        pack_dir=pack_dir,
        output_path=decisions_path,
        start_pending=True,
    )
    workspace_path = pack_dir / "HUMAN_REVIEW_WORKSPACE.evidence.html"
    workspace_script.create_report_quality_review_workspace(
        pack_dir=pack_dir,
        decisions_path=decisions_path,
        output_path=workspace_path,
    )

    workspace = workspace_path.read_text(encoding="utf-8")
    embedded = _embedded_payload(workspace)

    assert attack not in workspace
    assert "\\u003c/script\\u003e" in workspace
    assert "&lt;/script&gt;&lt;img src=x onerror=\"alert(1)\"&gt;" in workspace
    assert "Validation errors" in workspace
    assert "검증 오류 수정" in workspace
    assert 'data-tone="error">invalid' in workspace
    assert embedded["decision_file"]["decisions"][0]["reviewer"] == attack


def test_workspace_rejects_stale_decision_binding(tmp_path):
    workspace_script = _load_module(WORKSPACE_SCRIPT_PATH, "create_stale_report_quality_workspace")
    pack_dir, result = _create_pack(tmp_path)
    draft_path = pack_dir / "drafts" / "pilot-rqc-workspace_sample_001.json"
    draft_path.write_text(draft_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="draft SHA-256 values are stale"):
        workspace_script.create_report_quality_review_workspace(
            pack_dir=pack_dir,
            decisions_path=Path(result["review_decisions_path"]),
            output_path=pack_dir / "SECOND_WORKSPACE.html",
        )


def test_workspace_refuses_existing_or_external_output(tmp_path):
    workspace_script = _load_module(WORKSPACE_SCRIPT_PATH, "create_guarded_report_quality_workspace")
    pack_dir, result = _create_pack(tmp_path)
    decisions_path = Path(result["review_decisions_path"])

    with pytest.raises(ValueError, match="refusing to overwrite"):
        workspace_script.create_report_quality_review_workspace(
            pack_dir=pack_dir,
            decisions_path=decisions_path,
        )
    with pytest.raises(ValueError, match="directly inside"):
        workspace_script.create_report_quality_review_workspace(
            pack_dir=pack_dir,
            decisions_path=decisions_path,
            output_path=tmp_path / "outside.html",
        )
    symlink_path = pack_dir / "workspace-link.html"
    symlink_path.symlink_to(tmp_path / "outside.html")
    with pytest.raises(ValueError, match="symlink pack files"):
        workspace_script.create_report_quality_review_workspace(
            pack_dir=pack_dir,
            decisions_path=decisions_path,
            output_path=symlink_path,
        )


def test_workspace_cli_writes_custom_pack_local_output(tmp_path, capsys):
    workspace_script = _load_module(WORKSPACE_SCRIPT_PATH, "create_report_quality_workspace_cli")
    pack_dir, result = _create_pack(tmp_path)
    output_path = pack_dir / "SECOND_WORKSPACE.html"

    exit_code = workspace_script.main([
        str(pack_dir),
        "--decisions",
        result["review_decisions_path"],
        "--output",
        str(output_path),
        "--json",
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifact_count"] == 3
    assert payload["training_authorized"] is False
    assert payload["output_path"] == str(output_path)
    assert output_path.is_file()
