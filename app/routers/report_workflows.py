"""Report workflow router facade.

The route groups stay separate by responsibility while this module preserves
the public ``router`` import used by ``app.main``. Inclusion order is part of
the contract: static quality collection paths must precede the dynamic
``/{report_workflow_id}`` route.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.routers._report_workflow_core import (
    collection_router as _collection_router,
    promotion_router as _promotion_router,
    workflow_router as _workflow_router,
)
from app.routers._report_workflow_quality import (
    collection_router as _quality_collection_router,
    workflow_router as _quality_workflow_router,
)

router = APIRouter(tags=["report-workflows"])

router.include_router(_collection_router)
router.include_router(_quality_collection_router)
router.include_router(_workflow_router)
router.include_router(_quality_workflow_router)
router.include_router(_promotion_router)
