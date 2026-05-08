from pathlib import Path

import pytest

from app.agents.skill_registry import SkillNotFoundError, SkillRegistry


def test_registry_loads_first_party_skills() -> None:
    registry = SkillRegistry.from_directory()
    names = {skill.name for skill in registry.list_skills()}
    assert {"policy-planning", "evidence-gap-checker", "decision-brief-builder"} <= names


def test_registry_selects_skill_by_task_type() -> None:
    registry = SkillRegistry.from_directory()
    assert registry.select("policy_planning_brief").name == "policy-planning"
    assert registry.select("evidence_gap_review").name == "evidence-gap-checker"
    assert registry.select("decision_brief").name == "decision-brief-builder"


def test_registry_rejects_wrong_preferred_skill_for_task() -> None:
    registry = SkillRegistry.from_directory()
    with pytest.raises(SkillNotFoundError):
        registry.select("decision_brief", preferred_name="policy-planning")


def test_registry_rejects_duplicate_skill_names(tmp_path: Path) -> None:
    content = """---
name: duplicate
version: 0.1.0
title: Duplicate
description: Duplicate skill.
task_types:
  - one
risk_level: low
---

Body.
"""
    (tmp_path / "a.md").write_text(content, encoding="utf-8")
    (tmp_path / "b.md").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate skill name"):
        SkillRegistry.from_directory(tmp_path)
