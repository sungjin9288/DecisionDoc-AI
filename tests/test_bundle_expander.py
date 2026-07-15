"""tests/test_bundle_expander.py — Bundle auto-expansion 단위·통합 테스트.

Coverage:
  - RequestPatternStore: record, get_unmatched, get_all, clear_unmatched, limit
  - BundleAutoExpander: below threshold → None, confidence < 0.7 → None, success
  - AutoRegistry: load_auto_bundles from valid registry.json
  - Admin API endpoints: list, expand, delete, request-patterns
"""
from __future__ import annotations

import json
import threading

import pytest


# ── 테스트 격리 픽스처 ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_mock_bundle_from_registry():
    """각 테스트 전후로 mock_auto_bundle_kr을 BUNDLE_REGISTRY에서 제거.

    test_bundle_expander_success 가 reload_auto_bundles() 를 호출하면
    mock_auto_bundle_kr 이 모듈-수준 BUNDLE_REGISTRY에 추가된다.
    이후 테스트가 충돌 검사에 걸리지 않도록 정리한다.
    """
    from app.bundle_catalog.registry import BUNDLE_REGISTRY
    BUNDLE_REGISTRY.pop("mock_auto_bundle_kr", None)
    yield
    BUNDLE_REGISTRY.pop("mock_auto_bundle_kr", None)


# ── RequestPatternStore 단위 테스트 ─────────────────────────────────────────


def test_pattern_store_record_and_get_all(tmp_path):
    """record_request 후 get_all이 레코드를 반환하는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore

    store = RequestPatternStore(tmp_path, tenant_id="system")
    rid = store.record_request("AI 문서 자동화", bundle_id="tech_decision", matched=True)

    assert isinstance(rid, str) and len(rid) == 36  # UUID

    all_records = store.get_all()
    assert len(all_records) == 1
    assert all_records[0]["raw_input"] == "AI 문서 자동화"
    assert all_records[0]["matched"] is True
    assert all_records[0]["bundle_id"] == "tech_decision"
    assert all_records[0]["tenant_id"] == "system"


def test_pattern_store_is_tenant_bound_and_preserves_foreign_drift(tmp_path):
    """Tenant-owned reads and clear operations ignore explicit foreign records."""
    from app.storage.request_pattern_store import RequestPatternStore

    store_a = RequestPatternStore(tmp_path, tenant_id="tenant_a")
    store_b = RequestPatternStore(tmp_path, tenant_id="tenant_b")
    store_a.record_request("tenant A unmatched", bundle_id=None, matched=False)
    store_b.record_request("tenant B unmatched", bundle_id=None, matched=False)

    path_a = tmp_path / "tenants" / "tenant_a" / "request_patterns.jsonl"
    foreign_record = {
        "record_id": "foreign-record",
        "tenant_id": "tenant_b",
        "timestamp": "2026-07-16T00:00:00+00:00",
        "raw_input": "drifted tenant B input",
        "bundle_id": None,
        "matched": False,
    }
    with path_a.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(foreign_record) + "\n")

    assert [item["raw_input"] for item in store_a.get_all()] == [
        "tenant A unmatched",
    ]
    assert [item["raw_input"] for item in store_b.get_all()] == [
        "tenant B unmatched",
    ]
    assert store_a.clear_unmatched() == 1
    assert store_a.get_all() == []
    persisted = [
        json.loads(line)
        for line in path_a.read_text(encoding="utf-8").splitlines()
    ]
    assert persisted == [foreign_record]


def test_pattern_store_serializes_writes_across_instances(tmp_path):
    """Per-path locking prevents concurrent request instances from losing rows."""
    from app.storage.request_pattern_store import RequestPatternStore

    stores = [RequestPatternStore(tmp_path, tenant_id="tenant_a") for _ in range(20)]
    threads = [
        threading.Thread(
            target=store.record_request,
            args=(f"request {index}", None, False),
        )
        for index, store in enumerate(stores)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    records = RequestPatternStore(tmp_path, tenant_id="tenant_a").get_all()
    assert len(records) == 20
    assert {record["raw_input"] for record in records} == {
        f"request {index}" for index in range(20)
    }


def test_pattern_store_get_unmatched_filters_correctly(tmp_path):
    """get_unmatched이 matched=False 레코드만 반환하는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore

    store = RequestPatternStore(tmp_path, tenant_id="system")
    store.record_request("매칭된 요청", bundle_id="tech_decision", matched=True)
    store.record_request("비매칭 요청 A", bundle_id=None, matched=False)
    store.record_request("비매칭 요청 B", bundle_id=None, matched=False)

    unmatched = store.get_unmatched()
    assert len(unmatched) == 2
    assert all(not r["matched"] for r in unmatched)


