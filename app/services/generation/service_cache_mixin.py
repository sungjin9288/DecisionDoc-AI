"""Bundle cache path/TTL/read/write helpers mixin."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


class GenerationCacheMixin:
    """File-based bundle cache: TTL check, path derivation, atomic read/write, clear."""

    def _is_cache_fresh(self, cache_path: Path) -> bool:
        """Return True if the cache file is within the configured TTL.

        TTL is controlled by DECISIONDOC_CACHE_TTL_HOURS (default 24).
        Set to 0 for permanent cache (no expiry).
        """
        ttl_hours = int(os.getenv("DECISIONDOC_CACHE_TTL_HOURS", "24"))
        if ttl_hours <= 0:
            return True  # 0 → permanent cache
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        return age_hours < ttl_hours

    def _cache_path(self, provider_name: str, schema_version: str, payload: dict[str, Any]) -> Path:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = f"{provider_name}:{schema_version}:{canonical}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _try_read_cache(self, cache_path: Path) -> dict[str, Any] | None:
        try:
            text = cache_path.read_text(encoding="utf-8")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache_atomic(self, cache_path: Path, bundle: dict[str, Any]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(bundle, ensure_ascii=False, indent=2)
        tmp_path = cache_path.with_name(f"{cache_path.name}.tmp.{uuid4().hex}")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, cache_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def clear_cache(self) -> int:
        """Delete all cached bundles. Returns the number of files removed."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        return count
