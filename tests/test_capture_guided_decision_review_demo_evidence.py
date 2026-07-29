from __future__ import annotations

import copy
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from scripts.capture_guided_decision_review_demo_evidence import (
    capture_guided_review_demo_evidence,
    main,
    validate_guided_review_demo_receipt,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capture(tmp_path: Path):
    artifact_dir = tmp_path / "evidence"
    receipt_path = artifact_dir / "cli-logs" / "guided-review-demo.json"
    environment_before = dict(os.environ)
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(
            capture_guided_review_demo_evidence,
            artifact_dir=artifact_dir,
            receipt_path=receipt_path,
        ).result()
    assert dict(os.environ) == environment_before
    return result, artifact_dir, receipt_path


def test_guided_review_demo_receipt_rejects_unbound_hashes_and_unsafe_paths(
    tmp_path: Path,
) -> None:
    _, artifact_dir, receipt_path = _capture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validate_guided_review_demo_receipt(receipt, artifact_dir=artifact_dir)
    assert (
        main(
            [
                "--artifact-dir",
                str(artifact_dir),
                "--receipt-path",
                str(receipt_path),
                "--check-only",
            ]
        )
        == 0
    )

    arbitrary_hashes = copy.deepcopy(receipt)
    arbitrary_hashes["contracts"]["handoff_sha256"] = "a" * 64
    arbitrary_hashes["contracts"]["recheck_sha256"] = "b" * 64
    arbitrary_hashes["contracts"]["disposition_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="artifact"):
        validate_guided_review_demo_receipt(
            arbitrary_hashes,
            artifact_dir=artifact_dir,
        )

    unsafe_path = copy.deepcopy(receipt)
    unsafe_path["screenshots"]["guided_review"]["filename"] = "../review.png"
    with pytest.raises(ValueError, match="basename"):
        validate_guided_review_demo_receipt(unsafe_path, artifact_dir=artifact_dir)

    with pytest.raises(ValueError, match="external action"):
        validate_guided_review_demo_receipt(
            {
                **receipt,
                "excluded_external_actions": {
                    **receipt["excluded_external_actions"],
                    "provider_api_execution": True,
                },
            },
            artifact_dir=artifact_dir,
        )

    disposition_path = (
        artifact_dir
        / "cli-logs"
        / receipt["downloaded_receipts"]["disposition"]["filename"]
    )
    disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
    disposition["disposition_binding_sha256"] = "c" * 64
    disposition_path.write_text(
        json.dumps(disposition, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    nested_binding = copy.deepcopy(receipt)
    nested_binding["downloaded_receipts"]["disposition"].update(
        {
            "size_bytes": disposition_path.stat().st_size,
            "sha256": _sha256(disposition_path),
        }
    )
    nested_binding["contracts"]["disposition_sha256"] = _sha256(disposition_path)
    with pytest.raises(ValueError, match="disposition binding"):
        validate_guided_review_demo_receipt(nested_binding, artifact_dir=artifact_dir)


def test_guided_review_demo_capture_uses_local_shell_and_writes_valid_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "provider-key-must-not-be-recorded")
    result, artifact_dir, receipt_path = _capture(tmp_path)

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validate_guided_review_demo_receipt(receipt, artifact_dir=artifact_dir)

    assert result.browser_http_errors == []
    assert receipt["steps"] == [
        "project_created",
        "decision_evidence_map_loaded",
        "guided_review_rendered",
        "handoff_downloaded",
        "unchanged_recheck_downloaded",
        "acknowledged_unchanged_disposition_downloaded",
    ]
    assert receipt["browser_boundary"]["page_memory_only"] is True
    assert receipt["browser_boundary"]["disposition_receipt_persisted"] is False
    assert all(path.exists() for path in result.screenshots.values())
    assert receipt["stage_observations"] == {
        "Decision": "needs_attention",
        "Evidence": "needs_attention",
        "Review": "not_observed",
        "Documents": "not_observed",
    }
    assert "no persisted procurement review" in receipt["unobserved_stage_reason"]
    for binding in receipt["screenshots"].values():
        path = artifact_dir / "screenshots" / binding["filename"]
        assert binding["size_bytes"] == path.stat().st_size
        assert binding["sha256"] == _sha256(path)
    for binding in receipt["downloaded_receipts"].values():
        path = artifact_dir / "cli-logs" / binding["filename"]
        assert binding["size_bytes"] == path.stat().st_size
        assert binding["sha256"] == _sha256(path)
    receipt_text = receipt_path.read_text(encoding="utf-8")
    assert "127.0.0.1" not in receipt_text
    assert "password" not in receipt_text.lower()
    assert "access_token" not in receipt_text
    assert "provider-key-must-not-be-recorded" not in receipt_text


def test_guided_review_demo_capture_restores_environment_after_browser_failure(
    tmp_path: Path,
) -> None:
    @contextmanager
    def failing_playwright():
        raise RuntimeError("browser fixture failure")
        yield None

    environment_before = dict(os.environ)
    with pytest.raises(RuntimeError, match="browser fixture failure"):
        capture_guided_review_demo_evidence(
            artifact_dir=tmp_path / "evidence",
            receipt_path=tmp_path / "evidence" / "cli-logs" / "receipt.json",
            playwright_factory=failing_playwright,
        )
    assert dict(os.environ) == environment_before
