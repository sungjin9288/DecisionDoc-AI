"""app/routers/projects/__init__.py — Project management endpoints facade.

Split from the former app/routers/projects.py (1,468 lines) into domain-focused
sub-modules under this package (M5 milestone). Each sub-module owns one
APIRouter; this file aggregates them behind a single `router` symbol so
`app/main.py` can keep doing:

    from app.routers.projects import router as projects_router

with the exact same route paths, methods, dependencies, and behavior as
before the split. No route logic was changed — only moved.

Sub-modules:
- _shared: cross-cutting helpers used by more than one domain sub-router
  (`_resolve_gov_options`, `_load_pdf_builder`, `_serialize_project_detail`,
  `_serialize_meeting_recording_summary`).
- core: project CRUD, search, stats, archive, and document
  add/remove/download endpoints (`/projects`, `/projects/search`,
  `/projects/stats`, `/projects/archive/{fiscal_year}`, `/projects/{id}`,
  `/projects/{id}/archive`, `/projects/{id}/documents*`).
- meeting_recordings: Voice Brief import + native meeting-recording
  endpoints (`/projects/{id}/imports/voice-brief`,
  `/projects/{id}/recordings*`).
- procurement: Public Procurement Go/No-Go Copilot + Decision Council v1
  endpoints (`/projects/{id}/imports/g2b-opportunity`,
  `/projects/{id}/procurement*`, `/projects/{id}/decision-council*`).
- procurement_reviews: tenant review inbox, packet export, packet-bound review
  history, one-time receipt completion, and reviewed-package download endpoints.

Re-exports:
  Internal helpers are re-exported here for backward compatibility with any
  code doing ``from app.routers.projects import <name>`` or
  ``unittest.mock.patch("app.routers.projects.<name>", ...)``.
"""
from __future__ import annotations

from fastapi import APIRouter

# ── Re-exported cross-cutting helpers ─────────────────────────────────────
from app.routers.projects._shared import (
    _load_pdf_builder,
    _resolve_gov_options,
    _serialize_meeting_recording_summary,
    _serialize_project_detail,
)

# ── Re-exported meeting-recording helpers ─────────────────────────────────
from app.routers.projects.meeting_recordings import (
    _apply_meeting_recording_error_observability,
    _apply_meeting_recording_observability,
    _ensure_project_exists_for_meeting_recording,
    _set_error_code,
)

# ── Re-exported procurement / decision-council helpers ────────────────────
from app.routers.projects.procurement import (
    _append_procurement_override_reason,
    _apply_decision_council_observability,
    _apply_procurement_observability,
    _attach_decision_council_binding,
    _build_g2b_structured_context,
    _ensure_procurement_copilot_enabled,
    _load_decision_council_procurement_context_or_raise,
    _normalize_procurement_opportunity,
)

from app.routers.projects.core import router as _core_router
from app.routers.projects.meeting_recordings import router as _meeting_recordings_router
from app.routers.projects.procurement import router as _procurement_router
from app.routers.projects.procurement_reviews import router as _procurement_reviews_router

router = APIRouter(tags=["projects"])

router.include_router(_core_router)
router.include_router(_meeting_recordings_router)
router.include_router(_procurement_router)
router.include_router(_procurement_reviews_router)
