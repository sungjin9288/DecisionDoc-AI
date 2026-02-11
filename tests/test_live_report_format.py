from app.eval_live.runner import build_live_report, render_live_markdown


def _row(fixture_id: str, score: int, passed: bool = True):
    return {
        "fixture_id": fixture_id,
        "provider_error": False,
        "pass": passed,
        "validator_pass": passed,
        "lint_pass": passed,
        "required_sections_coverage": {"adr": 1.0, "onepager": 1.0, "eval_plan": 1.0, "ops_checklist": 1.0},
        "banned_token_violations": 0,
        "length_chars": {"adr": 2000, "onepager": 2000, "eval_plan": 2000, "ops_checklist": 2000, "total": 8000},
        "heuristic": {"score": score, "reasons": []},
        "errors": [],
    }


def test_live_report_json_and_md_format_contains_delta_winner_and_wins():
    providers_result = {
        "openai": [
            _row("01_normal_default_all", 90, True),
            _row("03_normal_full_fields", 80, True),
            _row("09_cost_constrained_1", 70, True),
        ],
        "gemini": [
            _row("01_normal_default_all", 85, True),
            _row("03_normal_full_fields", 80, True),
            _row("09_cost_constrained_1", 75, True),
        ],
    }

    report = build_live_report(run_id="r1", template_version="v1", providers_result=providers_result)
    assert "summary" in report
    assert "wins" in report["summary"]
    assert {"openai", "gemini", "tie"} <= set(report["summary"]["wins"].keys())
    assert report["comparison"]
    first = report["comparison"][0]
    assert {"fixture_id", "openai_score", "gemini_score", "score_delta", "winner"} <= set(first.keys())

    tie_row = [row for row in report["comparison"] if row["fixture_id"] == "03_normal_full_fields"][0]
    assert tie_row["score_delta"] == 0
    assert tie_row["winner"] == "tie"

    md = render_live_markdown(report)
    assert "delta" in md
    assert "winner" in md
    assert "| provider | avg_score |" in md
