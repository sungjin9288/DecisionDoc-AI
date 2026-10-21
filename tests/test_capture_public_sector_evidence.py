"""Public-sector evidence: the correct proposal passes and every planted mistake is caught."""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.capture_public_sector_evidence import (
    DEFAULT_RECEIPT_PATH,
    REPO_ROOT,
    capture_public_sector_evidence,
    validate_receipt,
)


@pytest.fixture(scope="module")
def receipt(tmp_path_factory: pytest.TempPathFactory) -> dict:
    out = tmp_path_factory.mktemp("public-sector-evidence")
    # PDF export runs its own event loop; keep it off the pytest-playwright loop.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            capture_public_sector_evidence,
            markdown_dir=out / "md",
            screenshot=out / "page1.png",
            receipt_path=out / "receipt.json",
            previews=False,
        ).result()


def test_rfp_is_read_back_from_hwpx_without_noise(receipt: dict) -> None:
    assert receipt["rfp"]["format"] == "hwpx"
    assert receipt["rfp"]["requirement_candidates"] == ["PSR-001", "SER-001", "SER-002", "SFR-001", "SFR-002", "SFR-003"]
    assert receipt["rfp"]["prefix_mentions"]["ISO"] == 1


def test_correct_proposal_passes_with_confirmed_pages_and_no_tool_traces(receipt: dict) -> None:
    clean = receipt["clean"]

    assert clean["proposal_check"]["passed"] and clean["requirements"]["covered"] == 6
    assert all(p["basis"] == "본문 확인" for row in clean["crosswalk"] for p in row["placements"])
    assert clean["pdf_package_cover"] is False and clean["pdf_metadata_names_tool"] is False
    assert set(clean["exports"]) == {"pdf", "hwpx", "docx"}


def test_planted_mistakes_are_all_detected(receipt: dict) -> None:
    detected = receipt["flawed"]["detected"]

    # The typo SFR-004 also leaves SFR-002 unanswered.
    assert detected["missing_requirements"] == ["SFR-002", "PSR-001"]
    assert detected["unknown_requirements"] == ["SFR-004"]
    assert detected["identifier_exposed"] is True
    assert detected["date_findings"] == ["날짜 '2026년 11월 2일'"]


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("clean", "pdf_package_cover"), True, "DecisionDoc cover"),
        (("flawed", "detected", "identifier_exposed"), False, "not detected"),
        (("flawed", "detected", "unknown_requirements"), [], "not detected"),
    ],
)
def test_receipt_validation_rejects_a_weaker_run(receipt: dict, path: tuple, value: object, message: str) -> None:
    tampered = copy.deepcopy(receipt)
    target = tampered
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=message):
        validate_receipt(tampered)


def test_tracked_receipt_is_valid_and_points_at_tracked_files() -> None:
    tracked = json.loads(DEFAULT_RECEIPT_PATH.read_text(encoding="utf-8"))
    validate_receipt(tracked)

    for relative in [*tracked["inputs"].values(), *tracked["tables"], tracked["preview"]]:
        assert (REPO_ROOT / relative).is_file(), relative
    assert Path(REPO_ROOT / tracked["tables"][0]).read_text(encoding="utf-8").count("| 대응 |") == 6
