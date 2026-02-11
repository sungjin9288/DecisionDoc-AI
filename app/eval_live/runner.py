import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.eval.config import EVAL_DOC_TYPES
from app.eval.heuristics import compute_heuristic_score
from app.eval.metrics import evaluate_fixture
from app.eval.runner import load_fixture_payloads
from app.eval_live.fixtureset import REPRESENTATIVE_FIXTURES
from app.providers.factory import get_provider
from app.schemas import GenerateRequest
from app.services.generation_service import GenerationService

LIVE_PROVIDERS = ["openai", "gemini"]


def _resolve_fixture_paths(fixtures_dir: Path) -> list[Path]:
    paths = []
    for fixture_id in REPRESENTATIVE_FIXTURES:
        path = fixtures_dir / f"{fixture_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing fixture for live eval: {path}")
        paths.append(path)
    return paths


def _build_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:6]
    return f"{ts}-{suffix}"


def _summary_for_provider(rows: list[dict]) -> dict:
    if not rows:
        return {
            "fixtures": 0,
            "avg_score": 0,
            "avg_total_chars": 0,
            "avg_coverage": 0.0,
            "total_banned_violations": 0,
            "fail_count": 0,
        }
    avg_score = round(sum(r["heuristic"]["score"] for r in rows) / len(rows), 2)
    avg_total = int(round(sum(r["length_chars"]["total"] for r in rows) / len(rows)))
    avg_cov = round(
        sum(sum(r["required_sections_coverage"].values()) / len(r["required_sections_coverage"]) for r in rows)
        / len(rows),
        4,
    )
    total_banned_violations = sum(int(r.get("banned_token_violations", 0)) for r in rows)
    fail_count = sum(1 for r in rows if (not r["pass"]) or r.get("provider_error"))
    return {
        "fixtures": len(rows),
        "avg_score": avg_score,
        "avg_total_chars": avg_total,
        "avg_coverage": avg_cov,
        "total_banned_violations": total_banned_violations,
        "fail_count": fail_count,
    }


def _pick_top_reasons(row: dict) -> list[str]:
    reasons = row.get("heuristic", {}).get("reasons", [])
    if not reasons and row.get("errors"):
        reasons = row["errors"]
    return [str(r) for r in reasons[:2]]


def _winner_for_fixture(openai_row: dict, gemini_row: dict) -> str:
    openai_pass = bool(openai_row.get("pass", False)) and not bool(openai_row.get("provider_error", False))
    gemini_pass = bool(gemini_row.get("pass", False)) and not bool(gemini_row.get("provider_error", False))
    if openai_pass != gemini_pass:
        return "openai" if openai_pass else "gemini"
    openai_score = int(openai_row.get("heuristic", {}).get("score", 0))
    gemini_score = int(gemini_row.get("heuristic", {}).get("score", 0))
    if openai_score > gemini_score:
        return "openai"
    if gemini_score > openai_score:
        return "gemini"
    return "tie"


def build_live_report(
    *,
    run_id: str,
    template_version: str,
    providers_result: dict[str, list[dict]],
) -> dict:
    openai_map = {r["fixture_id"]: r for r in providers_result.get("openai", [])}
    gemini_map = {r["fixture_id"]: r for r in providers_result.get("gemini", [])}

    comparison_rows: list[dict] = []
    wins = {"openai": 0, "gemini": 0, "tie": 0}

    for fixture_id in REPRESENTATIVE_FIXTURES:
        openai_row = openai_map.get(fixture_id, {"heuristic": {"score": 0}, "errors": ["missing_result"], "pass": False})
        gemini_row = gemini_map.get(fixture_id, {"heuristic": {"score": 0}, "errors": ["missing_result"], "pass": False})
        openai_score = int(openai_row.get("heuristic", {}).get("score", 0))
        gemini_score = int(gemini_row.get("heuristic", {}).get("score", 0))
        score_delta = openai_score - gemini_score
        winner = _winner_for_fixture(openai_row, gemini_row)
        wins[winner] += 1

        comparison_rows.append(
            {
                "fixture_id": fixture_id,
                "openai_score": openai_score,
                "gemini_score": gemini_score,
                "score_delta": score_delta,
                "winner": winner,
                "top_reasons_openai": _pick_top_reasons(openai_row),
                "top_reasons_gemini": _pick_top_reasons(gemini_row),
            }
        )

    provider_summary = {provider: _summary_for_provider(rows) for provider, rows in providers_result.items()}
    for provider in LIVE_PROVIDERS:
        provider_summary.setdefault(
            provider,
            {
                "fixtures": 0,
                "avg_score": 0,
                "avg_total_chars": 0,
                "avg_coverage": 0.0,
                "total_banned_violations": 0,
                "fail_count": 0,
            },
        )
        provider_summary[provider]["wins"] = wins.get(provider, 0)

    return {
        "run_id": run_id,
        "template_version": template_version,
        "fixtures": REPRESENTATIVE_FIXTURES,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "providers": provider_summary,
            "wins": wins,
        },
        "providers": providers_result,
        "comparison": comparison_rows,
    }


