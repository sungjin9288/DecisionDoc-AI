import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import is_enabled
from app.observability.logging import log_event
from app.ops.investigation_helpers import _env_int, _iso_utc, _tail_lines
from app.ops.report_history import (
    build_post_deploy_report_detail_payload,
    build_post_deploy_reports_payload,
    get_default_post_deploy_report_dir,
)

logger = logging.getLogger("decisiondoc.ops")


class PostDeployMixin:
    """Post-deploy report reading and on-demand post-deploy check execution for OpsInvestigationService."""

    def read_post_deploy_reports(
        self,
        *,
        limit: int,
        latest: bool,
    ) -> dict[str, Any]:
        return build_post_deploy_reports_payload(
            report_dir=get_default_post_deploy_report_dir(),
            limit=limit,
            latest=latest,
        )

    def read_post_deploy_report(
        self,
        *,
        report_file: str,
    ) -> dict[str, Any]:
        return build_post_deploy_report_detail_payload(
            report_dir=get_default_post_deploy_report_dir(),
            report_file=report_file,
        )

    def run_post_deploy_check(
        self,
        *,
        skip_smoke: bool,
    ) -> dict[str, Any]:
        if not is_enabled(os.getenv("DECISIONDOC_OPS_ALLOW_POST_DEPLOY_RUN", "0")):
            raise PermissionError("Post-deploy run is disabled.")
        repo_root = Path(__file__).resolve().parents[2]
        env_file = os.getenv("DECISIONDOC_OPS_POST_DEPLOY_ENV_FILE", "").strip()
        resolved_env_file = Path(env_file).expanduser() if env_file else repo_root / ".env.prod"
        report_dir = os.getenv("DECISIONDOC_POST_DEPLOY_REPORT_DIR", "").strip()
        resolved_report_dir = (
            Path(report_dir).expanduser() if report_dir else get_default_post_deploy_report_dir()
        )
        timeout_seconds = _env_int("DECISIONDOC_OPS_POST_DEPLOY_TIMEOUT_SECONDS", 900)
        command = [
            sys.executable,
            "scripts/post_deploy_check.py",
            "--env-file",
            str(resolved_env_file),
            "--report-dir",
            str(resolved_report_dir),
        ]
        if skip_smoke:
            command.append("--skip-smoke")

        run_id = uuid4().hex
        started_at = self._now()
        exit_code: int | None = None
        status = "unknown"
        stdout_tail: list[str] = []
        stderr_tail: list[str] = []
        try:
            completed = subprocess.run(
                command,
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
            exit_code = completed.returncode
            stdout_tail = _tail_lines(completed.stdout)
            stderr_tail = _tail_lines(completed.stderr)
            status = "passed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            stdout_tail = _tail_lines(exc.stdout or "")
            stderr_tail = _tail_lines(exc.stderr or "")
            status = "timeout"
        finished_at = self._now()
        report_file = None
        report_path = None
        try:
            summary = build_post_deploy_reports_payload(
                report_dir=resolved_report_dir,
                limit=1,
                latest=True,
            )
            report_file = str(summary.get("latest_report") or "").strip() or None
            if report_file:
                report_path = str(resolved_report_dir / report_file)
        except Exception:
            report_file = None
            report_path = None

        log_event(logger, {
            "event": "ops.post_deploy.run.completed",
            "run_id": run_id,
            "status": status,
            "exit_code": exit_code,
            "skip_smoke": skip_smoke,
            "started_at": _iso_utc(started_at),
            "finished_at": _iso_utc(finished_at),
        })

        return {
            "run_id": run_id,
            "status": status,
            "exit_code": exit_code,
            "started_at": _iso_utc(started_at),
            "finished_at": _iso_utc(finished_at),
            "report_dir": str(resolved_report_dir),
            "report_file": report_file,
            "report_path": report_path,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "command": " ".join(command),
        }
