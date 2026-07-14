from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_PACK_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
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
    assert embedded["decision_file"] == decisions
    assert embedded["decision_file"]["training_authorized"] is False
    assert embedded["minimum_overall_score"] == 0.8
    assert embedded["minimum_dimension_scores"]["visual_design"] == 0.7
    assert embedded["minimum_dimension_scores"]["export_readiness"] == 0.8
    assert len(embedded["decision_file"]["decisions"]) == 3
    assert "fetch(" not in workspace
    assert "XMLHttpRequest" not in workspace


def test_workspace_escapes_html_and_script_content(tmp_path):
    attack = '</script><img src=x onerror="alert(1)">'
    _, result = _create_pack(tmp_path, reviewer=attack)

    workspace = Path(result["review_workspace_path"]).read_text(encoding="utf-8")
    embedded = _embedded_payload(workspace)

    assert attack not in workspace
    assert "\\u003c/script\\u003e" in workspace
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