def render_live_markdown(report: dict) -> str:
    lines = [
        "# Live Eval Report",
        "",
        f"- run_id: `{report['run_id']}`",
        f"- template_version: `{report['template_version']}`",
        f"- fixtures: `{', '.join(report['fixtures'])}`",
        f"- generated_at: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        "| provider | avg_score | avg_coverage | avg_total_chars | banned_violations | failures | wins |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for provider, data in report["summary"]["providers"].items():
        lines.append(
            f"| {provider} | {data['avg_score']} | {data['avg_coverage']} | {data['avg_total_chars']} | {data['total_banned_violations']} | {data['fail_count']} | {data.get('wins', 0)} |"
        )
    lines.extend(["", "## Per Fixture Comparison", "", "| fixture_id | openai_score | gemini_score | delta | winner | notes |", "| --- | ---: | ---: | ---: | --- | --- |"])
    for row in report["comparison"]:
        delta = row["score_delta"]
        delta_label = f"+{delta}" if delta > 0 else str(delta)
        notes = ", ".join((row.get("top_reasons_openai", []) + row.get("top_reasons_gemini", []))[:2]) or "-"
        lines.append(
            f"| {row['fixture_id']} | {row['openai_score']} | {row['gemini_score']} | {delta_label} | {row['winner']} | {notes} |"
        )
    return "\n".join(lines) + "\n"


def run_live_eval(
    *,
    template_version: str = "v1",
    out_dir: Path = Path("reports/eval-live"),
    fixtures_dir: Path = Path("tests/fixtures"),
    fail_on_error: bool = True,
) -> tuple[dict, int]:
    os.environ["DECISIONDOC_TEMPLATE_VERSION"] = template_version
    os.environ["DECISIONDOC_CACHE_ENABLED"] = "0"

    fixture_paths = _resolve_fixture_paths(fixtures_dir)
    fixture_payloads = load_fixture_payloads(fixtures_dir, fixture_paths)
    template_dir = Path("app/templates") / template_version
    run_id = _build_run_id()

    providers_result: dict[str, list[dict]] = {}
    any_provider_errors = False

    for provider in LIVE_PROVIDERS:
        os.environ["DECISIONDOC_PROVIDER"] = provider
        service = GenerationService(provider_factory=get_provider, template_dir=template_dir, data_dir=Path("data"))
        rows: list[dict] = []
        for fixture_id, payload in fixture_payloads:
            request_payload = dict(payload)
            request_payload["doc_types"] = EVAL_DOC_TYPES
            req = GenerateRequest(**request_payload)
            try:
                result = service.generate_documents(req, request_id=f"live-{provider}-{fixture_id}")
                docs = result["docs"]
                rendered = {d["doc_type"]: d["markdown"] for d in docs}
                metrics = evaluate_fixture(docs)
                heuristic = compute_heuristic_score(rendered, metrics)
                row = {
                    "fixture_id": fixture_id,
                    "provider_error": False,
                    "pass": metrics["pass"],
                    "validator_pass": metrics["validator_pass"],
                    "lint_pass": metrics["lint_pass"],
                    "required_sections_coverage": metrics["required_sections_coverage"],
                    "banned_token_violations": metrics["banned_token_violations"],
                    "length_chars": metrics["length_chars"],
                    "heuristic": heuristic,
                    "errors": metrics["errors"] + heuristic["reasons"],
                }
            except Exception:
                any_provider_errors = True
                row = {
                    "fixture_id": fixture_id,
                    "provider_error": True,
                    "pass": False,
                    "validator_pass": False,
                    "lint_pass": False,
                    "required_sections_coverage": {k: 0.0 for k in EVAL_DOC_TYPES},
                    "banned_token_violations": 0,
                    "length_chars": {**{k: 0 for k in EVAL_DOC_TYPES}, "total": 0},
                    "heuristic": {"score": 0, "reasons": ["provider_error"]},
                    "errors": ["provider_error"],
                }
            rows.append(row)
        providers_result[provider] = rows

    report = build_live_report(run_id=run_id, template_version=template_version, providers_result=providers_result)

    report_dir = out_dir / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report["report_dir"] = str(report_dir)
    (report_dir / "live_eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "live_eval_report.md").write_text(render_live_markdown(report), encoding="utf-8")

    fail_count = sum(data["fail_count"] for data in report["summary"]["providers"].values())
    exit_code = 1 if (fail_on_error and (any_provider_errors or fail_count > 0)) else 0
    return report, exit_code
