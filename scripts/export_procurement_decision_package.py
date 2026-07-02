from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    build_export_package_failure_result,
    export_project_decision_package,
)


def _emit_result(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, indent=2))
    return exit_code


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a project-scoped procurement decision package."
    )
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", "data")))
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--reviewer-owner", default="executive-reviewer")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = export_project_decision_package(
            data_dir=args.data_dir,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            out_dir=args.out_dir,
            reviewer_owner=args.reviewer_owner,
        )
    except Exception as exc:
        result = build_export_package_failure_result(
            data_dir=args.data_dir,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            out_dir=args.out_dir,
            exc=exc,
        )
        return _emit_result(result, exit_code=1)

    return _emit_result(result, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
