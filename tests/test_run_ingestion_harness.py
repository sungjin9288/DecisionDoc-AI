from __future__ import annotations

import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_ingestion_harness.py"
_SPEC = importlib.util.spec_from_file_location("run_ingestion_harness", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_single_pdf_mode_detects_default_pdf_flow():
    path = Path("/tmp/example.pdf")
    assert _MODULE._single_pdf_mode([path], disable_pdf_endpoint=False) is True
    assert _MODULE._single_pdf_mode([path], disable_pdf_endpoint=True) is False


def test_build_context_preserves_source_boundaries(tmp_path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    context = _MODULE._build_context(
        [
            (first, "alpha"),
            (second, "beta"),
        ]
    )

    assert "# Source: first.md" in context
    assert "# Source: second.md" in context
    assert "alpha" in context
    assert "beta" in context
    assert "---" in context


def test_read_input_markdown_for_plain_text(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# Heading\n\nbody", encoding="utf-8")

    markdown = _MODULE._read_input_markdown(path, enable_plugins=False)

    assert markdown == "# Heading\n\nbody"
