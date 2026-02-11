import difflib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

GOLDEN_FIXTURES = [
    "01_normal_default_all.json",
    "04_underspecified_short_goal.json",
    "05_underspecified_short_context.json",
    "07_security_sensitive_constraints_1.json",
    "09_cost_constrained_1.json",
]
DOC_ORDER = ["adr", "onepager", "eval_plan", "ops_checklist"]


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "<uuid>",
        text,
    )
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip() + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def test_golden_snapshots_v1(tmp_path, monkeypatch, request):
    update = bool(request.config.getoption("--update-golden"))
    client = _create_client(tmp_path, monkeypatch)
    fixtures_dir = Path(__file__).parent / "fixtures"
    golden_root = Path(__file__).parent / "golden" / "v1"

    for fixture_name in GOLDEN_FIXTURES:
        payload = json.loads((fixtures_dir / fixture_name).read_text(encoding="utf-8"))
        response = client.post("/generate", json=payload)
        assert response.status_code == 200, fixture_name
        body = response.json()
        rendered = {doc["doc_type"]: _normalize(doc["markdown"]) for doc in body["docs"]}

        fixture_base = fixture_name.replace(".json", "")
        for doc_type in DOC_ORDER:
            if doc_type not in rendered:
                continue
            golden_path = golden_root / fixture_base / f"{doc_type}.md"
            if update:
                _atomic_write_text(golden_path, rendered[doc_type])
                continue

            assert golden_path.exists(), f"Missing golden snapshot: {golden_path}"
            expected = _normalize(golden_path.read_text(encoding="utf-8"))
            if rendered[doc_type] != expected:
                diff = "".join(
                    difflib.unified_diff(
                        expected.splitlines(keepends=True),
                        rendered[doc_type].splitlines(keepends=True),
                        fromfile=f"{golden_path} (expected)",
                        tofile=f"{fixture_name}:{doc_type} (actual)",
                    )
                )
                raise AssertionError(f"Golden mismatch for {fixture_name}/{doc_type}\n{diff}")
