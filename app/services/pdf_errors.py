"""PDF export errors, importable without Playwright (deployments may omit it)."""
from __future__ import annotations

PDF_ENGINE_INSTALL_HINT = "python3 -m playwright install chromium"


class PdfEngineUnavailableError(RuntimeError):
    """The headless Chromium used for PDF rendering could not start."""

    def __init__(self, detail: str = "") -> None:
        reason = detail.splitlines()[0] if detail else "unknown reason"
        super().__init__(
            f"PDF 변환 엔진(Chromium)을 시작할 수 없습니다. `{PDF_ENGINE_INSTALL_HINT}`로 설치한 뒤 다시 시도하세요. ({reason})"
        )
