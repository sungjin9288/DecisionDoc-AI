from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_summary_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "procurement_eval_summary.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_procurement_eval_summary", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_summary_reports_distribution_from_fixture():
    summary = _load_summary_module()
    cases = summary.load_cases(summary.DEFAULT_FIXTURE_PATH)
    report = summary.build_summary(cases)

    assert report["fixture_count"] >= 12
    assert report["recommendation_counts"]["GO"] >= 3
    assert report["recommendation_counts"]["CONDITIONAL_GO"] >= 4
    assert report["recommendation_counts"]["NO_GO"] >= 3
    assert "domain" in report["slice_dimensions"]
    assert "ai" in report["slice_dimensions"]["domain"]
    assert "security" in report["slice_dimensions"]["domain"]
    assert report["hard_fail_case_ids"]
    assert report["sparse_case_ids"]


def test_write_reports_emits_json_and_markdown(tmp_path):
    summary = _load_summary_module()
    cases = summary.load_cases(summary.DEFAULT_FIXTURE_PATH)
    report = summary.build_summary(cases)

    json_path, md_path = summary.write_reports(
        summary=report,
        fixture_path=summary.DEFAULT_FIXTURE_PATH,
        out_dir=tmp_path,
    )

    assert json_path.exists()
    assert md_path.exists()

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert saved["fixture_count"] == report["fixture_count"]
    assert "# Procurement Eval Summary" in markdown
    assert "Recommendation distribution" in markdown
    assert "`GO`" in markdown
