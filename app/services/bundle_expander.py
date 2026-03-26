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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.bundle_expander")

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
    ) -> None:
        self.provider = provider
        self.override_store = override_store
        self.pattern_store = pattern_store
        self._data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self._auto_dir = self._data_dir / "auto_bundles"
        self._registry_path = self._auto_dir / "registry.json"

    # ── Main entry point ──────────────────────────────────────────────────

    def analyze_and_expand(self) -> dict | None:
        """Analyse unmatched request patterns and auto-generate a bundle if detected.

        Returns:
            Bundle info dict if a new bundle was created, else None.
        """
        from app.config import get_auto_expand_threshold

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
        request_lines = "\n".join(f"- {r['raw_input']}" for r in unmatched[:50])
        prompt = _PATTERN_PROMPT_TEMPLATE.format(request_lines=request_lines)

        try:
            raw = self.provider.generate_raw(prompt, request_id="bundle-expander")
        except Exception as exc:
            _log.warning("[BundleExpander] LLM 호출 실패: %s", exc)
            return None

        # Step 2: Parse JSON response
        detection = self._parse_json_response(raw)
        if detection is None:
            return None

        if not detection.get("detected", False):
            _log.info(
                "[BundleExpander] 패턴 미감지 (confidence=%.2f)",
                detection.get("confidence", 0),
            )
            return None

        confidence = float(detection.get("confidence", 0.0))
        if confidence < 0.7:
            _log.info("[BundleExpander] confidence %.2f < 0.7 — 번들 생성 건너뜀", confidence)
            return None

        bundle_id = (detection.get("bundle_id") or "").strip()
        if not bundle_id:
            _log.warning("[BundleExpander] bundle_id가 비어 있음 — 건너뜀")
            return None

        # Step 3: Check for conflict with built-in bundles
        from app.bundle_catalog.registry import BUNDLE_REGISTRY
        if bundle_id in BUNDLE_REGISTRY:
            _log.warning(
                "[BundleExpander] '%s'는 이미 존재하는 번들입니다. 건너뜀.", bundle_id
            )
            return None

        # Step 4: Build and persist registry record
        record = {
            "bundle_id": bundle_id,
            "name_ko": detection.get("bundle_name", bundle_id),
            "name_en": bundle_id.replace("_", " ").title(),
            "description_ko": detection.get("description", ""),
            "icon": detection.get("icon", "📄"),
            "confidence": confidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "auto_expand",
            "sections": detection.get("sections", []),
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

    def _parse_json_response(self, raw: str) -> dict | None:
        """Parse LLM JSON response, stripping markdown fences if present."""
        text = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.rstrip().endswith("```"):
                text = text[: text.rfind("```")]
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            _log.warning(
                "[BundleExpander] LLM 응답 파싱 실패: %s | raw=%r", exc, raw[:300]
            )
            return None

    def _save_to_registry(self, bundle_id: str, record: dict) -> None:
        """Append or update the auto-bundle registry JSON file."""
        self._auto_dir.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if self._registry_path.exists():
            try:
                existing = json.loads(self._registry_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        existing[bundle_id] = record
        self._registry_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_python_code(self, bundle_id: str, record: dict) -> None:
        """Save human-readable BundleSpec Python code for review."""
        self._auto_dir.mkdir(parents=True, exist_ok=True)
        code = self._generate_python_code(record)
        py_path = self._auto_dir / f"{bundle_id}.py"
        py_path.write_text(code, encoding="utf-8")

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

        doc_parts = []
        for section in sections:
            sid = section["id"]
            stitle = section.get("title", sid)
            doc_parts.append(
                f'        DocumentSpec(\n'
                f'            key="{sid}",\n'
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
                f'                "section_title": "{stitle}",\n'
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
            f'    id="{bundle_id}",\n'
            f'    name_ko="{name_ko}",\n'
            f'    name_en="{name_en}",\n'
            f'    description_ko="{description_ko}",\n'
            f'    icon="{icon}",\n'
            f'    prompt_language="ko",\n'
            f'    prompt_hint=(\n'
            f'        "당신은 {name_ko} 문서 작성 전문가입니다.\\n"\n'
            f'        "각 섹션의 section_title 필드에 한국어 섹션명을 명확히 작성하세요.\\n"\n'
            f'        "summary는 해당 섹션의 핵심 내용을 2-3문장으로 작성하세요.\\n"\n'
            f'        "items는 구체적인 세부 사항을 5개 이상 작성하세요.\\n"\n'
            f'        "모든 내용을 한국어로 작성하세요."\n'
            f'    ),\n'
            f'    category="work",\n'
            f'    docs=[\n'
            f'{docs_str}\n'
            f'    ],\n'
            f')\n'
        )
