from pathlib import Path
import tempfile

from fastapi.testclient import TestClient


def test_create_app_defaults_data_dir_to_tmp_in_lambda(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "decisiondoc-ai-dev")
    monkeypatch.delenv("LAMBDA_TASK_ROOT", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    assert app.state.service.data_dir == Path(tempfile.gettempdir()) / "decisiondoc"
    assert client.get("/health").status_code == 200


def test_create_app_preserves_explicit_data_dir_in_lambda(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "decisiondoc-ai-dev")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LAMBDA_TASK_ROOT", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    app = create_app()

    assert app.state.service.data_dir == tmp_path
    assert Path(tmp_path).exists()
