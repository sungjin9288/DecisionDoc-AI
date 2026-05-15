#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("artifact root must be an object")
    return payload


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a DecisionDoc report quality correction artifact.")
    parser.add_argument("artifact", type=Path, help="Path to correction artifact JSON.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable validation result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.artifact)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "ok": False,
            "ready_for_learning": False,
            "errors": [str(exc)],
            "warnings": [],
            "artifact_id": None,
            "schema_version": None,
        }
    else:
        result = validate_correction_artifact(payload)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality correction artifact validated")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        if result["artifact_id"]:
            print(f"artifact_id={result['artifact_id']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality correction artifact validation failed")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