def test_pattern_store_clear_unmatched_removes_only_unmatched(tmp_path):
    """clear_unmatched 후 matched 레코드만 남는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore

    store = RequestPatternStore(tmp_path, tenant_id="system")
    store.record_request("매칭 요청", bundle_id="prd_kr", matched=True)
    store.record_request("비매칭 1", bundle_id=None, matched=False)
    store.record_request("비매칭 2", bundle_id=None, matched=False)

    removed = store.clear_unmatched()
    assert removed == 2

    remaining = store.get_all()
    assert len(remaining) == 1
    assert remaining[0]["matched"] is True

    # 두 번째 호출 — 이미 unmatched 없음 → 0 반환
    assert store.clear_unmatched() == 0


def test_pattern_store_limit_respected(tmp_path):
    """get_unmatched / get_all의 limit 파라미터가 동작하는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore

    store = RequestPatternStore(tmp_path, tenant_id="system")
    for i in range(10):
        store.record_request(f"요청 {i}", bundle_id=None, matched=False)

    assert len(store.get_unmatched(limit=3)) == 3
    assert len(store.get_all(limit=5)) == 5


def test_pattern_store_raw_input_truncated(tmp_path):
    """raw_input이 200자로 잘리는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore

    store = RequestPatternStore(tmp_path, tenant_id="system")
    long_input = "A" * 300
    store.record_request(long_input, bundle_id=None, matched=False)

    records = store.get_all()
    assert len(records[0]["raw_input"]) == 200


# ── BundleAutoExpander 단위 테스트 ───────────────────────────────────────────


def test_bundle_expander_below_threshold_returns_none(tmp_path, monkeypatch):
    """unmatched 요청 수가 threshold 미만이면 None을 반환하는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.services.bundle_expander import BundleAutoExpander
    from app.providers.mock_provider import MockProvider

    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "10")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    pattern_store = RequestPatternStore(tmp_path, tenant_id="system")
    # 5건만 추가 (threshold=10 미만)
    for i in range(5):
        pattern_store.record_request(f"비매칭 요청 {i}", bundle_id=None, matched=False)

    provider = MockProvider()
    expander = BundleAutoExpander(provider=provider, pattern_store=pattern_store)
    result = expander.analyze_and_expand()
    assert result is None


