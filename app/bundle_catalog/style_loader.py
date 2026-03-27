"""style_loader.py — 스타일 가이드 로드 및 프롬프트 텍스트 생성.

앱 시작 시 한 번 로드되며, build_bundle_prompt()에서 호출됩니다.
스타일 가이드 파일이 없거나 PyYAML 미설치 시 빈 문자열 반환 (graceful degradation).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.style_loader")

_STYLE_GUIDE_PATH = Path(__file__).parent / "style_guide.yaml"


@lru_cache(maxsize=1)
def _load_style_guide() -> dict[str, Any]:
    """YAML 파일 로드 (최초 1회만, 이후 캐시 반환)."""
    try:
        import yaml
    except ImportError:
        _log.warning("PyYAML 미설치 — 스타일 가이드 비활성화 (pip install PyYAML)")
        return {}
    try:
        with _STYLE_GUIDE_PATH.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        _log.warning("style_guide.yaml 미존재 — 스타일 가이드 비활성화")
        return {}
    except Exception as e:
        _log.error("style_guide.yaml 로드 실패: %s", e)
        return {}


def get_style_prompt(bundle_id: str, language: str = "ko") -> str:
    """번들과 언어에 맞는 스타일 가이드 프롬프트 텍스트 반환.

    Returns:
        AI 프롬프트에 삽입할 스타일 규칙 텍스트.
        스타일 가이드 미로드 시 빈 문자열 반환 (기존 동작 유지).
    """
    guide = _load_style_guide()
    if not guide:
        return ""

    lines: list[str] = []

    if language == "ko":
        lines.append("=== 문서 작성 스타일 규칙 (반드시 준수) ===")
    else:
        lines.append("=== Document Style Rules (strictly follow) ===")

    global_cfg = guide.get("global", {})

    # 톤 규칙
    tone = global_cfg.get("tone", {})
    if language == "ko":
        if tone.get("formality"):
            lines.append(f"• 톤: {tone['formality']}")
        if tone.get("tense"):
            lines.append(f"• 시제: {tone['tense']}")
    else:
        if tone.get("formality"):
            lines.append(f"• Tone: {tone['formality']}")

    # 문장 스타일 (최대 3개)
    sentence_rules = global_cfg.get("sentence_style", [])
    if sentence_rules:
        label = "• 문장 원칙:" if language == "ko" else "• Sentence principles:"
        lines.append(label)
        for rule in sentence_rules[:3]:
            lines.append(f"  - {rule}")

    # 수치/데이터 (최대 2개)
    number_rules = global_cfg.get("numbers_and_data", [])
    if number_rules:
        label = "• 수치/데이터:" if language == "ko" else "• Numbers/data:"
        lines.append(label)
        for rule in number_rules[:2]:
            lines.append(f"  - {rule}")

    # 금지 표현 (최대 4개)
    prohibited = global_cfg.get("prohibited_expressions", [])
    if prohibited:
        label = "• 금지 표현 (절대 사용 금지):" if language == "ko" else "• Prohibited expressions:"
        lines.append(label)
        for expr in prohibited[:4]:
            lines.append(f"  ✗ {expr}")

    # 언어별 추가 규칙
    lang_cfg = guide.get("language", {}).get(language, {})
    if lang_cfg and language == "ko":
        if lang_cfg.get("honorifics"):
            lines.append(f"• 어투: {lang_cfg['honorifics']}")
        if lang_cfg.get("list_ending"):
            lines.append(f"• 목록 형식: {lang_cfg['list_ending']}")
    elif lang_cfg and language == "en":
        if lang_cfg.get("voice"):
            lines.append(f"• Voice: {lang_cfg['voice']}")

    # 번들별 특화 규칙 (최대 3개)
    bundle_rules = (
        guide.get("bundle_overrides", {})
        .get(bundle_id, {})
        .get("extra_rules", [])
    )
    if bundle_rules:
        label = f"• '{bundle_id}' 번들 특화 규칙:" if language == "ko" else f"• '{bundle_id}' bundle-specific:"
        lines.append(label)
        for rule in bundle_rules[:3]:
            lines.append(f"  - {rule}")

    lines.append("=== 스타일 규칙 끝 ===" if language == "ko" else "=== End of Style Rules ===")

    return "\n".join(lines)


def reload_style_guide() -> None:
    """캐시 초기화 — 테스트 또는 핫-리로드 용도."""
    _load_style_guide.cache_clear()
