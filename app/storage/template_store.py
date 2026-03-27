"""TemplateStore — saves/loads user document form templates."""
from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class TemplateEntry:
    template_id: str
    tenant_id: str
    user_id: str
    name: str
    bundle_id: str
    bundle_name: str
    form_data: dict = field(default_factory=dict)  # title, goal, background, constraints, industry
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    use_count: int = 0


class TemplateStore:
    """Stores document form templates as JSONL per tenant."""

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._lock = threading.Lock()
        data_dir = os.getenv("DATA_DIR", "data")
        self._path = Path(data_dir) / "tenants" / tenant_id / "templates.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        entries = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _save(self, entries: list[dict]) -> None:
        tmp = self._path.with_name(f"{self._path.name}.tmp.{uuid.uuid4().hex}")
        with tmp.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            f.flush()
            import os as _os
            _os.fsync(f.fileno())
        import os as _os
        _os.replace(tmp, self._path)

    def add(self, entry: TemplateEntry) -> None:
        with self._lock:
            entries = self._load()
            entries.append(asdict(entry))
            self._save(entries)

    def list_for_user(self, user_id: str) -> list[dict]:
        with self._lock:
            entries = self._load()
        return [e for e in entries if e.get("user_id") == user_id]

    def get(self, template_id: str, user_id: str) -> dict | None:
        with self._lock:
            entries = self._load()
        for e in entries:
            if e.get("template_id") == template_id and e.get("user_id") == user_id:
                return e
        return None

    def delete(self, template_id: str, user_id: str) -> bool:
        with self._lock:
            entries = self._load()
            new = [e for e in entries if not (e.get("template_id") == template_id and e.get("user_id") == user_id)]
            if len(new) == len(entries):
                return False
            self._save(new)
        return True

    def increment_use_count(self, template_id: str, user_id: str) -> None:
        with self._lock:
            entries = self._load()
            for e in entries:
                if e.get("template_id") == template_id and e.get("user_id") == user_id:
                    e["use_count"] = e.get("use_count", 0) + 1
                    e["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    break
            self._save(entries)
