from app.eval.heuristics import compute_heuristic_score


def test_heuristic_score_is_deterministic_and_bounded():
    rendered = {
        "adr": "A\nB\nC\n",
        "onepager": "D\nE\nF\n",
        "eval_plan": "G\nH\nI\n",
        "ops_checklist": "J\nK\nL\n",
    }
    metrics = {
        "banned_token_violations": 0,
        "required_sections_coverage": {"adr": 1.0, "onepager": 1.0, "eval_plan": 1.0, "ops_checklist": 1.0},
        "length_chars": {"adr": 2500, "onepager": 2200, "eval_plan": 2100, "ops_checklist": 1800, "total": 8600},
    }

    first = compute_heuristic_score(rendered, metrics)
    second = compute_heuristic_score(rendered, metrics)
    assert first == second
    assert 0 <= first["score"] <= 100


def test_heuristic_penalties_trigger():
    rendered = {
        "adr": "repeat\nrepeat\nrepeat\n",
        "onepager": "TODO item\n",
        "eval_plan": "short\n",
        "ops_checklist": "tiny\n",
    }
    metrics = {
        "banned_token_violations": 2,
        "required_sections_coverage": {"adr": 0.5, "onepager": 0.7, "eval_plan": 0.8, "ops_checklist": 0.9},
        "length_chars": {"adr": 500, "onepager": 400, "eval_plan": 300, "ops_checklist": 200, "total": 1400},
    }
    result = compute_heuristic_score(rendered, metrics)
    assert 0 <= result["score"] <= 100
    assert result["score"] < 100
    assert result["reasons"]
