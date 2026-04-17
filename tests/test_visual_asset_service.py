from __future__ import annotations

from fastapi.testclient import TestClient

from app.providers.mock_provider import MockProvider
from app.services.visual_asset_service import generate_visual_assets_from_docs


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def test_generate_visual_assets_from_docs_mixes_provider_and_svg_assets():
    docs = [
        {
            "doc_type": "proposal_kr",
            "slide_outline": [
                {
                    "title": "현장 이미지",
                    "core_message": "현장 신뢰감을 높일 실제 사례 이미지를 제시한다.",
                    "evidence_points": ["현장 운영 환경", "서비스 적용 장면"],
                    "visual_type": "현장 사진",
                    "visual_brief": "운영 현장과 사용자 접점을 보여주는 이미지",
                    "layout_hint": "우측 대형 이미지",
                },
                {
                    "title": "추진 일정",
                    "core_message": "단계별 일정과 마일스톤을 명확히 정리한다.",
                    "evidence_points": ["착수", "중간 보고", "최종 완료"],
                    "visual_type": "타임라인",
                    "visual_brief": "착수부터 완료까지 주요 일정을 시각화",
                    "layout_hint": "우측 타임라인",
                },
            ],
        }
    ]

    assets = generate_visual_assets_from_docs(
        docs,
        title="공공 제안서",
        goal="발표용 시각자료를 함께 만든다.",
        provider=MockProvider(),
        request_id="req-visual-1",
    )

    assert len(assets) == 2
    image_asset = next(asset for asset in assets if asset["slide_title"] == "현장 이미지")
    svg_asset = next(asset for asset in assets if asset["slide_title"] == "추진 일정")
    assert image_asset["source_kind"] == "provider_image"
    assert image_asset["media_type"] == "image/png"
    assert image_asset["content_base64"]
    assert svg_asset["source_kind"] == "generated_svg"
    assert svg_asset["media_type"] == "image/svg+xml"
    assert svg_asset["content_base64"].startswith("PHN2Zy")


def test_generate_visual_assets_limits_provider_images_to_two():
    docs = [
        {
            "doc_type": "proposal_kr",
            "slide_outline": [
                {
                    "title": "이미지 1",
                    "core_message": "핵심 메시지 1",
                    "evidence_points": ["근거 1"],
                    "visual_type": "현장 사진",
                },
                {
                    "title": "이미지 2",
                    "core_message": "핵심 메시지 2",
                    "evidence_points": ["근거 2"],
                    "visual_type": "현장 사진",
                },
                {
                    "title": "이미지 3",
                    "core_message": "핵심 메시지 3",
                    "evidence_points": ["근거 3"],
                    "visual_type": "현장 사진",
                },
            ],
        }
    ]

    assets = generate_visual_assets_from_docs(
        docs,
        title="이미지 캡 테스트",
        goal="provider image 상한을 확인한다.",
        provider=MockProvider(),
        request_id="req-visual-2",
    )

    assert len(assets) == 3
    assert [asset["source_kind"] for asset in assets] == [
        "provider_image",
        "provider_image",
        "generated_svg",
    ]


def test_generate_visual_assets_endpoint_returns_mixed_assets(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/visual-assets",
        json={
            "title": "제안서 시각자료",
            "goal": "slide outline 기반 시각자료 생성",
            "bundle_type": "proposal_kr",
            "docs": [
                {
                    "doc_type": "business_understanding",
                    "slide_outline": [
                        {
                            "title": "사업 현장",
                            "core_message": "현장 맥락을 이미지로 설득력 있게 보여준다.",
                            "evidence_points": ["현장 적용 사례", "운영 환경"],
                            "visual_type": "현장 사진",
                            "visual_brief": "현장 사진 및 서비스 접점",
                            "layout_hint": "오른쪽 이미지",
                        },
                        {
                            "title": "추진 일정",
                            "core_message": "단계별 로드맵을 제시한다.",
                            "evidence_points": ["착수", "중간", "완료"],
                            "visual_type": "타임라인",
                            "layout_hint": "오른쪽 타임라인",
                        },
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "제안서 시각자료"
    assert body["bundle_type"] == "proposal_kr"
    assert body["count"] == 2
    kinds = {asset["slide_title"]: asset["source_kind"] for asset in body["assets"]}
    media_types = {asset["slide_title"]: asset["media_type"] for asset in body["assets"]}
    assert kinds["사업 현장"] == "provider_image"
    assert kinds["추진 일정"] == "generated_svg"
    assert media_types["사업 현장"] == "image/png"
    assert media_types["추진 일정"] == "image/svg+xml"
