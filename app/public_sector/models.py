"""RFP condition profile: what one RFP requires, as written by the session.

Unknown values stay ``None`` (or empty) and are reported as "확인 필요";
they are never filled with a default that would read as satisfied.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROFILE_SCHEMA_VERSION = "publicdoc.rfp_profile.v1"
# Marks text the writer has not replaced yet; checks treat such lines as unwritten.
PLACEHOLDER = "[작성 필요]"


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class ProjectInfo(_Strict):
    name: str = Field(..., min_length=1)
    issuer: str = ""
    notice_no: str = ""
    source_files: list[str] = Field(default_factory=list)


class Requirement(_Strict):
    id: str = Field(..., min_length=1)
    category: str = ""
    name: str = ""
    source: str = ""  # where the RFP states it, e.g. "제안요청서 p.23"


class EvaluationItem(_Strict):
    name: str = Field(..., min_length=1)
    points: float | None = None
    kind: Literal["정량", "정성", ""] = ""
    headings: list[str] = Field(default_factory=list)  # draft headings that answer this item


class OutlineSection(_Strict):
    """One chapter or section of the proposal outline the RFP prescribes (제안서 작성 요령)."""

    title: str = Field(..., min_length=1)
    level: int = Field(default=1, ge=1, le=3)
    evaluation_items: list[str] = Field(default_factory=list)  # evaluation item names this section answers
    requirement_ids: list[str] = Field(default_factory=list)
    guidance: str = ""  # what the RFP says to write here


class Obligation(_Strict):
    """A task-order item or a proposal commitment that later reports must account for."""

    id: str = Field(..., min_length=1)
    name: str = ""
    source: str = ""  # e.g. "과업지시서 3.2" or "제안서 p.41"


class SubmissionRules(_Strict):
    formats: list[str] = Field(default_factory=list)
    max_total_mb: float | None = None
    separate_files: list[str] = Field(default_factory=list)
    page_limit: int | None = None
    summary_page_limit: int | None = None
    blind_evaluation: bool | None = None
    notes: list[str] = Field(default_factory=list)


class Scoring(_Strict):
    technical: float | None = None
    price: float | None = None
    pass_ratio: float | None = None


class RfpProfile(_Strict):
    schema_version: Literal["publicdoc.rfp_profile.v1"]
    project: ProjectInfo
    requirements: list[Requirement] = Field(default_factory=list)
    evaluation_items: list[EvaluationItem] = Field(default_factory=list)
    outline: list[OutlineSection] = Field(default_factory=list)  # RFP 지정 목차, if any
    submission: SubmissionRules = Field(default_factory=SubmissionRules)
    scoring: Scoring = Field(default_factory=Scoring)
    tasks: list[Obligation] = Field(default_factory=list)  # 과업지시서 항목
    commitments: list[Obligation] = Field(default_factory=list)  # 제안서에서 약속한 인력·일정·산출물


def load_profile(path: str | Path) -> RfpProfile:
    """Read and validate a profile; raises ``pydantic.ValidationError`` on bad input."""
    return RfpProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))
