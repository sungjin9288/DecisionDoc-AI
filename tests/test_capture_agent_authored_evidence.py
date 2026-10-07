"""Session-authored evidence: replay the tracked bundle and check the receipt contract."""
from __future__ import annotations

import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.capture_agent_authored_evidence import (
    DEFAULT_RECEIPT_PATH,
    REPO_ROOT,
    authored_probes,
    capture_agent_authored_evidence,
    validate_receipt,
)


def _capture(tmp_path: Path) -> dict:
    environment_before = dict(os.environ)
    # TestClient runs its own event loop; keep it off the pytest-playwright loop.
    with ThreadPoolExecutor(max_workers=1) as executor:
        receipt = executor.submit(
            capture_agent_authored_evidence,
            markdown_dir=tmp_path / "markdown",
            screenshot_dir=tmp_path / "screenshots",
            receipt_path=tmp_path / "receipt.json",
            previews=False,
        ).result()
    assert dict(os.environ) == environment_before
    return receipt


def test_replay_keeps_every_authored_sentence_and_exports_all_formats(tmp_path: Path) -> None:
    receipt = _capture(tmp_path)

    assert receipt["provider"] == "agent_authored"
    assert receipt["authored_text"]["probes"] > 0
    assert receipt["authored_text"]["missing"] == []
    assert receipt["exports"]["pdf"]["pages"] > 0
    assert receipt["exports"]["pptx"]["slides"] > 0
    assert sorted(path.name for path in (tmp_path / "markdown").iterdir()) == [
        f"{doc_type}.md" for doc_type in receipt["doc_types"]
    ]
    assert json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8")) == receipt
    assert not list(tmp_path.rglob("*.pdf")) and not list(tmp_path.rglob("*.docx"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provider", "mock", "agent_authored"),
        ("authored_text", {"probes": 3, "survived": 2, "missing": ["x"]}, "did not survive"),
        ("exports_tracked", True, "must not be tracked"),
    ],
)
def test_receipt_validation_rejects_a_non_authored_run(field: str, value: object, message: str) -> None:
    receipt = json.loads(DEFAULT_RECEIPT_PATH.read_text(encoding="utf-8"))
    tampered = copy.deepcopy(receipt)
    tampered[field] = value

    with pytest.raises(ValueError, match=message):
        validate_receipt(tampered)


def test_tracked_receipt_points_at_tracked_evidence() -> None:
    receipt = json.loads(DEFAULT_RECEIPT_PATH.read_text(encoding="utf-8"))
    validate_receipt(receipt)

    referenced = [*receipt["markdown"], *receipt["previews"].values(), *receipt["inputs"].values()]
    for relative in referenced:
        if relative.endswith((".md", ".png", ".json")):
            assert (REPO_ROOT / relative).is_file(), relative


def test_probes_ignore_short_generic_strings() -> None:
    bundle = {"doc": {"title": "짧은 제목", "items": ["가" * 25, {"note": "나" * 30}]}}

    assert authored_probes(bundle) == ["가" * 25, "나" * 30]
