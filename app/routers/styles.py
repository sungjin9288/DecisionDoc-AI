"""app/routers/styles.py — Style profile management endpoints.

Extracted from app/main.py.
"""
from __future__ import annotations

import datetime
import uuid as _uuid
from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.dependencies import get_tenant_id, get_user_id
from app.schemas import CreateStyleProfileRequest, UpdateToneGuideRequest

router = APIRouter(tags=["styles"])


def _get_style_store(request: Request):
    from app.storage.style_store import get_style_store

    return get_style_store(
        get_tenant_id(request),
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    )


@router.post("/styles")
async def create_style_profile(request: Request, body: CreateStyleProfileRequest):
    """Create a new (empty) style profile for the tenant."""
    user_id = get_user_id(request)
    style_store = _get_style_store(request)
    profile = style_store.create(
        name=body.name,
        description=body.description,
        created_by=user_id,
    )
    return {"profile_id": profile.profile_id, "message": "스타일 프로필이 생성되었습니다."}


@router.get("/styles")
async def list_style_profiles(request: Request):
    """List all style profiles for the current tenant."""
    style_store = _get_style_store(request)
    profiles = style_store.list_profiles()
    return {
        "profiles": [
            {
                "profile_id": p.profile_id,
                "name": p.name,
                "description": p.description,
                "is_default": p.is_default,
                "is_system": p.is_system,
                "avatar_color": p.avatar_color,
                "example_count": len(p.examples),
                "bundle_override_count": len(p.bundle_overrides),
                "created_at": p.created_at,
            }
            for p in profiles
        ]
    }


@router.get("/styles/{profile_id}")
async def get_style_profile(request: Request, profile_id: str):
    """Get full details of a style profile."""
    style_store = _get_style_store(request)
    profile = style_store.get(profile_id)
    if not profile:
        raise HTTPException(404, "스타일 프로필을 찾을 수 없습니다.")
    return asdict(profile)


@router.post("/styles/{profile_id}/set-default")
async def set_default_style(request: Request, profile_id: str):
    """Mark a profile as the default for this tenant."""
    style_store = _get_style_store(request)
    if not style_store.get(profile_id):
        raise HTTPException(404, "스타일 프로필을 찾을 수 없습니다.")
    style_store.set_default(profile_id)
    return {"message": "기본 스타일 프로필이 설정되었습니다."}


@router.put("/styles/{profile_id}/tone")
async def update_tone_guide(
    request: Request, profile_id: str, body: UpdateToneGuideRequest
):
    """Update the global tone guide for a style profile."""
    from app.storage.style_store import ToneGuide

    style_store = _get_style_store(request)
    tone = ToneGuide(
        formality=body.formality,
        density=body.density,
        perspective=body.perspective,
        custom_rules=body.custom_rules,
        forbidden_words=body.forbidden_words,
        preferred_words=body.preferred_words,
    )
    try:
        style_store.update_tone_guide(profile_id, tone)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"message": "톤 가이드가 업데이트되었습니다."}


@router.put("/styles/{profile_id}/bundles/{bundle_id}")
async def set_bundle_tone(
    request: Request,
    profile_id: str,
    bundle_id: str,
    body: UpdateToneGuideRequest,
):
    """Set a bundle-specific tone override inside a style profile."""
    from app.storage.style_store import ToneGuide

    style_store = _get_style_store(request)
    tone = ToneGuide(**body.model_dump())
    try:
        style_store.set_bundle_override(profile_id, bundle_id, tone)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"message": f"{bundle_id} 번들 톤이 설정되었습니다."}


@router.delete("/styles/{profile_id}/bundles/{bundle_id}")
async def remove_bundle_tone(request: Request, profile_id: str, bundle_id: str):
    """Remove a bundle-specific tone override."""
    style_store = _get_style_store(request)
    try:
        style_store.remove_bundle_override(profile_id, bundle_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"message": f"{bundle_id} 번들 설정이 제거되었습니다."}


@router.post("/styles/{profile_id}/analyze")
async def analyze_style_document(
    request: Request,
    profile_id: str,
    files: list[UploadFile] = File(...),
    bundle_id: str | None = Form(None),
):
    """Upload documents and extract style patterns via LLM analysis."""
    from app.providers.factory import get_provider_for_bundle
    from app.services.generation.context_store import record_direct_provider_usage
    from app.services.style_analyzer import analyze_document_style
    from app.storage.style_store import StyleExample

    tenant_id = get_tenant_id(request)
    user_id = get_user_id(request)
    style_store = _get_style_store(request)
    if not style_store.get(profile_id):
        raise HTTPException(404, "스타일 프로필을 찾을 수 없습니다.")

    provider = get_provider_for_bundle(bundle_id or "proposal_kr", tenant_id)
    results = []

    for f in files:
        raw = await f.read()
        usage_totals: dict[str, int] = {}
        try:
            analysis = await analyze_document_style(
                f.filename,
                raw,
                bundle_id,
                provider,
                usage_totals=usage_totals,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        finally:
            if usage_totals.get("provider_calls", 0) > 0:
                record_direct_provider_usage(
                    request,
                    provider,
                    bundle_id=f"style.analyze.{bundle_id or 'proposal_kr'}",
                    extra_tokens=usage_totals,
                )

        example = StyleExample(
            example_id=str(_uuid.uuid4()),
            source_filename=f.filename,
            bundle_id=bundle_id,
            extracted_patterns=analysis.get("patterns", []),
            sample_sentences=analysis.get("sample_sentences", []),
            uploaded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            uploaded_by=user_id,
        )
        style_store.add_example(profile_id, example)
        results.append(
            {
                "filename": f.filename,
                "analysis": analysis,
                "example_id": example.example_id,
            }
        )

    return {"analyzed": results, "message": f"{len(results)}개 파일 분석 완료"}


@router.delete("/styles/{profile_id}/examples/{example_id}")
async def remove_style_example(request: Request, profile_id: str, example_id: str):
    """Remove a style example from a profile."""
    style_store = _get_style_store(request)
    try:
        style_store.remove_example(profile_id, example_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"message": "예시가 제거되었습니다."}


@router.delete("/styles/{profile_id}")
async def delete_style_profile(request: Request, profile_id: str):
    """Delete a custom style profile (system profiles cannot be deleted)."""
    style_store = _get_style_store(request)

    if style_store.get(profile_id) is None:
        raise HTTPException(404, "스타일 프로필을 찾을 수 없습니다.")
    if style_store.is_system(profile_id):
        raise HTTPException(400, "기본 제공 스타일 프로필은 삭제할 수 없습니다.")

    style_store.delete(profile_id)
    return {"message": "스타일 프로필이 삭제되었습니다."}
