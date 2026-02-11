import json
from pathlib import Path

from app.eval.runner import run_eval


def test_eval_runner_generates_reports_for_subset(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")

    fixture_a = tmp_path / "fixture_a.json"
    fixture_b = tmp_path / "fixture_b.json"
    fixture_a.write_text(json.dumps({"title": "Eval A", "goal": "Eval A goal"}), encoding="utf-8")
    fixture_b.write_text(
        json.dumps(
            {
                "title": "Eval B",
                "goal": "Eval B goal",
                "context": "SUPER_SECRET_DO_NOT_LOG",
                "constraints": "SUPER_SECRET_DO_NOT_LOG",
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    report, exit_code = run_eval(
        template_version="v1",
        out_dir=out_dir,
        fixtures_dir=tmp_path,
        fixture_paths=[fixture_a, fixture_b],
        data_dir=tmp_path / "data",
        fail_on_error=True,
    )

    assert exit_code == 0
    assert report["summary"]["fixtures"] == 2
    assert (out_dir / "eval_report.json").exists()
    assert (out_dir / "eval_report.md").exists()

    saved_json = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert {"eval_version", "template_version", "provider", "summary", "results"} <= set(saved_json.keys())

    serialized = (out_dir / "eval_report.json").read_text(encoding="utf-8") + "\n" + (
        out_dir / "eval_report.md"
    ).read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in serialized
    assert "GEMINI_API_KEY" not in serialized
    assert "SUPER_SECRET_DO_NOT_LOG" not in serialized
