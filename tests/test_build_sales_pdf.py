from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_markdown_to_html_renders_table_and_inline_code() -> None:
    builder = _load_script_module("decisiondoc_build_sales_intro_pdf", "scripts/build_sales_intro_pdf.py")
    html = builder._markdown_to_html(
        "# 제목\n\n| 항목 | 값 |\n| --- | --- |\n| 접근 | `admin.decisiondoc.kr` |\n"
    )

    assert "<table>" in html
    assert "<th>항목</th>" in html
    assert "<td><code>admin.decisiondoc.kr</code></td>" in html


def test_build_sales_pack_html_only_writes_selected_artifact(tmp_path: Path) -> None:
    pack_builder = _load_script_module("decisiondoc_build_sales_pack", "scripts/build_sales_pack.py")

    result = pack_builder.main(
        [
            "--docs",
            "meeting_onepager",
            "--output-dir",
            str(tmp_path),
            "--html-only",
        ]
    )

    assert result == 0
    assert (tmp_path / "decisiondoc_ai_meeting_onepager_ko.html").exists()
    assert not (tmp_path / "decisiondoc_ai_meeting_onepager_ko.pdf").exists()
