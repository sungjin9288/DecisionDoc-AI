"""pptx_service — build in-memory PPTX files from slide structures or rendered docs.

The implementation lives in this package, split into focused modules:

- ``constants``: shared style constants (colors, size limits).
- ``primitives``: low-level text/shape/style helpers (``_clean_slide_text``,
  ``_chunk_lines``, ``_add_card``, ``_style_text_frame`` …).
- ``basic_slides``: generic slide renderers — content slide, section
  divider, agenda, summary, table.
- ``visual_panels``: structured-slide visual panel renderers (placeholder,
  cards, KPI, matrix, timeline, flow, governance) plus generated
  image/SVG asset handling.
- ``structured_slide``: structured slide-outline helpers and the guided
  per-slide renderer (``_render_structured_guided_slide``).
- ``deck_builders``: the public ``build_pptx`` / ``build_pptx_from_docs``
  deck builders.

This package re-exports the full public and internal API so existing
``from app.services.pptx_service import X`` imports keep working unchanged.
"""
from __future__ import annotations

from app.services.pptx.constants import (
    _COLOR_BG_ACCENT,
    _COLOR_BG_DARK,
    _COLOR_BG_SOFT,
    _COLOR_BORDER,
    _COLOR_CARD,
    _COLOR_CARD_SOFT,
    _COLOR_TEXT_DARK,
    _COLOR_TEXT_LIGHT,
    _COLOR_TEXT_MUTED,
    _MAX_CONTENT_SLIDE_LEN,
    _MAX_CONTENT_SLIDE_LINES,
    _MAX_SLIDE_LINES,
    _MAX_TABLE_ROWS,
)
from app.services.pptx.primitives import (
    _add_card,
    _add_text_box,
    _chunk_lines,
    _clean_slide_text,
    _expand_slide_line,
    _set_slide_background,
    _set_text_frame_lines,
    _style_text_frame,
    _table_block_lines,
)
from app.services.pptx.basic_slides import (
    _render_agenda_slide,
    _render_section_divider,
    _render_slide,
    _render_summary_slide,
    _render_table_slide,
)
from app.services.pptx.visual_panels import (
    _render_structured_visual_panel,
    _render_visual_cards,
    _render_visual_flow,
    _render_visual_governance,
    _render_visual_image_asset,
    _render_visual_kpi,
    _render_visual_matrix,
    _render_visual_placeholder,
    _render_visual_timeline,
    _structured_visual_lines,
    _svg_asset_text_lines,
    _visual_kind,
    _with_svg_asset_evidence,
)
from app.services.pptx.structured_slide import (
    _render_structured_guided_slide,
    _structured_slide_acceptance_criteria,
    _structured_slide_content_blocks,
    _structured_slide_data_needs,
    _structured_slide_decision_question,
    _structured_slide_guidance,
    _structured_slide_lines,
    _structured_slide_list_field,
    _structured_slide_narrative_role,
    _structured_slide_summaries,
)
from app.services.pptx.deck_builders import build_pptx, build_pptx_from_docs

__all__ = [
    "build_pptx",
    "build_pptx_from_docs",
]