def test_bundle_expander_low_confidence_returns_none(tmp_path, monkeypatch):
    """confidence < 0.7 응답에서 None을 반환하는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.services.bundle_expander import BundleAutoExpander

    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "3")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    pattern_store = RequestPatternStore(tmp_path, tenant_id="system")
    for i in range(5):
        pattern_store.record_request(f"요청 {i}", bundle_id=None, matched=False)

    # Low-confidence mock provider
    class LowConfidenceMock:
        name = "mock_low"

        def generate_raw(self, prompt, *, request_id, **kwargs):
            return json.dumps({
                "detected": True,
                "bundle_id": "low_conf_bundle",
                "bundle_name": "저신뢰도 번들",
                "description": "테스트",
                "icon": "📄",
                "sections": [{"id": "s1", "title": "섹션1", "required": True}],
                "confidence": 0.5,
            }, ensure_ascii=False)

    expander = BundleAutoExpander(provider=LowConfidenceMock(), pattern_store=pattern_store)
    result = expander.analyze_and_expand()
    assert result is None


def test_bundle_expander_success(tmp_path, monkeypatch):
    """임계값 이상 unmatched + confidence ≥ 0.7 → 번들 생성 성공."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.services.bundle_expander import BundleAutoExpander
    from app.providers.mock_provider import MockProvider

    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "3")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    pattern_store = RequestPatternStore(tmp_path, tenant_id="system")
    for i in range(5):
        pattern_store.record_request(f"비매칭 요청 {i}", bundle_id=None, matched=False)

    provider = MockProvider()
    expander = BundleAutoExpander(provider=provider, pattern_store=pattern_store)
    result = expander.analyze_and_expand()

    # 번들이 생성되었는지 확인
    assert result is not None
    assert result["bundle_id"] == "mock_auto_bundle_kr"
    assert result["confidence"] >= 0.7
    assert "sections" in result

    # registry.json이 생성되었는지 확인
    registry_path = tmp_path / "auto_bundles" / "registry.json"
    assert registry_path.exists()
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "mock_auto_bundle_kr" in data

    # Python 코드 파일이 생성되었는지 확인
    py_path = tmp_path / "auto_bundles" / "mock_auto_bundle_kr.py"
    assert py_path.exists()

    # clear_unmatched 되었는지 확인
    assert len(pattern_store.get_unmatched()) == 0


def test_bundle_expander_no_conflict_with_builtin(tmp_path, monkeypatch):
    """이미 존재하는 번들 ID와 충돌하면 생성하지 않는지 확인."""
    from app.storage.request_pattern_store import RequestPatternStore
    from app.services.bundle_expander import BundleAutoExpander

    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "3")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    pattern_store = RequestPatternStore(tmp_path, tenant_id="system")
    for i in range(5):
        pattern_store.record_request(f"요청 {i}", bundle_id=None, matched=False)

    # Mock that returns a bundle_id that conflicts with a built-in bundle
    class ConflictMock:
        name = "mock_conflict"

        def generate_raw(self, prompt, *, request_id, **kwargs):
            return json.dumps({
                "detected": True,
                "bundle_id": "tech_decision",  # 이미 존재하는 번들
                "bundle_name": "충돌 번들",
                "description": "테스트",
                "icon": "📄",
                "sections": [{"id": "s1", "title": "섹션1", "required": True}],
                "confidence": 0.9,
            }, ensure_ascii=False)

    expander = BundleAutoExpander(provider=ConflictMock(), pattern_store=pattern_store)
    result = expander.analyze_and_expand()
    assert result is None


def test_bundle_expander_rejects_unsafe_bundle_id_before_writing(
    tmp_path,
    monkeypatch,
):
    """Provider output cannot escape the auto-bundle directory."""
    from app.services.bundle_expander import BundleAutoExpander
    from app.storage.request_pattern_store import RequestPatternStore

    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "1")
    pattern_store = RequestPatternStore(tmp_path, tenant_id="system")
    pattern_store.record_request("unsafe bundle request", None, False)

    class UnsafeBundleProvider:
        def generate_raw(self, prompt, *, request_id):  # noqa: ANN001, ARG002
            return json.dumps({
                "detected": True,
                "bundle_id": "../../outside",
                "bundle_name": "Unsafe",
                "description": "Unsafe path",
                "icon": "x",
                "sections": [
                    {"id": f"section_{index}", "title": "Section", "required": True}
                    for index in range(5)
                ],
                "confidence": 0.99,
            })

    expander = BundleAutoExpander(
        UnsafeBundleProvider(),
        pattern_store=pattern_store,
        data_dir=tmp_path,
    )

    assert expander.analyze_and_expand() is None
    assert not (tmp_path / "auto_bundles").exists()
    assert list(tmp_path.rglob("outside.py")) == []
    assert len(pattern_store.get_unmatched()) == 1


