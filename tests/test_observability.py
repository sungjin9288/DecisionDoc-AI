import logging

from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch, provider="mock"):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def test_logs_emitted_for_generate(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "obs", "goal": "capture logs"})
    assert response.status_code == 200

    events = [r.msg for r in caplog.records if isinstance(r.msg, dict)]
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
