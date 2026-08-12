from pathlib import Path
import re

import pytest

from app.agents.skill_registry import SkillNotFoundError, SkillRegistry


def _skill_text(name: str = "sample", **overrides: str) -> str:
    values = {
        "name": name,
        "version": "1.2.3",
        "title": "Sample Skill",
        "description": "A sample skill.",
        "task_types": "\n  - sample_task",
        "risk_level": "low",
    }
    values.update(overrides)
    lines = ["---"]
    for key, value in values.items():
        if value.startswith("\n"):
            lines.append(f"{key}:{value}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n---\n\nBody.\n"


def test_registry_loads_first_party_skills() -> None:
    registry = SkillRegistry.from_directory()
    names = {skill.name for skill in registry.list_skills()}
    assert {
        "policy-planning",
        "evidence-gap-checker",
        "decision-brief-builder",
        "develop-document-improver",
    } <= names


def test_registry_selects_skill_by_task_type() -> None:
    registry = SkillRegistry.from_directory()
    assert registry.select("policy_planning_brief").name == "policy-planning"
    assert registry.select("evidence_gap_review").name == "evidence-gap-checker"
    assert registry.select("decision_brief").name == "decision-brief-builder"
    assert registry.select("develop_quality_improvement").name == "develop-document-improver"


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


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("sample.md", _skill_text(name="wrong-name"), "unsafe or mismatched"),
        ("sample.md", _skill_text(version="1.2"), "semantic version"),
        ("sample.md", _skill_text(task_types="\n  - sample_task\n  - sample_task"), "duplicate task type"),
        ("sample.md", _skill_text(task_types="[]"), "empty task_types"),
        ("sample.md", _skill_text(task_types="\n  - ''"), "empty task type"),
        ("sample.md", _skill_text(risk_level="critical"), "risk level"),
        ("sample.md", _skill_text(description=""), "description"),
        ("sample.md", _skill_text()[:-6], "empty skill body"),
    ],
)
def test_registry_fails_closed_on_invalid_metadata(
    tmp_path: Path,
    filename: str,
    content: str,
    message: str,
) -> None:
    (tmp_path / filename).write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        SkillRegistry.from_directory(tmp_path)


def test_registry_rejects_unknown_metadata_and_duplicate_yaml_keys(tmp_path: Path) -> None:
    unknown = _skill_text().replace("risk_level: low", "risk_level: low\nunknown: true")
    (tmp_path / "sample.md").write_text(unknown, encoding="utf-8")
    with pytest.raises(ValueError, match="unknown skill metadata"):
        SkillRegistry.from_directory(tmp_path)

    duplicate = _skill_text().replace("name: sample", "name: sample\nname: sample")
    (tmp_path / "sample.md").write_text(duplicate, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML"):
        SkillRegistry.from_directory(tmp_path)


def test_registry_rejects_duplicate_default_task_mapping(tmp_path: Path) -> None:
    (tmp_path / "first.md").write_text(_skill_text(name="first"), encoding="utf-8")
    (tmp_path / "second.md").write_text(_skill_text(name="second"), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate default task mapping"):
        SkillRegistry.from_directory(tmp_path)


def test_registry_rejects_symlink_and_non_regular_skill_file(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text(_skill_text(name="target"), encoding="utf-8")
    (tmp_path / "link.md").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        SkillRegistry.from_directory(tmp_path)

    (tmp_path / "link.md").unlink()
    target.unlink()
    (tmp_path / "target.md").mkdir()
    with pytest.raises(ValueError, match="regular"):
        SkillRegistry.from_directory(tmp_path)


def test_catalog_is_sorted_hashed_and_does_not_expose_instructions_or_authority(tmp_path: Path) -> None:
    (tmp_path / "zeta.md").write_text(_skill_text(name="zeta", task_types="\n  - zeta_task"), encoding="utf-8")
    (tmp_path / "alpha.md").write_text(_skill_text(name="alpha", task_types="\n  - alpha_task"), encoding="utf-8")
    catalog = SkillRegistry.from_directory(tmp_path).catalog()
    assert catalog["schema_version"] == "document_ops_skill_catalog_v1"
    assert [item["name"] for item in catalog["skills"]] == ["alpha", "zeta"]
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["content_sha256"]) for item in catalog["skills"])
    assert re.fullmatch(r"[0-9a-f]{64}", catalog["catalog_fingerprint"])
    serialized = str(catalog)
    for forbidden in ("body", "source_path", "provider", "approval", "persistence", "external_code"):
        assert forbidden not in serialized
