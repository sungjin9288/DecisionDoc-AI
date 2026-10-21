"""A missing PDF engine is reported as 503 with an install hint, not an opaque 500."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from playwright.async_api import Error as PlaywrightError

from app.services import pdf_service
from app.services.pdf_errors import PdfEngineUnavailableError
from tests.async_helper import run_async

API_KEY = "pdf-engine-test-key"


class _MissingChromium:
    async def launch(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise PlaywrightError("BrowserType.launch: Executable doesn't exist at /cache/chrome-headless-shell")


class _FakePlaywright:
    chromium = _MissingChromium()

    async def __aenter__(self) -> "_FakePlaywright":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.fixture
def missing_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_service, "async_playwright", lambda: _FakePlaywright())


def test_build_pdf_raises_engine_unavailable_with_install_hint(missing_engine: None) -> None:
    with pytest.raises(PdfEngineUnavailableError) as excinfo:
        run_async(pdf_service.build_pdf([{"doc_type": "adr", "markdown": "# 제목\n본문"}], "제목"))

    assert "playwright install chromium" in str(excinfo.value)


def test_export_edited_pdf_returns_503_with_code(missing_engine: None, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", API_KEY)
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    from app.main import create_app

    with TestClient(create_app(), headers={"X-DecisionDoc-Api-Key": API_KEY}) as client:
        response = client.post(
            "/generate/export-edited",
            json={
                "bundle_id": "pdf-engine",
                "bundle_type": "tech_decision",
                "title": "제목",
                "format": "pdf",
                "docs": [{"doc_type": "adr", "markdown": "# 제목\n본문"}],
                "generate_missing_visuals": False,
            },
        )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "PDF_ENGINE_UNAVAILABLE"
    assert "playwright install chromium" in body["message"]
