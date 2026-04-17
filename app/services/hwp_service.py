"""hwp_service — build an in-memory hwpx (HancomOffice) file from rendered markdown docs.

hwpx is a ZIP archive containing HWP XML files.
No disk I/O; ``build_hwp`` returns raw bytes.
No external dependencies — uses Python's standard library zipfile module.

Government format improvements:
- Proper ``<hh:styles>`` definitions (본문 / 제목1 / 제목2 / 제목3)
- ``<hh:secPr>`` with A4 page size and configurable margins (hwpunit = 1/3600 inch)
- Optional 공문서 헤더 블록 paragraphs when is_government_format=True
"""
from __future__ import annotations

import html as _html
import re
import struct
import zipfile
from io import BytesIO
from typing import Any

from app.services.export_labels import humanize_doc_type
from app.services.export_outline import summarize_export_docs, summarize_export_package
from app.services.markdown_utils import parse_markdown_blocks
from app.services.visual_asset_service import decode_visual_asset_bytes, group_visual_assets_by_doc_type

# HWPX namespaces
_NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
_NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_NS_HC = "http://www.hancom.co.kr/hwpml/2011/core"
_NS_HS = "http://www.hancom.co.kr/hwpml/2011/section"
_NS_OPF = "http://www.idpf.org/2007/opf"
_NS_OCF = "urn:oasis:names:tc:opendocument:xmlns:container"
_NS_ODF = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"

# HWP unit: 1/3600 inch.  1 mm ≈ 141.732 hwpunits
# A4: 210mm × 297mm
_MM_TO_HWPU = 141.732  # hwpunits per mm
_A4_W = round(210 * _MM_TO_HWPU)   # 29764
_A4_H = round(297 * _MM_TO_HWPU)   # 42094


def _mm(mm: int | float) -> int:
    return round(mm * _MM_TO_HWPU)


def _escape(text: str) -> str:
    return _html.escape(text, quote=True)


# ---------------------------------------------------------------------------
# XML builders
# ---------------------------------------------------------------------------

def _container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<container xmlns="{_NS_OCF}">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="Contents/content.hpf"'
        ' media-type="application/hwpml-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>'
    )


