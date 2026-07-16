"""bundle_expander.py — 사용자 요청 패턴 분석 후 새 번들 자동 생성.

흐름:
  1. RequestPatternStore에서 unmatched 요청 로드
  2. LLM이 패턴 분석 → 번들 정의 JSON 반환
  3. confidence ≥ 0.7이고 built-in 번들과 충돌 없으면:
     - data/auto_bundles/registry.json에 저장
     - data/auto_bundles/{bundle_id}.py (Python 코드, 검토용) 저장
     - 레지스트리 즉시 갱신 (reload_auto_bundles)
     - unmatched 요청 초기화
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.storage.base import atomic_write_text

_log = logging.getLogger("decisiondoc.bundle_expander")

_BUNDLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_SECTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def is_safe_bundle_id(value: Any) -> bool:
    return isinstance(value, str) and _BUNDLE_ID_PATTERN.fullmatch(value) is not None

_PATTERN_PROMPT_TEMPLATE = """\
당신은 문서 요구사항 분석 전문가입니다.
아래는 사용자들이 현재 시스템에서 처리하지 못한 문서 요청 목록입니다:

{request_lines}

이 요청들에서 공통된 문서 유형 패턴을 분석하세요.
감지된 패턴이 명확한 문서 유형을 나타내는 경우에만 detected=true로 설정하세요.
bundle_id는 snake_case로, 한국어 번들이면 _kr로 끝내세요 (예: risk_assessment_kr).
sections는 5개 이상 8개 이하로 구성하세요.

