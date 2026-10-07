"""CLI authoring pinned to one procurement decision revision."""

from argparse import Namespace
import json

from app.bundle_catalog.registry import get_bundle_spec
from app.domain.schema import SCHEMA_VERSION
from app.providers.mock_provider import MockProvider
from scripts import decisiondoc_author as cli
from tests.test_procurement_generation_binding import HEADERS, _import, scope  # noqa: F401


def _bound_request(ctx, receipt) -> dict:
    return cli._build_request(Namespace(
        bundle="bid_decision_kr", title="입찰 판단", goal="선택한 공고만 근거로 판단한다",
        context="", context_file=None, constraints="", audience="",
        project_id=ctx.project, style_profile_id="",
        procurement_decision_id=receipt.decision_id, procurement_revision=receipt.decision_revision,
    ))


def test_brief_and_submit_stay_on_the_selected_decision(scope, tmp_path):  # noqa: F811
    scope.client.headers.update(HEADERS)
    _import(scope, "A", 0)
    receipt_b = _import(scope, "B", 1)
    request = _bound_request(scope, receipt_b)
    work_dir = tmp_path / "bid"

    brief = cli.write_brief(scope.client, request, work_dir).read_text(encoding="utf-8")
    assert "Only source B" in brief and "Only source A" not in brief

    bundle = MockProvider().generate_bundle(
        dict(request), schema_version=SCHEMA_VERSION, request_id="cli", bundle_spec=get_bundle_spec("bid_decision_kr")
    )
    (work_dir / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    summary = cli.submit(scope.client, work_dir, [])

    response = json.loads((work_dir / "response.json").read_text(encoding="utf-8"))
    binding = response["source_procurement_binding"]
    assert summary["provider"] == "agent_authored" and summary["project_document_id"]
    assert binding["decision_id"] == receipt_b.decision_id
    assert binding["decision_revision"] == receipt_b.decision_revision
    assert scope.calls == []  # no provider call on the authored path


def test_stale_revision_is_rejected_before_writing(scope, tmp_path):  # noqa: F811
    scope.client.headers.update(HEADERS)
    receipt_a = _import(scope, "A", 0)
    request = _bound_request(scope, receipt_a)
    request["expected_procurement_decision_revision"] = receipt_a.decision_revision + 1

    response = scope.client.post("/generate/authoring-brief", json=request)

    assert response.status_code == 409, response.text
