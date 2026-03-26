"""app/routers/g2b.py — 나라장터 (G2B) endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.api_key import require_api_key
from app.config import get_g2b_api_key, get_g2b_max_results
from app.maintenance.mode import require_not_maintenance
from app.schemas import G2BFetchRequest

router = APIRouter(prefix="/g2b", tags=["g2b"])


@router.get("/status")
async def g2b_status() -> dict:
    """Check G2B API configuration status."""
    api_key = get_g2b_api_key()
    return {
        "api_key_configured": bool(api_key),
        "api_key_preview": f"{api_key[:8]}..." if api_key else None,
        "scraping_available": True,
        "setup_url": "https://www.data.go.kr/data/15129394/openapi.do",
        "hint": "나라장터 입찰공고정보서비스 API 키 발급 후 G2B_API_KEY 설정",
    }


@router.get(
    "/search",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def search_g2b(
    request: Request,
    q: str,
    days: int = 7,
    limit: int = 10,
) -> dict:
    """Search 나라장터 announcements by keyword."""
    from app.services.g2b_collector import search_announcements

    results = await search_announcements(
        keyword=q,
        days_back=days,
        max_results=min(limit, get_g2b_max_results()),
        api_key=get_g2b_api_key(),
    )
    return {
        "query": q,
        "total": len(results),
        "results": [
            {
                "bid_number": r.bid_number,
                "title": r.title,
                "issuer": r.issuer,
                "budget": r.budget,
                "deadline": r.deadline,
                "category": r.category,
                "detail_url": r.detail_url,
            }
            for r in results
        ],
    }


@router.post(
    "/fetch",
    dependencies=[Depends(require_not_maintenance), Depends(require_api_key)],
)
async def fetch_g2b_announcement(
    request: Request,
    body: G2BFetchRequest,
) -> dict:
    """Fetch full announcement detail from URL or bid number.

    Returns structured fields for RFP auto-fill.
    """
    from app.providers.factory import get_provider_for_bundle
    from app.services.g2b_collector import fetch_announcement_detail
    from app.services.rfp_parser import parse_rfp_fields

    tenant_id = getattr(request.state, "tenant_id", "system") or "system"

    announcement = await fetch_announcement_detail(
        url_or_number=body.url_or_number,
        api_key=get_g2b_api_key(),
    )

    if not announcement:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")

    rfp_fields: dict = {}
    if announcement.raw_text:
        provider = get_provider_for_bundle("rfp_analysis_kr", tenant_id)
        rfp_fields = parse_rfp_fields(announcement.raw_text, provider=provider)

    return {
        "announcement": {
            "bid_number": announcement.bid_number,
            "title": announcement.title,
            "issuer": announcement.issuer,
            "budget": announcement.budget,
            "deadline": announcement.deadline,
            "bid_type": announcement.bid_type,
            "detail_url": announcement.detail_url,
            "raw_text_preview": announcement.raw_text[:1_000],
            "source": announcement.source,
        },
        "extracted_fields": rfp_fields,
        "structured_context": (
            f"발주기관: {announcement.issuer}\n"
            f"사업명: {announcement.title}\n"
            f"예산: {announcement.budget}\n"
            f"마감: {announcement.deadline}\n\n"
            + (announcement.raw_text[:5_000] if announcement.raw_text else "")
        ),
    }
