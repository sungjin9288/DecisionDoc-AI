"""Image type and pixel-size probes used when embedding pictures in HWPX."""
from __future__ import annotations

import struct


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
