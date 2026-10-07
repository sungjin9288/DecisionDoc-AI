"""Local authoring CLI against the real app with API-key authentication."""

import json
from argparse import Namespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bundle_catalog.registry import get_bundle_spec
from app.domain.schema import SCHEMA_VERSION
from app.providers.mock_provider import MockProvider
from scripts import decisiondoc_author as cli

API_KEY = "local-agent-test-key"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", API_KEY)
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    for name in ("DECISIONDOC_PROVIDER_GENERATION", "DECISIONDOC_PROVIDER_ATTACHMENT", "DECISIONDOC_PROVIDER_VISUAL"):
        monkeypatch.setenv(name, "")
    from app.main import create_app

    with TestClient(create_app(), headers={cli.API_KEY_HEADER: API_KEY}) as test_client:
        yield test_client


def _request() -> dict:
    args = Namespace(
        bundle="proposal_kr",
        title="[합성] 문서관리시스템 고도화 제안",
        goal="결재 완료 문서를 자동 보관한다",
        context="사업 기간은 6개월이다.",
        context_file=None,
        constraints="",
        audience="",
        project_id="",
        style_profile_id="",
    )
    return cli._build_request(args)


def _write_bundle(work_dir, request) -> None:
    bundle = MockProvider().generate_bundle(
        dict(request), schema_version=SCHEMA_VERSION, request_id="cli", bundle_spec=get_bundle_spec("proposal_kr")
    )
    (work_dir / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")


def test_brief_writes_prompt_request_and_schema(client, tmp_path):
    work_dir = tmp_path / "doc1"

    brief_path = cli.write_brief(client, _request(), work_dir)

    brief = brief_path.read_text(encoding="utf-8")
    assert "## 생성 프롬프트" in brief and "bundle.json" in brief
    assert json.loads((work_dir / "request.json").read_text(encoding="utf-8"))["bundle_type"] == "proposal_kr"
    assert json.loads((work_dir / "schema.json").read_text(encoding="utf-8"))["required"]


def test_submit_stores_and_exports_without_provider(client, tmp_path):
    work_dir = tmp_path / "doc1"
    request = _request()
    cli.write_brief(client, request, work_dir)
    _write_bundle(work_dir, request)

    summary = cli.submit(client, work_dir, ["docx", "hwpx", "pptx"])

    assert summary["provider"] == "agent_authored"
    suffixes = sorted(path.rsplit(".", 1)[-1] for path in summary["files"])
    assert suffixes.count("md") == len(get_bundle_spec("proposal_kr").doc_keys)
    assert {"docx", "hwpx", "pptx"} <= set(suffixes)
    assert all(Path(path).stat().st_size > 0 for path in summary["files"])
    assert json.loads((work_dir / "response.json").read_text(encoding="utf-8"))["provider"] == "agent_authored"


def test_submit_reports_rejection_reasons(client, tmp_path):
    work_dir = tmp_path / "doc1"
    request = _request()
    cli.write_brief(client, request, work_dir)
    (work_dir / "bundle.json").write_text(json.dumps({"business_understanding": "not an object"}), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        cli.submit(client, work_dir, [])

    assert "AUTHORED_BUNDLE_INVALID" in str(excinfo.value)
    assert not (work_dir / "response.json").exists()


def test_requests_without_agent_key_are_rejected(client):
    response = client.post("/generate/authoring-brief", json=_request(), headers={cli.API_KEY_HEADER: "wrong"})

    assert response.status_code == 401


def test_bundles_lists_registry_doc_keys():
    bundles = {item["id"]: item for item in cli.list_bundles()}

    assert bundles["proposal_kr"]["doc_keys"] == list(get_bundle_spec("proposal_kr").doc_keys)
