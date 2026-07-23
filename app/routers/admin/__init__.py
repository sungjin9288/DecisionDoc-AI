"""app/routers/admin/__init__.py — Admin, tenant management, invite, and model registry endpoints.

Split from the former app/routers/admin.py (2,246 lines) into domain-focused
sub-modules under this package (M5 milestone). Each sub-module owns one
APIRouter; this file aggregates them behind a single `router` symbol so
`app/main.py` can keep doing:

    from app.routers.admin import router as admin_router

with the exact same route paths, methods, dependencies, and behavior as
before the split. No route logic was changed — only moved.

Sub-modules (only _bundles, _invite, _tenants, _procurement_quality,
_locations, and _models own an APIRouter included below; the
_procurement_quality_* helper modules are plain imports with no routes):
- _procurement_quality: the two `/admin/tenants/{id}/procurement-quality-summary`
  and `/admin/locations/{id}/procurement-quality-summary` endpoints, plus the
  top-level aggregation function they call.
- _procurement_quality_helpers: pure/utility helpers backing the aggregation
  (parsing, filtering, sorting, link resolution).
- _procurement_quality_queues: remediation handoff + stale-share queue
  builders backing the aggregation.
- _procurement_quality_location: location-level stale-share overview used by
  _locations's `/admin/locations` endpoint.
- _invite: team invitation endpoints (`/admin/invite`, `/invite/*`).
- _bundles: bundle auto-expansion endpoints (`/admin/expand-bundles`,
  `/admin/auto-bundles*`, `/admin/request-patterns`).
- _tenants: tenant CRUD, custom-hint, stats, and API key rotation endpoints.
- _locations: location (tenant) overview + per-tenant user management.
- _models: fine-tuned model registry endpoints (`/models*`, `/admin/models/*`).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.routers.admin._auth_sessions import router as _auth_sessions_router
from app.routers.admin._bundles import router as _bundles_router
from app.routers.admin._invite import router as _invite_router
from app.routers.admin._locations import router as _locations_router
from app.routers.admin._models import router as _models_router
from app.routers.admin._procurement_quality import router as _procurement_quality_router
from app.routers.admin._tenants import router as _tenants_router

router = APIRouter(tags=["admin"])

router.include_router(_auth_sessions_router)
router.include_router(_bundles_router)
router.include_router(_invite_router)
router.include_router(_tenants_router)
router.include_router(_procurement_quality_router)
router.include_router(_locations_router)
router.include_router(_models_router)