def _content_hpf_xml(binary_items: list[dict[str, Any]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<opf:package xmlns:opf="{_NS_OPF}" version="1.0">',
        '  <opf:manifest>',
        '    <opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>',
        '    <opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>',
        '    <opf:item id="settings" href="Contents/settings.xml" media-type="application/xml"/>',
    ]
    for item in binary_items:
        lines.append(
            '    <opf:item '
            f'id="{_escape(item["id"])}" '
            f'href="{_escape(item["href"])}" '
            f'media-type="{_escape(item["media_type"])}" '
            'isEmbeded="1"/>'
        )
    lines.extend([
        '  </opf:manifest>',
        '</opf:package>',
    ])
    return "\n".join(lines)


def _manifest_xml(binary_items: list[dict[str, Any]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<manifest:manifest xmlns:manifest="{_NS_ODF}">',
        '  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/hwp+zip"/>',
        '  <manifest:file-entry manifest:full-path="Contents/content.hpf" manifest:media-type="application/hwpml-package+xml"/>',
        '  <manifest:file-entry manifest:full-path="Contents/header.xml" manifest:media-type="application/xml"/>',
        '  <manifest:file-entry manifest:full-path="Contents/section0.xml" manifest:media-type="application/xml"/>',
        '  <manifest:file-entry manifest:full-path="Contents/settings.xml" manifest:media-type="application/xml"/>',
    ]
    for item in binary_items:
        lines.append(
            '  <manifest:file-entry '
            f'manifest:full-path="{_escape(item["href"])}" '
            f'manifest:media-type="{_escape(item["media_type"])}"/>'
        )
    lines.append('</manifest:manifest>')
    return "\n".join(lines)


def _styles_xml(font_name: str = "맑은 고딕",
                font_size_pt: float = 10.5,
                line_spacing_pct: int = 160) -> str:
    """Generate <hh:styles> with 본문/제목1/제목2/제목3 style definitions.

    HWPX font sizes are in 1/100 pt units (hangul height attribute).
    Line spacing values: lineSpacingType="Percent", value = pct × 100.
    """
    body_sz  = round(font_size_pt * 100)           # 10.5pt → 1050
    h1_sz    = round((font_size_pt + 3) * 100)     # ~13.5pt → 1350
    h2_sz    = round((font_size_pt + 1.5) * 100)   # ~12pt   → 1200
    h3_sz    = round(font_size_pt * 100)            # body size, bold
    lsp      = line_spacing_pct * 100               # 160% → 16000

    def _style(style_id: str, name: str, hz_size: int, bold: str = "0") -> str:
        return (
            f'  <hh:style hh:styleId="{style_id}" hh:name="{name}" hh:type="para">\n'
            f'    <hh:paraShape hh:lineSpacingType="Percent" hh:lineSpacing="{lsp}">\n'
            f'      <hh:margin hh:left="0" hh:right="0" hh:prev="0" hh:next="0"/>\n'
            f'    </hh:paraShape>\n'
            f'    <hh:charShape>\n'
            f'      <hh:height hh:hangul="{hz_size}" hh:latin="{round(hz_size * 0.9)}"/>\n'
            f'      <hh:fontRef hh:hangul="{font_name}" hh:latin="Arial" hh:english="Arial"/>\n'
            f'      <hh:bold hh:value="{bold}"/>\n'
            f'      <hh:color hh:foreground="0"/>\n'
            f'    </hh:charShape>\n'
            f'  </hh:style>\n'
        )

    return (
        f'<hh:styles xmlns:hh="{_NS_HH}">\n'
        + _style("0", "본문",  body_sz, "0")
        + _style("1", "제목1", h1_sz,   "1")
        + _style("2", "제목2", h2_sz,   "1")
        + _style("3", "제목3", h3_sz,   "1")
        + "</hh:styles>"
    )


def _header_xml(
    title: str,
    font_name: str = "맑은 고딕",
    font_size_pt: float = 10.5,
    line_spacing_pct: int = 160,
) -> str:
    """HWPX header.xml — document metadata and style definitions."""
    styles = _styles_xml(font_name, font_size_pt, line_spacing_pct)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<hh:head xmlns:hh="{_NS_HH}">\n'
        f'  <hh:beginNum hh:page="1" hh:footnote="1"/>\n'
        f'  <hh:refList>\n'
        f'    <hh:fontfaces>\n'
        f'      <hh:fontface hh:lang="Hangul">\n'
        f'        <hh:font hh:name="{_escape(font_name)}" hh:type="TTF" hh:isEmbedded="0"/>\n'
        f'      </hh:fontface>\n'
        f'      <hh:fontface hh:lang="Latin">\n'
        f'        <hh:font hh:name="Arial" hh:type="TTF" hh:isEmbedded="0"/>\n'
        f'      </hh:fontface>\n'
        f'    </hh:fontfaces>\n'
        f'    <hh:borderFills/>\n'
        f'    <hh:charProperties/>\n'
        f'    <hh:tabProperties/>\n'
        f'    <hh:numberings/>\n'
        f'    <hh:bullets/>\n'
        f'    <hh:paraProperties/>\n'
        f'    {styles}\n'
        f'  </hh:refList>\n'
        f'  <hh:compatible/>\n'
        f'  <hh:docOption/>\n'
        f'  <hh:trackChanges/>\n'
        f'</hh:head>'
    )


def _para_xml(text: str, style: str = "본문") -> str:
    """Wrap text in an HWPX paragraph element."""
    escaped = _escape(text)
    return (
        f'  <hp:p>\n'
        f'    <hp:pPr>\n'
        f'      <hp:paraStyle hp:styleIDRef="{style}"/>\n'
        f'    </hp:pPr>\n'
        f'    <hp:run>\n'
        f'      <hp:rPr/>\n'
        f'      <hp:t>{escaped}</hp:t>\n'
        f'    </hp:run>\n'
        f'  </hp:p>'
    )


def _clean_hwp_text(text: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", str(text).strip())


def _table_block_paras(block: dict[str, Any]) -> list[str]:
    headers = [str(header).strip() for header in block.get("headers", [])]
    rows = block.get("rows", []) or []
    paras: list[str] = []
    if headers:
        paras.append(_para_xml("표: " + " | ".join(headers), "제목3"))
    for row in rows:
        if not isinstance(row, list):
            continue
        parts: list[str] = []
        for idx, cell in enumerate(row):
            value = _clean_hwp_text(cell)
            if not value:
                continue
            header = headers[idx] if idx < len(headers) else f"항목 {idx + 1}"
            parts.append(f"{header}: {value}")
        if parts:
            paras.append(_para_xml("• " + " / ".join(parts), "본문"))
    if paras:
        paras.append(_para_xml(""))
    return paras


def _gov_header_paras(title: str, opts: Any) -> list[str]:
    """Generate HWPX paragraph elements for the 공문서 헤더 블록."""
    paras: list[str] = []

    if opts.org_name:
        paras.append(_para_xml(opts.org_name, "제목1"))
    if opts.dept_name:
        paras.append(_para_xml(opts.dept_name, "제목2"))
    if opts.org_name or opts.dept_name:
        paras.append(_para_xml(""))
    paras.append(_para_xml("─" * 50, "본문"))
    if opts.doc_number:
        paras.append(_para_xml(f"문서번호: {opts.doc_number}", "본문"))
    if opts.recipient:
        paras.append(_para_xml(f"수\u2003\u2003신: {opts.recipient}", "본문"))
    if opts.via:
        paras.append(_para_xml(f"경\u2003\u2003유: {opts.via}", "본문"))
    paras.append(_para_xml(f"제\u2003\u2003목: {title}", "제목3"))
    paras.append(_para_xml(""))
    if opts.attachments:
        att_line = "  ".join(f"{i}. {a}" for i, a in enumerate(opts.attachments, 1))
        paras.append(_para_xml(f"붙\u2003\u2003임: {att_line}", "본문"))
    paras.append(_para_xml(""))

    return paras


def _media_extension(media_type: str) -> str:
    lowered = str(media_type or "").lower()
    if lowered == "image/png":
        return "png"
    if lowered in {"image/jpeg", "image/jpg"}:
        return "jpg"
    if lowered == "image/gif":
        return "gif"
    if lowered == "image/bmp":
        return "bmp"
    return ""


def _parse_png_size(raw: bytes) -> tuple[int, int] | None:
    if len(raw) >= 24 and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", raw[16:24])
    return None


def _parse_jpeg_size(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 4 or raw[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 9 < len(raw):
        if raw[index] != 0xFF:
            index += 1
            continue
        marker = raw[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(raw):
            break
        segment_length = int.from_bytes(raw[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(raw):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(raw[index + 3:index + 5], "big")
            width = int.from_bytes(raw[index + 5:index + 7], "big")
            if width > 0 and height > 0:
                return width, height
            break
        index += segment_length
    return None


def _image_hwpu_size(raw: bytes, media_type: str) -> tuple[int, int]:
    pixel_size: tuple[int, int] | None = None
    if media_type == "image/png":
        pixel_size = _parse_png_size(raw)
    elif media_type in {"image/jpeg", "image/jpg"}:
        pixel_size = _parse_jpeg_size(raw)

    max_width = _A4_W - _mm(50)
    max_height = _A4_H - _mm(140)
    default_width = min(max_width, _mm(140))
    default_height = min(max_height, _mm(90))

    if not pixel_size:
        return default_width, default_height

    src_width, src_height = pixel_size
    if src_width <= 0 or src_height <= 0:
        return default_width, default_height

    width = default_width
    height = round(width * (src_height / src_width))
    if height > max_height:
        height = max_height
        width = round(height * (src_width / src_height))
    return max(1, width), max(1, height)


def _picture_xml(ref_id: str, width: int, height: int, inst_id: int) -> str:
    return (
        '  <hp:p>\n'
        '    <hp:run>\n'
        f'      <hp:pic id="{inst_id}" zOrder="0" numberingType="NONE" textWrap="TOP_AND_BOTTOM" '
        f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="NONE" groupLevel="0" instid="{inst_id}" reverse="0">\n'
        f'        <hp:sz width="{width}" widthRelTo="ABSOLUTE" height="{height}" heightRelTo="ABSOLUTE" protect="0"/>\n'
        '        <hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
        'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>\n'
        '        <hp:outMargin left="0" right="0" top="0" bottom="0"/>\n'
        '        <hp:offset x="0" y="0"/>\n'
        f'        <hp:orgSz width="{width}" height="{height}"/>\n'
        f'        <hp:curSz width="{width}" height="{height}"/>\n'
        '        <hp:lineShape color="0" width="0" style="SOLID" endCap="FLAT" headStyle="NORMAL" tailStyle="NORMAL" '
        'headfill="0" tailfill="0" headSz="SMALL_SMALL" tailSz="SMALL_SMALL" outlineStyle="NORMAL" alpha="0"/>\n'
        '        <hp:imgRect>\n'
        '          <hc:pt0 x="0" y="0"/>\n'
        f'          <hc:pt1 x="{width}" y="0"/>\n'
        f'          <hc:pt2 x="{width}" y="{height}"/>\n'
        f'          <hc:pt3 x="0" y="{height}"/>\n'
        '        </hp:imgRect>\n'
        '        <hp:imgClip left="-1" right="-1" top="-1" bottom="-1"/>\n'
        '        <hp:inMargin left="0" right="0" top="0" bottom="0"/>\n'
        f'        <hp:imgDim dimwidth="{width}" dimheight="{height}"/>\n'
        f'        <hc:img binaryItemIDRef="{_escape(ref_id)}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>\n'
        '      </hp:pic>\n'
        '    </hp:run>\n'
        '  </hp:p>'
    )


def _prepare_hwp_visual_assets(visual_assets: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prepared: list[dict[str, Any]] = []
    binary_items: list[dict[str, Any]] = []
    for index, asset in enumerate(visual_assets or [], start=1):
        if not isinstance(asset, dict):
            continue
        asset_copy = dict(asset)
        media_type = str(asset_copy.get("media_type", "") or "").strip().lower()
        extension = _media_extension(media_type)
        raw = decode_visual_asset_bytes(asset_copy)
        if extension and raw:
            item_id = f"bindata{index}"
            href = f"BinData/{item_id}.{extension}"
            width, height = _image_hwpu_size(raw, media_type)
            asset_copy["hwp_binary_item_id"] = item_id
            asset_copy["hwp_binary_href"] = href
            asset_copy["hwp_binary_width"] = width
            asset_copy["hwp_binary_height"] = height
            asset_copy["hwp_binary_index"] = index
            binary_items.append(
                {
                    "id": item_id,
                    "href": href,
                    "media_type": media_type,
                    "raw": raw,
                }
            )
        prepared.append(asset_copy)
    return prepared, binary_items


def _export_cover_paras(title: str, docs: list[dict[str, Any]]) -> list[str]:
    summaries = summarize_export_docs(docs)
    package = summarize_export_package(docs)
    paras = [
        _para_xml(title, "제목1"),
        _para_xml("완성형 문서 패키지", "제목2"),
        _para_xml(f"총 {len(docs)}개 문서를 하나의 제출 패키지로 정리했습니다.", "본문"),
        _para_xml("패키지 지표", "제목3"),
        _para_xml(f"문서 수: {package['doc_count']}", "본문"),
        _para_xml(f"표 수: {package['table_total']}", "본문"),
        _para_xml(f"목록 수: {package['bullet_total']}", "본문"),
        _para_xml(f"주요 섹션 수: {package['heading_total']}", "본문"),
        _para_xml(f"주요 구성: {package['headline']}", "본문"),
        _para_xml(""),
        _para_xml("문서 구성", "제목3"),
    ]
    for idx, doc in enumerate(docs, start=1):
        paras.append(_para_xml(f"{idx}. {humanize_doc_type(str(doc.get('doc_type', 'document')))}", "본문"))
    paras.append(_para_xml(""))
    paras.append(_para_xml("핵심 검토 포인트", "제목3"))
    for summary in summaries:
        section_text = " · ".join(summary.get("section_items") or [summary["sections"]])
        metric_text = " · ".join(summary.get("metric_items") or [summary["metrics"]])
        paras.append(_para_xml(f"[{summary['index']}] {summary['label']}", "본문"))
        paras.append(_para_xml(f"핵심 메시지: {summary['lead']}", "본문"))
        paras.append(_para_xml(f"핵심 섹션: {section_text}", "본문"))
        paras.append(_para_xml(f"구성 지표: {metric_text}", "본문"))
        paras.append(_para_xml(""))
    paras.append(_para_xml("─" * 50, "본문"))
    paras.append(_para_xml(""))
    return paras


def _section_xml(
    docs: list[dict[str, Any]],
    title: str,
    opts: Any | None,
    top_mm: int,
    bot_mm: int,
    left_mm: int,
    right_mm: int,
    visual_assets: list[dict[str, Any]] | None = None,
) -> str:
    """Build the body section XML with page layout and paragraph content."""
    paras: list[str] = []
    assets_by_doc_type = group_visual_assets_by_doc_type(visual_assets or [])

    # 공문서 헤더 블록
    if opts and opts.is_government_format:
        paras.extend(_gov_header_paras(title, opts))
    else:
        paras.extend(_export_cover_paras(title, docs))

    # Content
    summaries = summarize_export_docs(docs)
    for i, doc in enumerate(docs):
        if i > 0:
            paras.append(_para_xml("─" * 40, "본문"))
            paras.append(_para_xml(""))
        if not (opts and opts.is_government_format):
            doc_title = humanize_doc_type(str(doc.get("doc_type", "document")))
            summary = summaries[i]
            paras.append(_para_xml(f"문서 {i + 1:02d} / {len(docs):02d}", "제목3"))
            paras.append(_para_xml(doc_title, "제목2"))
            paras.append(_para_xml(summary["lead"], "본문"))
            section_text = " · ".join(summary.get("section_items") or [summary["sections"]])
            metric_text = " · ".join(summary.get("metric_items") or [summary["metrics"]])
            paras.append(_para_xml(f"검토 초점: {section_text}", "본문"))
            paras.append(_para_xml(f"구성 지표: {metric_text}", "본문"))
            paras.append(_para_xml(""))
            visual_items = assets_by_doc_type.get(str(doc.get("doc_type", "document")), [])
            if visual_items:
                paras.append(_para_xml("생성 시각자료", "제목3"))
                for asset in visual_items[:2]:
                    slide_title = str(asset.get("slide_title", "")).strip() or "시각자료"
                    visual_type = str(asset.get("visual_type", "")).strip()
                    visual_brief = str(asset.get("visual_brief", "")).strip()
                    title_line = slide_title + (f" · {visual_type}" if visual_type else "")
                    paras.append(_para_xml(title_line, "본문"))
                    if visual_brief:
                        paras.append(_para_xml(visual_brief, "본문"))
                    ref_id = str(asset.get("hwp_binary_item_id", "")).strip()
                    width = int(asset.get("hwp_binary_width", 0) or 0)
                    height = int(asset.get("hwp_binary_height", 0) or 0)
                    binary_index = int(asset.get("hwp_binary_index", 0) or 0)
                    if ref_id and width > 0 and height > 0:
                        paras.append(_picture_xml(ref_id, width, height, 1000 + binary_index))
                paras.append(_para_xml(""))
        for block in parse_markdown_blocks(doc.get("markdown", "")):
            block_type = block.get("type")
            if block_type == "heading":
                level = int(block.get("level", 1))
                style = {1: "제목1", 2: "제목2", 3: "제목3"}.get(level, "제목3")
                paras.append(_para_xml(_clean_hwp_text(block.get("text", "")), style))
            elif block_type == "list_item":
                text = _clean_hwp_text(block.get("text", ""))
                paras.append(_para_xml(f"• {text}", "본문"))
            elif block_type == "paragraph":
                paras.append(_para_xml(_clean_hwp_text(block.get("text", "")), "본문"))
            elif block_type == "table":
                paras.extend(_table_block_paras(block))
            elif block_type in {"blank", "hr"}:
                paras.append(_para_xml("", "본문"))

    # 결재란 (텍스트 형태 — HWP에서 표 그리기는 별도 spec 필요)
    if opts and opts.is_government_format:
        approvers: list[tuple[str, str]] = []
        if opts.drafter:
            approvers.append(("기안", opts.drafter))
        if opts.reviewer:
            approvers.append(("검토", opts.reviewer))
        if opts.approver:
            approvers.append(("결재", opts.approver))
        if approvers:
            paras.append(_para_xml(""))
            roles = "   ".join(f"{role}: {name}" for role, name in approvers)
            paras.append(_para_xml(f"[결재란] {roles}", "본문"))

    body = "\n".join(paras)

    # Page layout in hwpunits
    w  = _A4_W
    h  = _A4_H
    ml = _mm(left_mm)
    mr = _mm(right_mm)
    mt = _mm(top_mm)
    mb = _mm(bot_mm)
    hd = _mm(10)   # header distance 10mm
    ft = _mm(10)   # footer distance 10mm

    sec_pr = (
        f'  <hh:secPr>\n'
        f'    <hh:pageSize hh:width="{w}" hh:height="{h}" hh:orientation="Portrait"/>\n'
        f'    <hh:pageMargin hh:left="{ml}" hh:right="{mr}" '
        f'hh:top="{mt}" hh:bottom="{mb}" '
        f'hh:header="{hd}" hh:footer="{ft}" hh:gutter="0"/>\n'
        f'  </hh:secPr>\n'
    )

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<hh:sec xmlns:hh="{_NS_HH}" xmlns:hs="{_NS_HS}" xmlns:hp="{_NS_HP}" xmlns:hc="{_NS_HC}">\n'
        f'{sec_pr}'
        f'{body}\n'
        f'</hh:sec>'
    )


def _settings_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<hh:settings xmlns:hh="{_NS_HH}">\n'
        '  <hh:startNum>\n'
        '    <hh:page hh:startNum="1"/>\n'
        '  </hh:startNum>\n'
        '</hh:settings>'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_hwp(
    docs: list[dict[str, Any]],
    title: str,
    gov_options: Any | None = None,
    visual_assets: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build an hwpx file from a list of rendered docs.

    Args:
        docs: List of {"doc_type": str, "markdown": str}.
        title: Document title.
        gov_options: Optional ``GovDocOptions`` dataclass instance.

    Returns:
        Raw bytes of the .hwpx file (ZIP archive).
    """
    opts = gov_options

    top_mm    = opts.top_margin_mm    if opts else 30
    bot_mm    = opts.bottom_margin_mm if opts else 15
    left_mm   = opts.left_margin_mm   if opts else 20
    right_mm  = opts.right_margin_mm  if opts else 20
    font_name = opts.font_name        if opts else "맑은 고딕"
    font_size = opts.font_size_pt     if opts else 10.5
    spacing   = opts.line_spacing_pct if opts else 160
    prepared_visual_assets, binary_items = _prepare_hwp_visual_assets(visual_assets)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype MUST be stored uncompressed (per hwpx spec)
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        zf.writestr(zi, "application/hwp+zip")
        zf.writestr("META-INF/container.xml", _container_xml())
        zf.writestr("META-INF/manifest.xml", _manifest_xml(binary_items))
        zf.writestr("Contents/content.hpf", _content_hpf_xml(binary_items))
        zf.writestr(
            "Contents/header.xml",
            _header_xml(title, font_name, font_size, spacing),
        )
        zf.writestr(
            "Contents/section0.xml",
            _section_xml(docs, title, opts, top_mm, bot_mm, left_mm, right_mm, visual_assets=prepared_visual_assets),
        )
        zf.writestr("Contents/settings.xml", _settings_xml())
        for item in binary_items:
            zf.writestr(item["href"], item["raw"])
    return buf.getvalue()