Return ONLY JSON (no markdown fences):
{{
  "detected": bool,
  "bundle_id": "snake_case_bundle_id",
  "bundle_name": "한국어 번들 이름",
  "description": "한 문장 한국어 설명",
  "icon": "이모지",
  "sections": [
    {{"id": "section_id", "title": "한국어 섹션 제목", "required": true}}
  ],
  "confidence": 0.0
}}
"""


class BundleAutoExpander:
    """Analyses unmatched request patterns and auto-generates new bundle specs."""

    def __init__(
        self,
        provider: Any,
        override_store: Any | None = None,
        pattern_store: Any | None = None,
        *,
        data_dir: Path | None = None,
    ) -> None:
        self.provider = provider
        self.override_store = override_store
        self.pattern_store = pattern_store
        self._data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(os.getenv("DATA_DIR", "./data"))
        )
        self._auto_dir = self._data_dir / "auto_bundles"
        self._registry_path = self._auto_dir / "registry.json"

    # ── Main entry point ──────────────────────────────────────────────────

    def analyze_and_expand(
        self,
        *,
        record_provider_usage: Callable[[Any], None] | None = None,
    ) -> dict | None:
        """Analyse unmatched request patterns and auto-generate a bundle if detected.

        Returns:
            Bundle info dict if a new bundle was created, else None.
        """
        from app.config import get_auto_expand_threshold

        self.last_provider_called = False

        if self.pattern_store is None:
            _log.warning("[BundleExpander] pattern_store가 없음 — 분석 건너뜀")
            return None

        threshold = get_auto_expand_threshold()
        unmatched = self.pattern_store.get_unmatched(limit=50)
        if len(unmatched) < threshold:
            _log.info(
                "[BundleExpander] unmatched=%d < threshold=%d — 패턴 분석 건너뜀",
                len(unmatched),
                threshold,
            )
            return None

        # Step 1: Call LLM for pattern analysis
        request_inputs: list[str] = []
        for record in unmatched[:50]:
            raw_input = record.get("raw_input") if isinstance(record, dict) else None
            if isinstance(raw_input, str) and raw_input.strip():
                request_inputs.append(raw_input.strip()[:200])
        if len(request_inputs) < threshold:
            _log.warning(
                "[BundleExpander] 유효한 unmatched 입력=%d < threshold=%d",
                len(request_inputs),
                threshold,
            )
            return None
        request_lines = "\n".join(f"- {raw_input}" for raw_input in request_inputs)
        prompt = _PATTERN_PROMPT_TEMPLATE.format(request_lines=request_lines)

        self.last_provider_called = True
        try:
            raw = self.provider.generate_raw(prompt, request_id="bundle-expander")
        except Exception as exc:
            _log.warning("[BundleExpander] LLM 호출 실패: %s", exc)
            return None
        finally:
            if record_provider_usage is not None:
                record_provider_usage(self.provider)

        # Step 2: Parse JSON response
        detection = self._parse_json_response(raw)
        if detection is None:
            return None

        if detection.get("detected") is not True:
            _log.info(
                "[BundleExpander] 패턴 미감지 (confidence=%r)",
                detection.get("confidence", 0),
            )
            return None

        try:
            confidence = float(detection.get("confidence", 0.0))
        except (TypeError, ValueError):
            _log.warning("[BundleExpander] confidence가 숫자가 아닙니다")
            return None
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            _log.warning("[BundleExpander] confidence 범위가 유효하지 않습니다")
            return None
        if confidence < 0.7:
            _log.info("[BundleExpander] confidence %.2f < 0.7 — 번들 생성 건너뜀", confidence)
            return None

        raw_bundle_id = detection.get("bundle_id")
        bundle_id = raw_bundle_id.strip() if isinstance(raw_bundle_id, str) else ""
        if not is_safe_bundle_id(bundle_id):
            _log.warning(
                "[BundleExpander] 안전하지 않은 bundle_id=%r — 건너뜀",
                bundle_id,
            )
            return None

        # Step 3: Check for conflict with built-in bundles
        from app.bundle_catalog.registry import BUNDLE_REGISTRY
        if bundle_id in BUNDLE_REGISTRY:
            _log.warning(
                "[BundleExpander] '%s'는 이미 존재하는 번들입니다. 건너뜀.", bundle_id
            )
            return None

        sections = self._validate_sections(detection.get("sections"))
        if sections is None:
            return None

        # Step 4: Build and persist registry record
        record = {
            "bundle_id": bundle_id,
            "name_ko": self._clean_text(detection.get("bundle_name"), bundle_id, 120),
            "name_en": bundle_id.replace("_", " ").title(),
            "description_ko": self._clean_text(detection.get("description"), "", 300),
            "icon": self._clean_text(detection.get("icon"), "📄", 16),
            "confidence": confidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "auto_expand",
            "sections": sections,
        }

        self._save_to_registry(bundle_id, record)
        self._save_python_code(bundle_id, record)

        # Step 5: Clear unmatched requests
        removed = self.pattern_store.clear_unmatched()
        _log.info(
            "[BundleExpander] 번들 '%s' 생성 완료 (confidence=%.2f), unmatched %d건 초기화",
            bundle_id,
            confidence,
            removed,
        )

        # Step 6: Reload registry so the new bundle is immediately available
        try:
            from app.bundle_catalog.registry import reload_auto_bundles
            reload_auto_bundles()
        except Exception as exc:
            _log.warning("[BundleExpander] 레지스트리 갱신 실패 (무시): %s", exc)

        return {
            "bundle_id": bundle_id,
            "name_ko": record["name_ko"],
            "confidence": confidence,
            "sections": record["sections"],
            "created_at": record["created_at"],
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    def _parse_json_response(self, raw: Any) -> dict | None:
        """Parse LLM JSON response, stripping markdown fences if present."""
        if not isinstance(raw, str):
            _log.warning("[BundleExpander] LLM 응답이 문자열이 아닙니다")
            return None
        text = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.rstrip().endswith("```"):
                text = text[: text.rfind("```")]
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            _log.warning(
                "[BundleExpander] LLM 응답 파싱 실패: %s | raw=%r", exc, raw[:300]
            )
            return None
        if not isinstance(parsed, dict):
            _log.warning("[BundleExpander] LLM 응답이 JSON object가 아닙니다")
            return None
        return parsed

    @staticmethod
    def _clean_text(value: Any, fallback: str, limit: int) -> str:
        if not isinstance(value, str):
            return fallback
        cleaned = value.strip()
        return cleaned[:limit] if cleaned else fallback

    @staticmethod
    def _validate_sections(value: Any) -> list[dict[str, Any]] | None:
        if not isinstance(value, list) or not 5 <= len(value) <= 8:
            _log.warning("[BundleExpander] sections는 5~8개여야 합니다")
            return None

        sections: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                _log.warning("[BundleExpander] section 항목이 object가 아닙니다")
                return None
            section_id = item.get("id")
            title = item.get("title")
            required = item.get("required", True)
            if (
                not isinstance(section_id, str)
                or not _SECTION_ID_PATTERN.fullmatch(section_id)
                or section_id in seen_ids
                or not isinstance(title, str)
                or not title.strip()
                or not isinstance(required, bool)
            ):
                _log.warning("[BundleExpander] 유효하지 않은 section=%r", item)
                return None
            seen_ids.add(section_id)
            sections.append({
                "id": section_id,
                "title": title.strip()[:120],
                "required": required,
            })
        return sections

    def _save_to_registry(self, bundle_id: str, record: dict) -> None:
        """Append or update the auto-bundle registry JSON file."""
        self._auto_dir.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if self._registry_path.exists():
            try:
                loaded = json.loads(self._registry_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
                else:
                    _log.warning("[BundleExpander] registry가 JSON object가 아닙니다")
            except (OSError, json.JSONDecodeError):
                existing = {}
        existing[bundle_id] = record
        atomic_write_text(
            self._registry_path,
            json.dumps(existing, ensure_ascii=False, indent=2),
        )

    def _save_python_code(self, bundle_id: str, record: dict) -> None:
        """Save human-readable BundleSpec Python code for review."""
        self._auto_dir.mkdir(parents=True, exist_ok=True)
        code = self._generate_python_code(record)
        py_path = self._auto_dir / f"{bundle_id}.py"
        atomic_write_text(py_path, code)

    @staticmethod
    def _generate_python_code(record: dict) -> str:
        """Generate BundleSpec Python source code from a registry record (for review)."""
        bundle_id = record["bundle_id"]
        name_ko = record.get("name_ko", bundle_id)
        name_en = record.get("name_en", bundle_id.replace("_", " ").title())
        description_ko = record.get("description_ko", record.get("description", ""))
        icon = record.get("icon", "📄")
        sections = record.get("sections", [])
        created_at = record.get("created_at", "")
        const_name = bundle_id.upper()
        prompt_hint = (
            f"당신은 {name_ko} 문서 작성 전문가입니다.\n"
            "각 섹션의 section_title 필드에 한국어 섹션명을 명확히 작성하세요.\n"
            "summary는 해당 섹션의 핵심 내용을 2-3문장으로 작성하세요.\n"
            "items는 구체적인 세부 사항을 5개 이상 작성하세요.\n"
            "모든 내용을 한국어로 작성하세요."
        )

        doc_parts = []
        for section in sections:
            sid = section["id"]
            stitle = section.get("title", sid)
            doc_parts.append(
                f'        DocumentSpec(\n'
                f"            key={sid!r},\n"
                f'            template_file="auto_bundle/section.md.j2",\n'
                f'            json_schema={{\n'
                f'                "type": "object",\n'
                f'                "required": ["section_title", "summary", "items"],\n'
                f'                "properties": {{\n'
                f'                    "section_title": {{"type": "string"}},\n'
                f'                    "summary": {{"type": "string"}},\n'
                f'                    "items": {{"type": "array", "items": {{"type": "string"}}}},\n'
                f'                }},\n'
                f'            }},\n'
                f'            stabilizer_defaults={{\n'
                f'                "section_title": {stitle!r},\n'
                f'                "summary": "",\n'
                f'                "items": [],\n'
                f'            }},\n'
                f'            lint_headings=["## 개요", "## 세부 내용"],\n'
                f'            validator_headings=["## 개요", "## 세부 내용"],\n'
                f'            critical_non_empty_headings=["## 개요"],\n'
                f'        )'
            )

        docs_str = ",\n".join(doc_parts)
        return (
            f"# Auto-generated by BundleAutoExpander on {created_at}\n"
            f"# Review and edit before promoting to app/bundle_catalog/bundles/\n"
            f"from app.bundle_catalog.spec import BundleSpec, DocumentSpec\n\n"
            f"{const_name} = BundleSpec(\n"
            f"    id={bundle_id!r},\n"
            f"    name_ko={name_ko!r},\n"
            f"    name_en={name_en!r},\n"
            f"    description_ko={description_ko!r},\n"
            f"    icon={icon!r},\n"
            f'    prompt_language="ko",\n'
            f"    prompt_hint={prompt_hint!r},\n"
            f'    category="work",\n'
            f'    docs=[\n'
            f'{docs_str}\n'
            f'    ],\n'
            f')\n'
        )
