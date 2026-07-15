"""app/routers/admin/_models.py — Fine-tuned model registry endpoints.

Extracted from app/routers/admin.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.ops_key import require_ops_key
from app.dependencies import get_tenant_id

router = APIRouter()

# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

@router.get("/models")
def list_models(
    request: Request,
    bundle_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List fine-tuned models for the current tenant."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = get_tenant_id(request)
    registry = ModelRegistry(request.app.state.data_dir, tenant_id=tenant_id)
    return registry.list_models(bundle_id=bundle_id, status=status)


@router.get("/models/{model_id:path}")
def get_model(model_id: str, request: Request) -> dict:
    """Get details for a specific fine-tuned model."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = get_tenant_id(request)
    registry = ModelRegistry(request.app.state.data_dir, tenant_id=tenant_id)
    model = registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return model


@router.post("/admin/models/trigger-training", dependencies=[Depends(require_ops_key)])
async def admin_trigger_training(request: Request, payload: dict) -> dict:
    """Manually trigger fine-tune check for a bundle+tenant. Requires OPS key."""
    from app.services.finetune_orchestrator import FineTuneOrchestrator
    tenant_id = get_tenant_id(request)
    bundle_id_val: str | None = payload.get("bundle_id") or None
    orch = FineTuneOrchestrator(request.app.state.data_dir)
    result = await orch.check_and_trigger(bundle_id_val, tenant_id)
    if result is None:
        return {"triggered": False, "message": "Not enough data or training already in progress."}
    return {"triggered": True, **result}


@router.post("/admin/models/{model_id:path}/promote", dependencies=[Depends(require_ops_key)])
def admin_promote_model(model_id: str, request: Request) -> dict:
    """Manually promote a model to 'ready' status. Requires OPS key."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = get_tenant_id(request)
    registry = ModelRegistry(request.app.state.data_dir, tenant_id=tenant_id)
    model = registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    job_id = model.get("openai_job_id", "")
    if not registry.update_status(job_id, "ready", model_id=model_id):
        raise HTTPException(status_code=500, detail="Failed to update model status.")
    return {"promoted": True, "model_id": model_id, "status": "ready"}


@router.post("/admin/models/{model_id:path}/deprecate", dependencies=[Depends(require_ops_key)])
def admin_deprecate_model(model_id: str, request: Request) -> dict:
    """Deprecate a model. Requires OPS key."""
    from app.storage.model_registry import ModelRegistry
    tenant_id = get_tenant_id(request)
    registry = ModelRegistry(request.app.state.data_dir, tenant_id=tenant_id)
    if not registry.deprecate_model(model_id):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return {"deprecated": True, "model_id": model_id}


@router.get("/admin/models/jobs", dependencies=[Depends(require_ops_key)])
async def admin_list_jobs(request: Request) -> list[dict]:
    """List active OpenAI fine-tuning jobs with fresh status. Requires OPS key."""
    from app.services.finetune_orchestrator import FineTuneOrchestrator
    orch = FineTuneOrchestrator(request.app.state.data_dir)
    jobs = await orch.list_active_jobs()
    return [
        {
            "id": j.get("id"),
            "status": j.get("status"),
            "model": j.get("model"),
            "fine_tuned_model": j.get("fine_tuned_model"),
            "created_at": j.get("created_at"),
            "finished_at": j.get("finished_at"),
            "training_file": j.get("training_file"),
            "error": j.get("error"),
        }
        for j in jobs
    ]