@pytest.mark.parametrize(
    "provider_response",
    [
        None,
        {},
        "[]",
        json.dumps({"detected": True, "confidence": "not-a-number"}),
        json.dumps({"detected": True, "confidence": "NaN"}),
        json.dumps({"detected": "true", "confidence": 0.9}),
        json.dumps({
            "detected": True,
            "confidence": 0.9,
            "bundle_id": 123,
        }),
    ],
)
def test_bundle_expander_rejects_malformed_provider_contract(
    tmp_path,
    monkeypatch,
    provider_response,
):
    """Malformed provider output is rejected without partial artifacts."""
    from app.services.bundle_expander import BundleAutoExpander
    from app.storage.request_pattern_store import RequestPatternStore

    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "1")
    pattern_store = RequestPatternStore(tmp_path, tenant_id="system")
    pattern_store.record_request("malformed provider request", None, False)

    class MalformedProvider:
        def generate_raw(self, prompt, *, request_id):  # noqa: ANN001, ARG002
            return provider_response

    expander = BundleAutoExpander(
        MalformedProvider(),
        pattern_store=pattern_store,
        data_dir=tmp_path,
    )

    assert expander.analyze_and_expand() is None
    assert not (tmp_path / "auto_bundles").exists()
    assert len(pattern_store.get_unmatched()) == 1


def test_generated_bundle_code_escapes_provider_text() -> None:
    """Human-review source remains valid Python for quoted provider text."""
    from app.services.bundle_expander import BundleAutoExpander

    code = BundleAutoExpander._generate_python_code({
        "bundle_id": "quoted_bundle_kr",
        "name_ko": '인용 "번들"\n이름',
        "name_en": "Quoted Bundle",
        "description_ko": "첫 줄\n둘째 줄",
        "icon": "doc",
        "created_at": "2026-07-16T00:00:00+00:00",
        "sections": [
            {"id": "summary", "title": '요약 "인용"'},
        ],
    })

    compile(code, "quoted_bundle_kr.py", "exec")


# ── AutoRegistry 단위 테스트 ─────────────────────────────────────────────────


def test_auto_registry_load_bundles(tmp_path, monkeypatch):
    """data/auto_bundles/registry.json에서 BundleSpec을 로드하는지 확인."""
    from app.bundle_catalog.auto_registry import load_auto_bundles

    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    # 레지스트리 생성
    auto_dir = tmp_path / "auto_bundles"
    auto_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "test_auto_bundle": {
            "bundle_id": "test_auto_bundle",
            "name_ko": "테스트 자동 번들",
            "name_en": "Test Auto Bundle",
            "description_ko": "테스트용 번들",
            "icon": "🧪",
            "confidence": 0.85,
            "sections": [
                {"id": "intro", "title": "소개", "required": True},
                {"id": "details", "title": "세부 내용", "required": True},
                {"id": "conclusion", "title": "결론", "required": False},
                {"id": "appendix", "title": "부록", "required": False},
                {"id": "references", "title": "참고 자료", "required": False},
            ],
        }
    }
    (auto_dir / "registry.json").write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )

    bundles = load_auto_bundles()
    assert "test_auto_bundle" in bundles
    spec = bundles["test_auto_bundle"]
    assert spec.id == "test_auto_bundle"
    assert spec.name_ko == "테스트 자동 번들"
    assert len(spec.docs) == 5


def test_auto_registry_empty_when_no_file(tmp_path, monkeypatch):
    """registry.json이 없으면 빈 딕셔너리를 반환하는지 확인."""
    from app.bundle_catalog.auto_registry import load_auto_bundles

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = load_auto_bundles()
    assert result == {}


# ── Admin API 통합 테스트 ────────────────────────────────────────────────────


