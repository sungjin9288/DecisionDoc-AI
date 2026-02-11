from collections import Counter
from typing import Any


def compute_heuristic_score(rendered: dict[str, str], metrics: dict[str, Any]) -> dict[str, Any]:
    score = 100.0
    reasons: list[str] = []

    banned_count = int(metrics.get("banned_token_violations", 0))
    if banned_count > 0:
        penalty = min(60, 30 * banned_count)
        score -= penalty
        reasons.append(f"banned_token_violations={banned_count}")

    coverage = metrics.get("required_sections_coverage", {})
    for doc_type, ratio in coverage.items():
        deficit = max(0.0, 1.0 - float(ratio))
        if deficit > 0:
            penalty = min(40.0, deficit * 40.0)
            score -= penalty
            reasons.append(f"{doc_type}_coverage={float(ratio):.2f}")

    lengths = metrics.get("length_chars", {})
    total_chars = int(lengths.get("total", 0))
    if total_chars < 3000:
        score -= 30
        reasons.append("total_chars_below_3000")

    for doc_type, value in lengths.items():
        if doc_type == "total":
            continue
        doc_len = int(value)
        if doc_len < 600:
            score -= 10
            reasons.append(f"{doc_type}_chars_below_600")

    for doc_type, text in rendered.items():
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        repeated = any(count >= 3 for count in Counter(lines).values())
        if repeated:
            score -= 10
            reasons.append(f"repetition_detected:{doc_type}")

    if coverage and all(float(v) >= 0.95 for v in coverage.values()) and total_chars >= 8000:
        score += 5
        reasons.append("high_coverage_and_length_bonus")

    bounded = max(0, min(100, int(round(score))))
    return {"score": bounded, "reasons": reasons}
