"""Tests for BundleSpec registry — validates all registered bundles."""

import pytest

from app.bundle_catalog.registry import BUNDLE_REGISTRY
from app.bundle_catalog.spec import BundleSpec, DocumentSpec


ALL_BUNDLE_IDS = sorted(BUNDLE_REGISTRY.keys())


@pytest.mark.parametrize("bundle_id", ALL_BUNDLE_IDS)
def test_bundle_has_required_fields(bundle_id):
    """Each BundleSpec must have all identity fields set."""
    spec = BUNDLE_REGISTRY[bundle_id]
    assert isinstance(spec, BundleSpec)
    assert spec.id == bundle_id
    assert spec.name_ko
    assert spec.name_en
    assert spec.description_ko
    assert spec.icon
    assert spec.prompt_language in ("ko", "en")


@pytest.mark.parametrize("bundle_id", ALL_BUNDLE_IDS)
def test_bundle_has_non_empty_docs(bundle_id):
    """Each BundleSpec must have at least one DocumentSpec."""
    spec = BUNDLE_REGISTRY[bundle_id]
    assert len(spec.docs) >= 1
    for doc in spec.docs:
        assert isinstance(doc, DocumentSpec)
        assert doc.key
        assert doc.template_file


@pytest.mark.parametrize("bundle_id", ALL_BUNDLE_IDS)
def test_bundle_json_schema_valid(bundle_id):
    """json_schema property must produce a valid JSON Schema dict."""
    spec = BUNDLE_REGISTRY[bundle_id]
    schema = spec.json_schema
    assert schema["type"] == "object"
    assert "required" in schema
    assert "properties" in schema
    assert set(schema["required"]) == set(schema["properties"].keys())


@pytest.mark.parametrize("bundle_id", ALL_BUNDLE_IDS)
def test_bundle_doc_keys_consistent(bundle_id):
    """doc_keys must match the keys in the docs list."""
    spec = BUNDLE_REGISTRY[bundle_id]
    assert spec.doc_keys == [d.key for d in spec.docs]


def test_bundle_registry_has_seventeen_builtins():
    """Registry must contain exactly 17 built-in bundles including bid_decision_kr."""
    # Auto bundles may be loaded at import time — filter to built-in only
    builtin_ids = {
        "tech_decision", "proposal_kr", "business_plan_kr", "edu_plan_kr",
        "meeting_minutes_kr", "project_report_kr", "contract_kr",
        "presentation_kr", "job_description_kr", "okr_plan_kr", "prd_kr",
        # 나라장터 특화 6종
        "bid_decision_kr",
        "rfp_analysis_kr", "performance_plan_kr", "completion_report_kr",
        "interim_report_kr", "task_order_kr",
    }
    assert builtin_ids.issubset(set(BUNDLE_REGISTRY.keys()))
    assert len([k for k in BUNDLE_REGISTRY if k in builtin_ids]) == 17


def test_academic_report_kr_removed():
    """academic_report_kr must not be in the registry (student bundle removed)."""
    assert "academic_report_kr" not in BUNDLE_REGISTRY


def test_new_enterprise_bundles_present():
    """New enterprise bundles must be registered with valid categories."""
    expected_categories = {
        "meeting_minutes_kr": "internal",
        "project_report_kr": "report",
        "contract_kr": "internal",
    }
    for bundle_id, expected_cat in expected_categories.items():
        assert bundle_id in BUNDLE_REGISTRY
        spec = BUNDLE_REGISTRY[bundle_id]
        assert spec.category == expected_cat, (
            f"{bundle_id}: expected category='{expected_cat}', got '{spec.category}'"
        )


def test_generate_request_doc_tone_field():
    """GenerateRequest must accept doc_tone field."""
    from app.schemas import GenerateRequest
    req = GenerateRequest(title="t", goal="g", doc_tone="concise")
    assert req.doc_tone == "concise"
    req_default = GenerateRequest(title="t", goal="g")
    assert req_default.doc_tone == "formal"
