"""Visual asset generation, edited-doc export, and knowledge-promotion schemas."""

from dataclasses import dataclass, field as dc_field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EditedDocInput(BaseModel):
    """One user-edited document section for /generate/export-edited."""

    model_config = ConfigDict(strict=True, extra="forbid")

    doc_type: str
    markdown: str
    total_slides: int | None = None
    slide_outline: list[dict[str, Any]] = Field(default_factory=list)


class VisualAssetDocInput(BaseModel):
    """Slide-aware document payload for visual asset generation."""

    model_config = ConfigDict(strict=True, extra="forbid")

    doc_type: str
    markdown: str = ""
    total_slides: int | None = None
    slide_outline: list[dict[str, Any]] = Field(default_factory=list)


class GeneratedVisualAsset(BaseModel):
    asset_id: str
    doc_type: str
    slide_title: str
    visual_type: str = ""
    visual_brief: str = ""
    layout_hint: str = ""
    source_kind: str
    source_model: str = ""
    prompt: str = ""
    media_type: str
    encoding: Literal["base64"] = "base64"
    content_base64: str


class GenerateVisualAssetsRequest(BaseModel):
    """Payload for POST /generate/visual-assets."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    goal: str = ""
    bundle_type: str = Field(default="tech_decision", min_length=1)
    docs: list[VisualAssetDocInput] = Field(default_factory=list, min_length=1)
    max_assets: int = Field(default=6, ge=1, le=12)


class GenerateVisualAssetsResponse(BaseModel):
    title: str
    bundle_type: str
    count: int
    assets: list[GeneratedVisualAsset]


class UpdateHistoryVisualAssetsRequest(BaseModel):
    """Payload for persisting generated visual asset snapshots onto history entries."""

    model_config = ConfigDict(strict=True, extra="forbid")

    visual_assets: list[GeneratedVisualAsset] = Field(default_factory=list, max_length=12)


class PromoteKnowledgeReferenceRequest(BaseModel):
    """Promote approved generated docs into project knowledge as gold references."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    bundle_type: str = Field(..., min_length=1)
    docs: list[EditedDocInput] = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    quality_tier: str = "gold"
    success_state: str = "approved"
    source_organization: str = ""
    reference_year: int | None = None
    notes: str = ""
    source_bundle_id: str = ""
    source_request_id: str = ""


@dataclass
class GovDocOptions:
    """행안부 공문서 표준 서식 옵션.

    모든 필드는 선택사항이며 기본값을 가집니다.
    ``is_government_format=True`` 로 설정 시 공문서 헤더 블록과 결재란이 추가됩니다.
    """

    # 공문서 메타데이터
    doc_number: str = ""          # 문서번호 (예: "행정안전부-1234")
    recipient: str = ""           # 수신 (예: "수신자 참조")
    via: str = ""                 # 경유
    classification: str = ""      # 보안 등급 (예: "대외비", "비밀")
    org_name: str = ""            # 발신기관명 (예: "행정안전부")
    dept_name: str = ""           # 부서명
    contact: str = ""             # 담당자 연락처
    attachments: list[str] = dc_field(default_factory=list)  # 붙임 목록

    # 결재란
    drafter: str = ""             # 기안자
    reviewer: str = ""            # 검토자
    approver: str = ""            # 결재자

    # 페이지 레이아웃 (행안부 표준 기본값)
    top_margin_mm: int = 30       # 위 여백 (행안부 표준: 30mm)
    bottom_margin_mm: int = 15    # 아래 여백 (행안부 표준: 15mm)
    left_margin_mm: int = 20      # 좌 여백 (행안부 표준: 20mm)
    right_margin_mm: int = 20     # 우 여백 (행안부 표준: 20mm)

    # 글꼴 설정
    font_name: str = "맑은 고딕"   # 한글 폰트 (행안부 표준: 맑은 고딕)
    font_size_pt: float = 10.5    # 글자 크기 (행안부 표준: 10.5pt)
    line_spacing_pct: int = 160   # 줄간격 % (행안부 표준: 160%)

    # 플래그
    is_government_format: bool = False  # 공문서 표준 서식 적용 여부


class EditedExportRequest(BaseModel):
    """Payload for POST /generate/export-edited — export pre-rendered (possibly
    user-edited) docs without re-running LLM generation."""

    bundle_id: str = ""
    bundle_type: str = "tech_decision"
    title: str = "문서"
    format: str  # "docx" | "pdf" | "excel" | "hwp"
    docs: list[EditedDocInput]
    visual_assets: list[GeneratedVisualAsset] = Field(default_factory=list)
    gov_options: dict | None = None  # serialized GovDocOptions fields
