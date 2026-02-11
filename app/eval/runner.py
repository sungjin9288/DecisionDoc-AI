import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.eval.config import EVAL_DOC_TYPES, EVAL_VERSION
from app.eval.metrics import evaluate_fixture
from app.providers.factory import get_provider
from app.schemas import GenerateRequest
from app.services.generation_service import GenerationService


def load_fixture_payloads(fixtures_dir: Path, fixture_paths: list[Path] | None = None) -> list[tuple[str, dict[str, Any]]]:
    targets = fixture_paths if fixture_paths is not None else sorted(fixtures_dir.glob("*.json"))
    loaded: list[tuple[str, dict[str, Any]]] = []
    for path in targets:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixture_id = path.stem
        loaded.append((fixture_id, payload))
    return loaded


def _sanitize_payload_for_eval(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    sanitized["doc_types"] = EVAL_DOC_TYPES
    return sanitized


def _render_markdown_report(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Eval Report")
    lines.append("")
    lines.append(f"- eval_version: `{report['eval_version']}`")
    lines.append(f"- template_version: `{report['template_version']}`")
    lines.append(f"- provider: `{report['provider']}`")
    lines.append(f"- generated_at: `{report['generated_at']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| fixtures | pass_count | fail_count | avg_total_chars |")
    lines.append("| ---: | ---: | ---: | ---: |")
    summary = report["summary"]
    lines.append(
        f"| {summary['fixtures']} | {summary['pass_count']} | {summary['fail_count']} | {summary['avg_total_chars']} |"
    )
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    failures = [row for row in report["results"] if not row["pass"]]
    if not failures:
        lines.append("- None")
    else:
        for row in failures:
            lines.append(f"- `{row['fixture_id']}`: {', '.join(row['errors'])}")
    lines.append("")
    return "\n".join(lines)


def run_eval(
    *,
    eval_version: str = EVAL_VERSION,
    template_version: str = "v1",
    out_dir: Path = Path("reports/eval/v1"),
    fixtures_dir: Path = Path("tests/fixtures"),
    fixture_paths: list[Path] | None = None,
    data_dir: Path = Path("data"),
    fail_on_error: bool = True,
) -> tuple[dict[str, Any], int]:
    os.environ["DECISIONDOC_PROVIDER"] = "mock"
    os.environ["DECISIONDOC_TEMPLATE_VERSION"] = template_version

    template_dir = Path("app/templates") / template_version
    service = GenerationService(provider_factory=get_provider, template_dir=template_dir, data_dir=data_dir)

    results: list[dict[str, Any]] = []
    for fixture_id, payload in load_fixture_payloads(fixtures_dir, fixture_paths):
        request_payload = _sanitize_payload_for_eval(payload)
        req = GenerateRequest(**request_payload)
        request_id = f"eval-{fixture_id}"
        generated = service.generate_documents(req, request_id=request_id)
        docs = generated["docs"]
        metrics = evaluate_fixture(docs)

        row = {
            "fixture_id": fixture_id,
            "pass": metrics["pass"],
            "validator_pass": metrics["validator_pass"],
            "lint_pass": metrics["lint_pass"],
            "required_sections_coverage": metrics["required_sections_coverage"],
            "banned_token_violations": metrics["banned_token_violations"],
            "length_chars": metrics["length_chars"],
            "errors": metrics["errors"],
        }
        results.append(row)

    pass_count = sum(1 for row in results if row["pass"])
    fail_count = len(results) - pass_count
    avg_total_chars = int(round(sum(row["length_chars"]["total"] for row in results) / len(results))) if results else 0

    report = {
        "eval_version": eval_version,
        "template_version": template_version,
        "provider": "mock",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "fixtures": len(results),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "avg_total_chars": avg_total_chars,
        },
        "results": results,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "eval_report.md").write_text(_render_markdown_report(report), encoding="utf-8")

    exit_code = 1 if (fail_on_error and fail_count > 0) else 0
    return report, exit_code
