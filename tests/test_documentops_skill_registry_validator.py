from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_documentops_skill_registry import RESULT_SCHEMA_VERSION, main


def _skill_text(name: str = "sample", task_type: str = "sample_task") -> str:
    return f"""---
name: {name}
version: 1.2.3
title: Sample Skill
description: A sample skill.
task_types:
  - {task_type}
risk_level: low
---

Body.
"""


def test_validator_emits_versioned_deterministic_json_for_registry(capsys, tmp_path: Path) -> None:
    (tmp_path / "zeta.md").write_text(_skill_text("zeta", "zeta_task"), encoding="utf-8")
    (tmp_path / "alpha.md").write_text(_skill_text("alpha", "alpha_task"), encoding="utf-8")

    assert main(["--registry-dir", str(tmp_path), "--json"]) == 0
    first = capsys.readouterr().out
    assert main(["--registry-dir", str(tmp_path), "--json"]) == 0
    second = capsys.readouterr().out

    assert first == second
    result = json.loads(first)
    assert result["schema_version"] == RESULT_SCHEMA_VERSION
    assert result["status"] == "passed"
    assert [item["name"] for item in result["skills"]] == ["alpha", "zeta"]
    assert all("body" not in item and "source_path" not in item for item in result["skills"])


def test_validator_returns_json_failure_for_invalid_registry(capsys, tmp_path: Path) -> None:
    broken = _skill_text("broken").replace("risk_level: low", "unknown: true\nrisk_level: low")
    (tmp_path / "broken.md").write_text(broken, encoding="utf-8")

    assert main(["--registry-dir", str(tmp_path), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == RESULT_SCHEMA_VERSION
    assert result["status"] == "failed"
    assert result["error_type"] == "ValueError"
