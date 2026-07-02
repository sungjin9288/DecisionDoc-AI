"""pptx style constants shared across the pptx builder modules."""
from __future__ import annotations

from pptx.dml.color import RGBColor

_MAX_SLIDE_LINES = 5
_MAX_CONTENT_SLIDE_LINES = 4
_MAX_CONTENT_SLIDE_LEN = 64
_MAX_TABLE_ROWS = 6
_COLOR_BG_DARK = RGBColor(27, 33, 69)
_COLOR_BG_ACCENT = RGBColor(98, 79, 255)
_COLOR_BG_SOFT = RGBColor(244, 245, 255)
_COLOR_CARD = RGBColor(255, 255, 255)
_COLOR_CARD_SOFT = RGBColor(238, 235, 255)
_COLOR_TEXT_DARK = RGBColor(31, 37, 67)
_COLOR_TEXT_MUTED = RGBColor(99, 107, 139)
_COLOR_TEXT_LIGHT = RGBColor(255, 255, 255)
_COLOR_BORDER = RGBColor(216, 220, 242)
