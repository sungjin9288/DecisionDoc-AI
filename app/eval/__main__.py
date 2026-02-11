import argparse
import sys
from pathlib import Path

from app.eval.config import EVAL_VERSION
from app.eval.runner import run_eval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DecisionDoc eval report generation.")
    parser.add_argument("--eval-version", default=EVAL_VERSION)
    parser.add_argument("--template-version", default="v1")
    parser.add_argument("--out-dir", default="reports/eval/v1")
    parser.add_argument("--fail-on-error", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _, exit_code = run_eval(
        eval_version=args.eval_version,
        template_version=args.template_version,
        out_dir=Path(args.out_dir),
        fail_on_error=bool(args.fail_on_error),
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
