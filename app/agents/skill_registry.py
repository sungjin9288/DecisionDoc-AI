"""Curated, read-only registry for first-party DocumentOps skills."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.agents.schemas import DocumentOpsSkill


class SkillNotFoundError(KeyError):
    """Raised when a requested skill or task mapping is unavailable."""


class SkillRegistry:
    """Load first-party Markdown skills without executing arbitrary code."""

    def __init__(self, skills: Iterable[DocumentOpsSkill] | None = None) -> None:
        self._skills: dict[str, DocumentOpsSkill] = {}
        for skill in skills or []:
            self.register(skill)

    @classmethod
    def from_directory(cls, skills_dir: str | Path | None = None) -> "SkillRegistry":
        root = Path(skills_dir) if skills_dir is not None else Path(__file__).with_name("skills")
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise ValueError(f"skill registry directory is not a regular directory: {root}")
        paths = sorted(root.iterdir(), key=lambda item: item.name)
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"symlink skill file is not allowed: {path.name}")
            if path.suffix == ".md" and not path.is_file():
                raise ValueError(f"skill file is not regular: {path.name}")
        skills = [_load_skill(path) for path in paths if path.suffix == ".md"]
        names = [skill.name for skill in skills]
        if len(names) != len(set(names)):
            raise ValueError("duplicate skill name")
        return cls(skills)

    def register(self, skill: DocumentOpsSkill) -> None:
        if not _SHA256_RE.fullmatch(skill.content_sha256):
            raise ValueError(f"content_sha256 must be lowercase 64-hex: {skill.name}")
        source_name = Path(skill.source_path).stem
        if Path(skill.source_path).suffix == ".md" and skill.name != source_name:
            raise ValueError(f"unsafe or mismatched skill name: {skill.name!r}")
        if not _SAFE_NAME_RE.fullmatch(skill.name):
            raise ValueError(f"unsafe or mismatched skill name: {skill.name!r}")
        if len(skill.task_types) != len(set(skill.task_types)):
            raise ValueError(f"duplicate task type in skill: {skill.name}")
        if not skill.task_types or any(not task_type.strip() for task_type in skill.task_types):
            raise ValueError(f"empty task type in skill: {skill.name}")
        if any(not _SAFE_TASK_TYPE_RE.fullmatch(task_type) for task_type in skill.task_types):
            raise ValueError(f"unsafe task type in skill: {skill.name}")
        if skill.name in self._skills:
            raise ValueError(f"duplicate skill name: {skill.name}")
        for existing in self._skills.values():
            overlap = set(existing.task_types).intersection(skill.task_types)
            if overlap:
                task_type = sorted(overlap)[0]
                raise ValueError(f"duplicate default task mapping: {task_type}")
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

    def catalog(self) -> dict[str, Any]:
        """Return a deterministic public catalog with no executable content."""
        skills = [
            {
                "name": skill.name,
                "version": skill.version,
                "title": skill.title,
                "description": skill.description,
                "task_types": list(skill.task_types),
                "risk_level": skill.risk_level,
                "content_sha256": skill.content_sha256,
            }
            for skill in self.list_skills()
        ]
        payload = {"schema_version": "document_ops_skill_catalog_v1", "skills": skills}
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {**payload, "catalog_fingerprint": fingerprint}


_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(?P<meta>.*?)\n---[ \t]*\n(?P<body>.*)\Z", re.DOTALL)
_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SAFE_TASK_TYPE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_METADATA = {"name", "version", "title", "description", "task_types", "risk_level"}
_ALLOWED_RISK_LEVELS = {"low", "medium", "high"}


def _load_skill(path: Path) -> DocumentOpsSkill:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"skill file is not a regular file: {path}")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError(f"skill file is missing front matter: {path}")
    metadata = _parse_front_matter(match.group("meta"))
    body = match.group("body").strip()
    name = _required_string(metadata, "name")
    if not _SAFE_NAME_RE.fullmatch(name):
        raise ValueError(f"unsafe or mismatched skill name: {name!r}")
    version_value = metadata.get("version")
    version = version_value.strip() if isinstance(version_value, str) else ""
    version_match = _SEMVER_RE.fullmatch(version) if version else None
    prerelease = version_match.group(4) if version_match else None
    if (
        not version_match
        or any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in (prerelease or "").split("."))
    ):
        raise ValueError(f"invalid semantic version: {version!r}")
    title = _required_string(metadata, "title")
    description = _required_string(metadata, "description")
    task_types = _as_string_list(metadata.get("task_types"))
    if not task_types:
        raise ValueError(f"empty task_types: {path.name}")
    if len(task_types) != len(set(task_types)):
        raise ValueError(f"duplicate task type: {path.name}")
    if any(not task_type.strip() for task_type in task_types):
        raise ValueError(f"empty task type: {path.name}")
    if any(not _SAFE_TASK_TYPE_RE.fullmatch(task_type) for task_type in task_types):
        raise ValueError(f"unsafe task type: {path.name}")
    risk_level = _required_string(metadata, "risk_level")
    if risk_level not in _ALLOWED_RISK_LEVELS:
        raise ValueError(f"unsupported risk level: {risk_level!r}")
    if not body:
        raise ValueError(f"empty skill body: {path.name}")
    content_sha256 = hashlib.sha256(raw).hexdigest()
    if not _SHA256_RE.fullmatch(content_sha256):
        raise ValueError(f"invalid content_sha256: {path.name}")
    return DocumentOpsSkill(
        name=name,
        version=version,
        title=title,
        description=description,
        task_types=task_types,
        risk_level=risk_level,
        body=body,
        source_path=str(path),
        content_sha256=content_sha256,
    )


def _parse_front_matter(text: str) -> dict[str, object]:
    loader = _StrictSafeLoader(text)
    try:
        metadata = loader.get_single_data()
    except (yaml.YAMLError, TypeError) as exc:
        raise ValueError("invalid YAML front matter") from exc
    finally:
        loader.dispose()
    if not isinstance(metadata, dict):
        raise ValueError("front matter must be a YAML mapping")
    unknown = set(metadata).difference(_ALLOWED_METADATA)
    if unknown:
        raise ValueError(f"unknown skill metadata: {sorted(map(str, unknown))}")
    return metadata


class _StrictSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _StrictSafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError("mapping", node.start_mark, f"duplicate key: {key}", key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _required_string(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"empty or invalid metadata: {key}")
    return value.strip()


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    if any(not isinstance(item, str) for item in value):
        raise ValueError("task_types must be a list of strings")
    return [item.strip() for item in value]
