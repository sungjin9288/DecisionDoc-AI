"""Agent-authored local generation: brief parity, authored pipeline and errors."""

from copy import deepcopy

from fastapi.testclient import TestClient

from app.bundle_catalog.registry import get_bundle_spec
from app.domain.schema import SCHEMA_VERSION, build_bundle_prompt
from app.providers.mock_provider import MockProvider
from app.services.auth_service import create_access_token

REQUEST = {
    "title": "[합성] 문서관리시스템 고도화 제안",
    "goal": "결재 완료 문서를 자동 보관하고 검색 시간을 줄인다",
    "context": "합성 UAT 자료. 사업 기간은 착수 후 6개월이고 예산은 1억 원(가상)이다.",
    "bundle_type": "proposal_kr",
}


class PromptCapturingMockProvider(MockProvider):
    def __init__(self, captured: dict) -> None:
        super().__init__()
        self.captured = captured

    def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
        self.captured["prompt"] = build_bundle_prompt(
            requirements, schema_version, bundle_spec, feedback_hints=feedback_hints
        )
        self.captured["calls"] = self.captured.get("calls", 0) + 1
        return super().generate_bundle(
            requirements,
            schema_version=schema_version,
            request_id=request_id,
            bundle_spec=bundle_spec,
            feedback_hints=feedback_hints,
        )


def _client(tmp_path, monkeypatch, captured: dict) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    for name in ("DECISIONDOC_PROVIDER_GENERATION", "DECISIONDOC_PROVIDER_ATTACHMENT", "DECISIONDOC_PROVIDER_VISUAL"):
        monkeypatch.setenv(name, "")
    import app.main as main_module

    monkeypatch.setattr(main_module, "get_provider", lambda: PromptCapturingMockProvider(captured))
    return TestClient(main_module.create_app())


def _admin_headers() -> dict[str, str]:
    token = create_access_token(user_id="author", tenant_id="system", role="admin", username="author")
    return {"Authorization": f"Bearer {token}"}


def _valid_bundle() -> dict:
    spec = get_bundle_spec("proposal_kr")
    return MockProvider().generate_bundle(
        dict(REQUEST), schema_version=SCHEMA_VERSION, request_id="fixture", bundle_spec=spec
    )


def _history_count(client: TestClient) -> int:
    response = client.get("/history", headers=_admin_headers())
    assert response.status_code == 200
    return response.json()["count"]


def test_brief_matches_the_prompt_the_provider_path_builds(tmp_path, monkeypatch):
    captured: dict = {}
    client = _client(tmp_path, monkeypatch, captured)

    brief = client.post("/generate/authoring-brief", json=REQUEST, headers=_admin_headers())
    assert brief.status_code == 200, brief.text
    assert "calls" not in captured  # the brief never calls a provider

    generated = client.post("/generate", json=REQUEST, headers=_admin_headers())
    assert generated.status_code == 200, generated.text

    body = brief.json()
    assert body["prompt"] == captured["prompt"]
    assert body["bundle_type"] == "proposal_kr"
    assert body["doc_keys"] == list(get_bundle_spec("proposal_kr").doc_keys)
    assert body["json_schema"]["required"]


def test_authored_bundle_runs_pipeline_without_provider_or_cache(tmp_path, monkeypatch):
    captured: dict = {}
    client = _client(tmp_path, monkeypatch, captured)
    bundle = _valid_bundle()
    marker = "결재 완료 문서는 보존 등급에 따라 30일 안에 기록관으로 자동 이관한다."
    summary = bundle["business_understanding"]["executive_summary"]
    bundle["business_understanding"]["executive_summary"] = f"{summary} {marker}"

    response = client.post(
        "/generate/authored",
        json={"request": REQUEST, "bundle": bundle},
        headers=_admin_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "agent_authored"
    assert body["cache_hit"] is None
    assert [doc["doc_type"] for doc in body["docs"]] == list(get_bundle_spec("proposal_kr").doc_keys)
    assert any(marker in doc["markdown"] for doc in body["docs"])
    assert "calls" not in captured
    assert not any((tmp_path / "cache").rglob("*.json"))
    assert _history_count(client) == 1


def test_authored_bundle_links_to_project(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, {})
    project = client.post("/projects", json={"name": "[합성] 작성 연결", "fiscal_year": 2026}, headers=_admin_headers())
    assert project.status_code == 200, project.text
    project_id = project.json()["project_id"]

    response = client.post(
        "/generate/authored",
        json={"request": {**REQUEST, "project_id": project_id}, "bundle": _valid_bundle()},
        headers=_admin_headers(),
    )

    assert response.status_code == 200, response.text
    document_id = response.json()["project_document_id"]
    assert document_id
    detail = client.get(f"/projects/{project_id}", headers=_admin_headers()).json()
    documents = detail.get("documents", detail.get("project", {}).get("documents", []))
    assert [doc["doc_id"] for doc in documents] == [document_id]


def test_invalid_authored_bundle_returns_reason_and_writes_nothing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, {})
    project_id = client.post(
        "/projects", json={"name": "[합성] 실패 확인", "fiscal_year": 2026}, headers=_admin_headers()
    ).json()["project_id"]
    bundle = deepcopy(_valid_bundle())
    missing = next(iter(bundle))
    del bundle[missing]

    response = client.post(
        "/generate/authored",
        json={"request": {**REQUEST, "project_id": project_id}, "bundle": bundle},
        headers=_admin_headers(),
    )

    assert response.status_code == 422
    detail = response.json().get("detail", response.json())
    assert detail["code"] == "AUTHORED_BUNDLE_INVALID"
    assert detail["message"] and detail["errors"]
    assert _history_count(client) == 0
    project = client.get(f"/projects/{project_id}", headers=_admin_headers()).json()
    assert not project.get("documents", project.get("project", {}).get("documents", []))


def test_authored_request_rejects_unknown_fields(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, {})

    response = client.post(
        "/generate/authored",
        json={"request": REQUEST, "bundle": _valid_bundle(), "provider": "openai"},
        headers=_admin_headers(),
    )

    assert response.status_code == 422
