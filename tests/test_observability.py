import logging
import json
import sys
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.observability.logging import JsonLineFormatter


def _create_client(tmp_path, monkeypatch, provider="mock", procurement_enabled=False):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv(
        "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED",
        "1" if procurement_enabled else "0",
    )
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def _captured_events(caplog, capsys) -> list[dict]:
    events = []
    for record in caplog.records:
        if isinstance(record.msg, dict):
            events.append(record.msg)
            continue
        text = record.getMessage()
        if isinstance(text, str) and text.startswith("{"):
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    if events:
        return events

    stderr_output = capsys.readouterr().err
    for line in stderr_output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def test_logs_emitted_for_generate(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "obs", "goal": "capture logs"})
    assert response.status_code == 200

    events = _captured_events(caplog, capsys)
    assert any(e.get("event") == "request.completed" for e in events)
    generate_events = [e for e in events if e.get("event") == "generate.completed"]
    assert generate_events

    evt = generate_events[-1]
    assert isinstance(evt.get("request_id"), str)
    assert evt.get("status_code") == 200
    for key in ["provider_ms", "render_ms", "lints_ms", "validator_ms"]:
        assert isinstance(evt.get(key), int)
        assert evt.get(key) >= 0


def test_logs_do_not_contain_sensitive_tokens(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)

    sentinel = "SUPER_SECRET_DO_NOT_LOG"
    response = client.post(
        "/generate",
        json={
            "title": "sensitive",
            "goal": "sensitive",
            "context": sentinel,
            "constraints": sentinel,
            "assumptions": [sentinel],
        },
    )
    assert response.status_code == 200

    all_logs = "\n".join([caplog.text] + [str(r.msg) for r in caplog.records])
    assert sentinel not in all_logs
    assert "OPENAI_API_KEY" not in all_logs
    assert "GEMINI_API_KEY" not in all_logs


def test_json_formatter_includes_traceback_for_exception_records():
    formatter = JsonLineFormatter()
    try:
        raise RuntimeError("formatter boom")
    except RuntimeError:
        record = logging.getLogger("decisiondoc.test").makeRecord(
            name="decisiondoc.test",
            level=logging.ERROR,
            fn=__file__,
            lno=0,
            msg="Unhandled error during test",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(formatter.format(record))
    assert payload["message"] == "Unhandled error during test"
    assert "traceback" in payload
    assert "RuntimeError: formatter boom" in payload["traceback"]


def test_procurement_logs_include_action_state_and_recommendation(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch, procurement_enabled=True)

    create_project = client.post("/projects", json={"name": "obs procurement", "fiscal_year": 2026})
    assert create_project.status_code == 200
    project_id = create_project.json()["project_id"]

    from app.services.g2b_collector import G2BAnnouncement
    fake = G2BAnnouncement(
        bid_number="OBS-2026-001",
        title="AI 기반 민원 서비스 고도화 사업",
        issuer="행정안전부",
        budget="5억원",
        announcement_date="2026-03-25",
        deadline="2026-05-30 17:00",
        bid_type="일반경쟁",
        category="용역",
        detail_url="https://www.g2b.go.kr/notice/OBS-2026-001",
        attachments=[],
        raw_text="입찰참가자격: 소프트웨어사업자, ISMS 보유. 유사사업 수행실적 필요.",
        source="scrape",
    )

    with patch(
        "app.services.g2b_collector.fetch_announcement_detail",
        new=AsyncMock(return_value=fake),
    ):
        imported = client.post(
            f"/projects/{project_id}/imports/g2b-opportunity",
            json={"url_or_number": "OBS-2026-001"},
        )
    assert imported.status_code == 200

    from app.storage.knowledge_store import KnowledgeStore
    KnowledgeStore(project_id, data_dir=str(tmp_path)).add_document(
        "capability.txt",
        (
            "공공 AI 서비스 구축 레퍼런스 2건, 클라우드 전환 경험, "
            "소프트웨어사업자 등록, ISMS 인증, PM/개발자/컨설턴트 인력 보유."
        ),
    )

    recommended = client.post(f"/projects/{project_id}/procurement/recommend")
    assert recommended.status_code == 200

    events = _captured_events(caplog, capsys)
    import_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/imports/g2b-opportunity"
    ]
    assert import_events
    assert import_events[-1]["procurement_action"] == "import"
    assert import_events[-1]["procurement_project_id"] == project_id
    assert import_events[-1]["procurement_operation"] == "created"
    assert import_events[-1]["procurement_source_kind"] == "g2b"
    assert import_events[-1]["procurement_source_id"] == "OBS-2026-001"

    recommend_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/procurement/recommend"
    ]
    assert recommend_events
    assert recommend_events[-1]["procurement_action"] == "recommend"
    assert recommend_events[-1]["procurement_project_id"] == project_id
    assert recommend_events[-1]["procurement_recommendation"] in {"GO", "CONDITIONAL_GO", "NO_GO"}
    assert recommend_events[-1]["procurement_checklist_action_count"] >= 0


def test_generate_logs_procurement_handoff_usage(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch, procurement_enabled=True)

    create_project = client.post("/projects", json={"name": "handoff obs", "fiscal_year": 2026})
    assert create_project.status_code == 200
    project_id = create_project.json()["project_id"]

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
        ProcurementRecommendationValue,
    )
    store = client.app.state.procurement_store
    snapshot = store.save_source_snapshot(
        tenant_id="system",
        project_id=project_id,
        source_kind="g2b_import",
        source_label="obs handoff",
        external_id="OBS-HANDOFF-001",
        payload={
            "announcement": {"title": "AI 기반 민원 서비스 고도화 사업"},
            "extracted_fields": {"issuer": "행정안전부"},
            "structured_context": "행정안전부 / CONDITIONAL_GO / 최신 파트너 확약서 필요",
        },
    )
    store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="OBS-HANDOFF-001",
                source_url="https://www.g2b.go.kr/notice/OBS-HANDOFF-001",
                title="AI 기반 민원 서비스 고도화 사업",
                issuer="행정안전부",
                budget="5억원",
                deadline="2026-05-30 17:00",
                bid_type="일반경쟁",
                category="용역",
                region="전국",
                raw_text_preview="행정안전부 / CONDITIONAL_GO",
            ),
            recommendation=ProcurementRecommendation(
                value=ProcurementRecommendationValue.CONDITIONAL_GO,
                summary="조건부 진행",
                evidence=["레퍼런스는 충분하지만 파트너 확약이 필요합니다."],
            ),
            source_snapshots=[snapshot],
        )
    )

    response = client.post(
        "/generate",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 참여 여부를 판단한다",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
        },
    )
    assert response.status_code == 200

    events = _captured_events(caplog, capsys)
    generate_events = [e for e in events if e.get("event") == "generate.completed"]
    assert generate_events
    assert generate_events[-1]["bundle_type"] == "bid_decision_kr"
    assert generate_events[-1]["procurement_handoff_used"] is True

    request_events = [
        e for e in events
        if e.get("event") == "request.completed" and e.get("path") == "/generate"
    ]
    assert request_events
    assert request_events[-1]["procurement_handoff_used"] is True