@pytest.fixture()
def _admin_client(tmp_path, monkeypatch):
    """Admin API 테스트용 TestClient."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    import app.main as main_module
    from fastapi.testclient import TestClient
    application = main_module.create_app()
    return TestClient(application), tmp_path


def test_admin_request_patterns_empty(tmp_path, monkeypatch):
    """GET /admin/request-patterns — 초기 상태에서 빈 레코드 반환."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    import app.main as main_module
    from fastapi.testclient import TestClient
    client = TestClient(main_module.create_app())

    resp = client.get(
        "/admin/request-patterns",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["unmatched_count"] == 0
    assert data["records"] == []


def test_admin_request_patterns_shows_records(tmp_path, monkeypatch):
    """GET /admin/request-patterns — 기록된 패턴이 응답에 포함되는지 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    import app.main as main_module
    from app.storage.request_pattern_store import RequestPatternStore
    from fastapi.testclient import TestClient

    client = TestClient(main_module.create_app())

    # 직접 패턴 기록
    store = RequestPatternStore(tmp_path, tenant_id="system")
    store.record_request("비매칭 요청 A", bundle_id=None, matched=False)
    store.record_request("매칭 요청 B", bundle_id="tech_decision", matched=True)

    resp = client.get(
        "/admin/request-patterns",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["unmatched_count"] == 1


def test_request_pattern_routes_use_current_tenant(tmp_path, monkeypatch):
    """Freeform writes and admin reads remain inside the request tenant."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "pattern-api-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "pattern-ops-key")
    from app.main import create_app
    from fastapi.testclient import TestClient

    application = create_app()
    application.state.tenant_store.create_tenant("tenant_a", "Tenant A")
    application.state.tenant_store.create_tenant("tenant_b", "Tenant B")
    client = TestClient(application)

    def headers(tenant_id: str) -> dict[str, str]:
        return {
            "X-Tenant-ID": tenant_id,
            "X-DecisionDoc-Api-Key": "pattern-api-key",
            "X-DecisionDoc-Ops-Key": "pattern-ops-key",
        }

    response_a = client.post(
        "/generate/freeform",
        headers=headers("tenant_a"),
        json={"title": "Tenant A request", "goal": "A-only pattern"},
    )
    response_b = client.post(
        "/generate/freeform",
        headers=headers("tenant_b"),
        json={"title": "Tenant B request", "goal": "B-only pattern"},
    )
    assert response_a.status_code == response_b.status_code == 200
    assert client.post(
        "/generate/freeform",
        headers=headers("tenant_a"),
        json={"title": "", "goal": ""},
    ).status_code == 422
    assert client.post(
        "/generate/freeform",
        headers=headers("tenant_a"),
        json={"title": "Valid title", "goal": "Valid goal", "unknown": True},
    ).status_code == 422

    patterns_a = client.get(
        "/admin/request-patterns",
        headers=headers("tenant_a"),
    ).json()
    patterns_b = client.get(
        "/admin/request-patterns",
        headers=headers("tenant_b"),
    ).json()
    assert [item["raw_input"] for item in patterns_a["records"]] == [
        "Tenant A request A-only pattern",
    ]
    assert [item["raw_input"] for item in patterns_b["records"]] == [
        "Tenant B request B-only pattern",
    ]


def test_request_patterns_reject_member_role(tmp_path, monkeypatch):
    """Raw request titles and goals are visible only to admins and Ops."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("JWT_SECRET_KEY", "pattern-test-secret-at-least-32-bytes")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.delenv("DECISIONDOC_OPS_KEY", raising=False)
    from app.main import create_app
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    client.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "admin@example.com",
            "password": "AdminPass1!",
        },
    )
    admin_login = client.post(
        "/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    ).json()
    admin_headers = {
        "Authorization": f"Bearer {admin_login['access_token']}",
    }
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": "member",
            "display_name": "Member",
            "email": "member@example.com",
            "password": "MemberPass1!",
            "role": "member",
        },
    )
    assert created.status_code == 200
    member_login = client.post(
        "/auth/login",
        json={"username": "member", "password": "MemberPass1!"},
    ).json()

    response = client.get(
        "/admin/request-patterns",
        headers={"Authorization": f"Bearer {member_login['access_token']}"},
    )

    assert response.status_code == 403


def test_admin_auto_bundles_list(tmp_path, monkeypatch):
    """GET /admin/auto-bundles — 자동 생성 번들 목록 반환."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    import app.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.create_app())
    ops_headers = {"X-DecisionDoc-Ops-Key": "test-ops-key"}

    # 초기 상태: 빈 목록
    resp = client.get("/admin/auto-bundles", headers=ops_headers)
    assert resp.status_code == 200
    data = resp.json()
    bundles = data.get("bundles") if isinstance(data, dict) else data
    assert bundles == []

    # registry.json 생성
    auto_dir = tmp_path / "auto_bundles"
    auto_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "sample_auto_kr": {
            "bundle_id": "sample_auto_kr",
            "name_ko": "샘플 자동 번들",
            "confidence": 0.8,
            "sections": [],
        }
    }
    (auto_dir / "registry.json").write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )

    resp = client.get("/admin/auto-bundles", headers=ops_headers)
    assert resp.status_code == 200
    data = resp.json()
    items = data["bundles"] if "bundles" in data else data
    assert len(items) == 1
    assert items[0]["bundle_id"] == "sample_auto_kr"

    (auto_dir / "registry.json").write_text("[]", encoding="utf-8")
    resp = client.get("/admin/auto-bundles", headers=ops_headers)
    data = resp.json()
    bundles = data.get("bundles") if isinstance(data, dict) else data
    assert bundles == []


