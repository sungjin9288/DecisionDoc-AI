"""app/routers/generate/__init__.py — Generate endpoints facade.

Split from the former app/routers/generate.py (2,170 lines) into domain-focused
sub-modules under this package (M5 milestone). Each sub-module owns one
APIRouter; this file aggregates them behind a single `router` symbol so
`app/main.py` can keep doing:

    from app.routers.generate import router as generate_router

with the exact same route paths, methods, dependencies, and behavior as
before the split. No route logic was changed — only moved.

Sub-modules:
- _shared: constants + helpers shared across the sub-routers below
  (procurement/decision-council context, request.state/log-event builders,
  attachment extraction, visual-asset helpers, and the `_run_generate` core
  pipeline).
- core: core document generation endpoints (`/generate`,
  `/generate/with-attachments`, `/generate/from-documents`, `/generate/from-pdf`).
- export: document export / binary-format endpoints (`/generate/export`,
  `/generate/pptx`, `/generate/visual-assets`, `/generate/stream`,
  `/generate/docx`, `/generate/pdf`, `/generate/excel`, `/generate/hwp`,
  `/generate/export-edited`, `/generate/export-zip`).
- ai_features: auxiliary AI-powered text endpoints (`/generate/rewrite-section`,
  `/generate/sketch`, `/generate/refine`, `/generate/related`,
  `/generate/summary`, `/generate/validate`, `/generate/freeform`,
  `/generate/review`, `/generate/translate`).
- ops: feedback, ops, and attachment-parsing endpoints (`/feedback`,
  `/ops/cache/clear`, `/ops/investigate`, `/ops/post-deploy/*`,
  `/attachments/parse-rfp`, `/generate/recommend-bundle`).

Re-exports:
  Several library functions (``build_docx``, ``build_pptx``,
  ``generate_visual_assets_from_docs``, ``extract_multiple``,
  ``extract_pdf_structured``, ``extract_text_with_ai_fallback``) and internal
  helpers (``_run_generate``, ``_resolve_gov_options``, ``_store_zip_docs``,
  ``_get_zip_docs``, ``_get_low_rating_threshold``, ...) are re-exported here
  for backward compatibility with existing tests that do
  ``unittest.mock.patch("app.routers.generate.<name>", ...)`` or
  ``from app.routers.generate import <name>``. The sub-modules look these up
  on this facade module at call time (see each sub-module's ``_facade()``
  helper) so patches applied here take effect.
"""
from __future__ import annotations

from fastapi import APIRouter

# ── Re-exported library functions (patched by existing tests) ────────────────
from app.services.attachment_service import (
    extract_multiple,
    extract_pdf_structured,
    extract_text_with_ai_fallback,
)
from app.services.docx_service import build_docx
from app.services.pptx_service import build_pptx
from app.services.visual_asset_service import generate_visual_assets_from_docs

# ── Re-exported internal helpers (used directly by existing tests) ───────────
from app.routers.generate._shared import (
    _apply_generate_state,
    _auto_improve_if_needed,
    _build_generate_log_event,
    _build_generated_docs_response,
    _build_procurement_attachment_context,
    _build_structured_slide_data,
    _DECISION_COUNCIL_APPLIED_BUNDLE_IDS,
    _ensure_procurement_bundle_enabled,
    _ensure_procurement_override_reason_for_downstream,
    _extract_latest_procurement_override_reason,
    _extract_uploaded_documents,
    _generate_visual_assets_for_docs,
    _get_low_rating_threshold,
    _get_zip_docs,
    _heuristic_score,
    _legacy_binary_hwp_upload_names,
    _load_pdf_builder,
    _LEGACY_BINARY_HWP_GUIDANCE,
    _mark_decision_council_handoff_context,
    _mark_procurement_downstream_resolved_context,
    _PROCUREMENT_BUNDLE_LABELS,
    _PROCUREMENT_OVERRIDE_REQUIRED_BUNDLE_IDS,
    _raise_if_legacy_binary_hwp_uploads,
    _resolve_gov_options,
    _run_generate,
    _score_to_grade,
    _store_zip_docs,
    _zip_docs_cache,
)

from app.routers.generate.core import router as _core_router
from app.routers.generate.export import router as _export_router
from app.routers.generate.ai_features import router as _ai_features_router
from app.routers.generate.ops import router as _ops_router

router = APIRouter(tags=["generate"])

router.include_router(_core_router)
router.include_router(_export_router)
router.include_router(_ai_features_router)
router.include_router(_ops_router)
