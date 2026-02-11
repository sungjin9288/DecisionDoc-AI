import argparse
import os
import sys
from pathlib import Path

from app.eval_live.runner import run_live_eval


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live provider comparison eval.")
    parser.add_argument("--template-version", default="v1")
    parser.add_argument("--out-dir", default="reports/eval-live")
    parser.add_argument("--fail-on-error", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def _validate_required_keys() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY for live eval.")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("Missing GEMINI_API_KEY for live eval.")


def _build_short_summary(report: dict) -> str:
    providers = report["summary"]["providers"]
    wins = report["summary"]["wins"]
    comparison = report["comparison"]
    biggest = max(comparison, key=lambda r: abs(int(r["score_delta"]))) if comparison else None
    biggest_label = (
        f"{biggest['fixture_id']} (delta {biggest['score_delta']:+d}, winner={biggest['winner']})" if biggest else "-"
    )
    lines = [
        "Live Eval Summary",
        f"run_id: {report['run_id']}",
        f"template_version: {report['template_version']}",
        f"fixtures: {', '.join(report['fixtures'])}",
        f"openai avg_score: {providers['openai']['avg_score']}",
        f"gemini avg_score: {providers['gemini']['avg_score']}",
        f"wins: openai={wins['openai']}, gemini={wins['gemini']}, tie={wins['tie']}",
        f"biggest_delta: {biggest_label}",
        f"artifact_dir: {report.get('report_dir', '-')}",
        "raw text/keys/model outputs are not stored in report.",
    ]
    return "\n".join(lines)


def _write_github_step_summary(report: dict) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    providers = report["summary"]["providers"]
    wins = report["summary"]["wins"]
    lines = [
        "## Live Eval Summary",
        "",
        f"- run_id: `{report['run_id']}`",
        f"- template_version: `{report['template_version']}`",
        f"- fixtures: `{', '.join(report['fixtures'])}`",
        f"- artifact_dir: `{report.get('report_dir', '-')}`",
        "",
        "| provider | avg_score | avg_coverage | avg_total_chars | fail_count | wins |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| openai | {providers['openai']['avg_score']} | {providers['openai']['avg_coverage']} | {providers['openai']['avg_total_chars']} | {providers['openai']['fail_count']} | {wins['openai']} |",
        f"| gemini | {providers['gemini']['avg_score']} | {providers['gemini']['avg_coverage']} | {providers['gemini']['avg_total_chars']} | {providers['gemini']['fail_count']} | {wins['gemini']} |",
        "",
    ]
    with Path(summary_path).open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    args = _parse_args()
    try:
        _validate_required_keys()
    except RuntimeError:
        return 1

    report, exit_code = run_live_eval(
        template_version=args.template_version,
        out_dir=Path(args.out_dir),
        fail_on_error=bool(args.fail_on_error),
    )
    print(_build_short_summary(report))
    _write_github_step_summary(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