def test_admin_delete_auto_bundle(tmp_path, monkeypatch):
    """DELETE /admin/auto-bundles/{bundle_id} — 번들 삭제 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    import app.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.create_app())

    # registry.json 생성
    auto_dir = tmp_path / "auto_bundles"
    auto_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "to_delete_kr": {
            "bundle_id": "to_delete_kr",
            "name_ko": "삭제될 번들",
            "confidence": 0.8,
            "sections": [],
        }
    }
    (auto_dir / "registry.json").write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )

    # 삭제 요청
    resp = client.delete(
        "/admin/auto-bundles/to_delete_kr",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["bundle_id"] == "to_delete_kr"

    # 삭제 후 목록 확인
    resp = client.get("/admin/auto-bundles", headers={"X-DecisionDoc-Ops-Key": "test-ops-key"})
    data = resp.json()
    bundles = data["bundles"] if "bundles" in data else data
    assert bundles == []


def test_admin_delete_nonexistent_bundle_returns_404(tmp_path, monkeypatch):
    """DELETE /admin/auto-bundles/{bundle_id} — 존재하지 않는 번들은 404 반환."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    import app.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.create_app())

    resp = client.delete(
        "/admin/auto-bundles/nonexistent_bundle",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert resp.status_code == 404


def test_admin_delete_rejects_unsafe_bundle_id(tmp_path, monkeypatch):
    """DELETE validates legacy registry keys before resolving a source path."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    import app.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.create_app())
    response = client.delete(
        "/admin/auto-bundles/unsafe.bundle",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )

    assert response.status_code == 400


def test_admin_expand_bundles_below_threshold(tmp_path, monkeypatch):
    """POST /admin/expand-bundles — 임계값 미달 시 expanded=False 반환."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "10")
    import app.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.create_app())

    # 2건만 기록 (threshold=10 미만)
    from app.storage.request_pattern_store import RequestPatternStore
    store = RequestPatternStore(tmp_path, tenant_id="system")
    store.record_request("비매칭 A", bundle_id=None, matched=False)
    store.record_request("비매칭 B", bundle_id=None, matched=False)

    resp = client.post(
        "/admin/expand-bundles",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expanded"] is False


def test_admin_expand_bundles_success(tmp_path, monkeypatch):
    """POST /admin/expand-bundles — 임계값 이상 + Mock 고신뢰도 → expanded=True."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.setenv("AUTO_EXPAND_THRESHOLD", "3")
    import app.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.create_app())

    # 5건 기록 (threshold=3 이상)
    from app.storage.request_pattern_store import RequestPatternStore
    store = RequestPatternStore(tmp_path, tenant_id="system")
    for i in range(5):
        store.record_request(f"비매칭 요청 {i}", bundle_id=None, matched=False)

    resp = client.post(
        "/admin/expand-bundles",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expanded"] is True
    assert "bundle" in body
    assert body["bundle"]["bundle_id"] == "mock_auto_bundle_kr"
