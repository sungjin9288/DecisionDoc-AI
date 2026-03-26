"""pptx_service — build an in-memory PPTX skeleton from slide_structure data.

No disk I/O is performed; ``build_pptx`` returns raw bytes.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from pptx import Presentation


def build_pptx(slide_data: dict[str, Any], title: str) -> bytes:
    """Build a PPTX skeleton from a ``slide_structure`` bundle document.

    Args:
        slide_data: The ``slide_structure`` dict from ``raw_bundle``.
                    Expected keys: ``presentation_goal``, ``slide_outline`` (list).
        title:      Document title used on the cover slide.

    Returns:
        Raw bytes of the ``.pptx`` file.
    """
    prs = Presentation()

    # ── Cover slide (layout 0 = "Title Slide" in default theme) ──────────────
    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = title
    if len(cover.placeholders) > 1:
        cover.placeholders[1].text = slide_data.get("presentation_goal", "")

    # ── Content slides (layout 1 = "Title and Content") ──────────────────────
    content_layout = prs.slide_layouts[1]
    for item in slide_data.get("slide_outline", []):
        if not isinstance(item, dict):
            continue  # skip malformed items

        slide = prs.slides.add_slide(content_layout)
        slide.shapes.title.text = str(item.get("title", ""))

        # Body: split key_content on newlines → one bullet per line
        body_tf = slide.placeholders[1].text_frame
        body_tf.clear()
        raw = str(item.get("key_content", ""))
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            if i == 0:
                body_tf.paragraphs[0].text = line
            else:
                body_tf.add_paragraph().text = line

        # Speaker notes: design_tip
        design_tip = str(item.get("design_tip", ""))
        if design_tip:
            slide.notes_slide.notes_text_frame.text = design_tip

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()
