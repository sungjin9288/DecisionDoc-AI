from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.services.procurement_decision_package_service import (
    INCLUDED_ARTIFACT_ORDER,
    LOCAL_DEMO_EXPECTED_PACKAGE_PATH,
    NON_AUTHORIZATION_MARKER,
    PROCUREMENT_REVIEW_NAME,
    load_json,
    render_procurement_review_workspace,
    validate_procurement_review_text,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE_PATH = ROOT / LOCAL_DEMO_EXPECTED_PACKAGE_PATH


def _package_doc() -> dict[str, object]:
    return load_json(EXPECTED_PACKAGE_PATH)


def test_renders_complete_read_only_review_workspace() -> None:
    package_doc = _package_doc()

    review_html = render_procurement_review_workspace(package_doc)

    assert review_html.startswith("<!doctype html>")
    assert 'data-procurement-review-workspace' in review_html
    assert 'data-package-id="local-procurement-demo-001-package"' in review_html
    assert "CONDITIONAL_GO" in review_html
    assert NON_AUTHORIZATION_MARKER in review_html
    assert "<script" not in review_html.lower()
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        assert artifact_name in review_html


def test_marks_workspace_as_current_artifact_and_links_sibling_artifacts() -> None:
    review_html = render_procurement_review_workspace(_package_doc())

    assert f"<span>{PROCUREMENT_REVIEW_NAME}</span>" in review_html
    assert 'aria-current="page"' in review_html
    assert 'href="decision_package.json"' in review_html
    assert 'href="pending_signoff.json"' in review_html
    assert f'href="{PROCUREMENT_REVIEW_NAME}"' not in review_html


def test_escapes_package_content_in_html() -> None:
    package_doc = deepcopy(_package_doc())
    package_doc["package"]["opportunity_ref"]["title"] = '<script>alert("x")</script>'
    package_doc["package"]["recommendation_reason"] = '<img src=x onerror="alert(1)">'

    review_html = render_procurement_review_workspace(package_doc)

    assert '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;' in review_html
    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;' in review_html
    assert '<script>alert("x")</script>' not in review_html
    assert '<img src=x onerror="alert(1)">' not in review_html


def test_validator_rejects_missing_boundary_and_scripts() -> None:
    package_doc = _package_doc()
    package = package_doc["package"]
    review_html = render_procurement_review_workspace(package_doc)

    validate_procurement_review_text(review_html, package=package)

    broken_boundary = review_html.replace(
        package["reviewer_handoff"]["non_authorization_note"],
        "boundary removed",
    )
    with pytest.raises(ValueError, match="missing review markers"):
        validate_procurement_review_text(broken_boundary, package=package)

    with pytest.raises(ValueError, match="must remain script-free"):
        validate_procurement_review_text(
            review_html.replace("</body>", "<script></script></body>"),
            package=package,
        )
