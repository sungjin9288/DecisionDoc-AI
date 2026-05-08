"""Curated local skill registry for DecisionDoc agents."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from app.agents.schemas import DocumentOpsSkill


class SkillNotFoundError(KeyError):
    """Raised when a requested skill or task mapping is unavailable."""


class SkillRegistry:
    """Loads first-party Markdown skills without executing arbitrary code."""

    def __init__(self, skills: Iterable[DocumentOpsSkill] | None = None) -> None:
        self._skills: dict[str, DocumentOpsSkill] = {}
        for skill in skills or []:
            self.register(skill)

    @classmethod
    def from_directory(cls, skills_dir: str | Path | None = None) -> "SkillRegistry":
        root = Path(skills_dir) if skills_dir is not None else Path(__file__).with_name("skills")
        skills = [_load_skill(path) for path in sorted(root.glob("*.md"))]
        return cls(skills)

    def register(self, skill: DocumentOpsSkill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"duplicate skill name: {skill.name}")
        self._skills[skill.name] = skill

    def list_skills(self) -> list[DocumentOpsSkill]:
        return sorted(self._skills.values(), key=lambda item: item.name)

    def get(self, name: str) -> DocumentOpsSkill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillNotFoundError(f"unknown skill: {name}") from exc

    def select(self, task_type: str, *, preferred_name: str | None = None) -> DocumentOpsSkill:
        if preferred_name:
            skill = self.get(preferred_name)
            if task_type not in skill.task_types:
                raise SkillNotFoundError(f"skill {preferred_name} does not support task_type={task_type}")
            return skill
        for skill in self.list_skills():
            if task_type in skill.task_types:
                return skill
        raise SkillNotFoundError(f"no skill registered for task_type={task_type}")


_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)\Z", re.DOTALL)


def _load_skill(path: Path) -> DocumentOpsSkill:
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError(f"skill file is missing front matter: {path}")
    metadata = _parse_front_matter(match.group("meta"))
    body = match.group("body").strip()
    task_types = _as_string_list(metadata.get("task_types"))
    return DocumentOpsSkill(
        name=str(metadata.get("name") or path.stem).strip(),
        version=str(metadata.get("version") or "0.1.0").strip(),
        title=str(metadata.get("title") or path.stem).strip(),
        description=str(metadata.get("description") or "").strip(),
        task_types=task_types,
        risk_level=str(metadata.get("risk_level") or "low").strip(),
        body=body,
        source_path=str(path),
    )


def _parse_front_matter(text: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        line = raw_line.rstrip()
        stripped = line.strip()
        if current_key and line[:1].isspace() and stripped.startswith("-"):
            value = stripped[1:].strip().strip('"').strip("'")
            items = metadata.setdefault(current_key, [])
            if not isinstance(items, list):
                raise ValueError(f"front matter key is not a list: {current_key}")
            items.append(value)
            continue
        if ":" not in line:
            raise ValueError(f"invalid front matter line: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            metadata[key] = []
            current_key = key
            continue
        current_key = None
        metadata[key] = _parse_scalar(value)
    return metadata


def _parse_scalar(value: str) -> object:
    value = value.strip().strip('"').strip("'")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip('"').strip("'") for part in inner.split(",") if part.strip()]
    return value


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
