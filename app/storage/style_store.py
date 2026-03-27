"""app/storage/style_store.py — Tenant-scoped custom tone & style profiles.

Storage: data/tenants/{tenant_id}/style_profiles.json
Thread-safe via threading.Lock per store instance.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.storage.base import BaseJsonStore

_log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Data models ────────────────────────────────────────────────────────────────


@dataclass
class ToneGuide:
    """User-written tone instructions for document generation."""

    formality: str = ""          # "경어체" | "해요체" | "합쇼체" | "혼용"
    density: str = ""            # "간결하게" | "보통" | "상세하게"
    perspective: str = ""        # "1인칭" | "3인칭" | "기관명칭" | "혼용"
    custom_rules: list[str] = field(default_factory=list)    # free-form rules
    forbidden_words: list[str] = field(default_factory=list) # words to avoid
    preferred_words: list[str] = field(default_factory=list) # words to prefer


@dataclass
class StyleExample:
    """Style patterns extracted from an uploaded document."""

    example_id: str
    source_filename: str
    bundle_id: str | None           # None = applies to all bundles
    extracted_patterns: list[str]   # LLM-extracted style patterns
    sample_sentences: list[str]     # representative sentences from the doc
    uploaded_at: str
    uploaded_by: str                # user_id of the uploader


@dataclass
class StyleProfile:
    """A named collection of tone preferences and style examples."""

    profile_id: str
    tenant_id: str
    name: str
    description: str
    tone_guide: ToneGuide
    examples: list[StyleExample]
    bundle_overrides: dict[str, ToneGuide]  # bundle_id → specific tone
    is_default: bool
    created_by: str
    created_at: str
    updated_at: str


# ── Serialization helpers ──────────────────────────────────────────────────────


def _tone_from_dict(d: dict) -> ToneGuide:
    return ToneGuide(
        formality=d.get("formality", ""),
        density=d.get("density", ""),
        perspective=d.get("perspective", ""),
        custom_rules=d.get("custom_rules", []),
        forbidden_words=d.get("forbidden_words", []),
        preferred_words=d.get("preferred_words", []),
    )


def _example_from_dict(d: dict) -> StyleExample:
    return StyleExample(
        example_id=d["example_id"],
        source_filename=d.get("source_filename", ""),
        bundle_id=d.get("bundle_id"),
        extracted_patterns=d.get("extracted_patterns", []),
        sample_sentences=d.get("sample_sentences", []),
        uploaded_at=d.get("uploaded_at", ""),
        uploaded_by=d.get("uploaded_by", ""),
    )


def _profile_from_dict(d: dict) -> StyleProfile:
    return StyleProfile(
        profile_id=d["profile_id"],
        tenant_id=d.get("tenant_id", ""),
        name=d.get("name", ""),
        description=d.get("description", ""),
        tone_guide=_tone_from_dict(d.get("tone_guide") or {}),
        examples=[_example_from_dict(e) for e in d.get("examples", [])],
        bundle_overrides={
            k: _tone_from_dict(v)
            for k, v in (d.get("bundle_overrides") or {}).items()
        },
        is_default=d.get("is_default", False),
        created_by=d.get("created_by", ""),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def _profile_to_dict(p: StyleProfile) -> dict:
    return {
        "profile_id": p.profile_id,
        "tenant_id": p.tenant_id,
        "name": p.name,
        "description": p.description,
        "tone_guide": asdict(p.tone_guide),
        "examples": [asdict(e) for e in p.examples],
        "bundle_overrides": {k: asdict(v) for k, v in p.bundle_overrides.items()},
        "is_default": p.is_default,
        "created_by": p.created_by,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


# ── StyleStore ────────────────────────────────────────────────────────────────


class StyleStore(BaseJsonStore):
    """Thread-safe, file-backed style profile store scoped to a single tenant."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__()
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        tenant_dir = data_dir / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "style_profiles.json"
        if not self._path.exists():
            self._save({})

    def _get_path(self) -> Path:
        return self._path

    # ── public API ─────────────────────────────────────────────────────────

    def create(
        self,
        tenant_id: str,
        name: str,
        description: str,
        created_by: str,
    ) -> StyleProfile:
        """Create a new (empty) style profile."""
        profile = StyleProfile(
            profile_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=name,
            description=description,
            tone_guide=ToneGuide(),
            examples=[],
            bundle_overrides={},
            is_default=False,
            created_by=created_by,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        with self._lock:
            data = self._load()
            # Auto-set default when this is the first profile
            if not data:
                profile.is_default = True
            data[profile.profile_id] = _profile_to_dict(profile)
            self._save(data)
        return profile

    def get(self, profile_id: str) -> StyleProfile | None:
        with self._lock:
            data = self._load()
        raw = data.get(profile_id)
        return _profile_from_dict(raw) if raw else None

    def get_default(self, tenant_id: str) -> StyleProfile | None:
        """Return the default profile for this tenant, or None if none exists."""
        with self._lock:
            data = self._load()
        for raw in data.values():
            if raw.get("tenant_id") == tenant_id and raw.get("is_default"):
                return _profile_from_dict(raw)
        return None

    def list_by_tenant(self, tenant_id: str) -> list[StyleProfile]:
        with self._lock:
            data = self._load()
        return [
            _profile_from_dict(v)
            for v in data.values()
            if v.get("tenant_id") == tenant_id
        ]

    def set_default(self, profile_id: str) -> None:
        """Mark *profile_id* as the default; clear the flag on all others."""
        with self._lock:
            data = self._load()
            for pid, raw in data.items():
                raw["is_default"] = pid == profile_id
                raw["updated_at"] = _now_iso()
            self._save(data)

    def update_tone_guide(self, profile_id: str, tone_guide: ToneGuide) -> StyleProfile:
        with self._lock:
            data = self._load()
            if profile_id not in data:
                raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")
            data[profile_id]["tone_guide"] = asdict(tone_guide)
            data[profile_id]["updated_at"] = _now_iso()
            self._save(data)
            return _profile_from_dict(data[profile_id])

    def set_bundle_override(
        self, profile_id: str, bundle_id: str, tone_guide: ToneGuide
    ) -> None:
        with self._lock:
            data = self._load()
            if profile_id not in data:
                raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")
            data[profile_id].setdefault("bundle_overrides", {})[bundle_id] = asdict(
                tone_guide
            )
            data[profile_id]["updated_at"] = _now_iso()
            self._save(data)

    def remove_bundle_override(self, profile_id: str, bundle_id: str) -> None:
        with self._lock:
            data = self._load()
            if profile_id not in data:
                raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")
            data[profile_id].get("bundle_overrides", {}).pop(bundle_id, None)
            data[profile_id]["updated_at"] = _now_iso()
            self._save(data)

    def add_example(self, profile_id: str, example: StyleExample) -> None:
        with self._lock:
            data = self._load()
            if profile_id not in data:
                raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")
            data[profile_id].setdefault("examples", []).append(asdict(example))
            data[profile_id]["updated_at"] = _now_iso()
            self._save(data)

    def remove_example(self, profile_id: str, example_id: str) -> None:
        with self._lock:
            data = self._load()
            if profile_id not in data:
                raise ValueError(f"프로필을 찾을 수 없습니다: {profile_id}")
            data[profile_id]["examples"] = [
                e for e in data[profile_id].get("examples", [])
                if e["example_id"] != example_id
            ]
            data[profile_id]["updated_at"] = _now_iso()
            self._save(data)

    def delete(self, profile_id: str) -> None:
        with self._lock:
            data = self._load()
            data.pop(profile_id, None)
            self._save(data)

    def is_system(self, profile_id: str) -> bool:
        """Return True if this profile is a built-in system profile."""
        with self._lock:
            data = self._load()
        return bool(data.get(profile_id, {}).get("is_system", False))

    def initialize_defaults(self, tenant_id: str) -> None:
        """Load default system style profiles on first startup.

        Idempotent — only adds profiles whose style_id is not already present.
        """
        import copy
        from app.storage.default_styles import DEFAULT_STYLE_PROFILES

        with self._lock:
            data = self._load()
            existing_ids = set(data.keys())

            added = 0
            for profile in DEFAULT_STYLE_PROFILES:
                sid = profile["style_id"]
                if sid in existing_ids:
                    continue
                tg = profile.get("tone_guide", {})
                now = datetime.now(timezone.utc).isoformat()
                entry: dict = {
                    "profile_id": sid,
                    "tenant_id": tenant_id,
                    "name": profile["name"],
                    "description": profile["description"],
                    "tone_guide": {
                        "formality": tg.get("formality", ""),
                        "density": tg.get("density", ""),
                        "perspective": tg.get("perspective", ""),
                        "custom_rules": copy.copy(profile.get("custom_rules", [])),
                        "forbidden_words": copy.copy(profile.get("forbidden_expressions", [])),
                        "preferred_words": [],
                    },
                    "examples": [],
                    "bundle_overrides": {},
                    "is_default": profile.get("is_default", False),
                    "is_system": True,
                    "few_shot_example": profile.get("few_shot_example", ""),
                    "avatar_color": profile.get("avatar_color", ""),
                    "created_by": "system",
                    "created_at": now,
                    "updated_at": now,
                }
                data[sid] = entry
                added += 1

            if added:
                self._save(data)
                _log.info("[StyleStore] Loaded %d default style profiles for tenant=%s", added, tenant_id)


# ── per-tenant singleton factory ───────────────────────────────────────────────

_style_stores: dict[str, StyleStore] = {}
_ss_lock = threading.Lock()


def get_style_store(tenant_id: str) -> StyleStore:
    """Return a shared StyleStore instance for the given tenant."""
    with _ss_lock:
        if tenant_id not in _style_stores:
            _style_stores[tenant_id] = StyleStore(tenant_id)
        return _style_stores[tenant_id]
