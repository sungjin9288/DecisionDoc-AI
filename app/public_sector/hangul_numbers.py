"""Parse Hangul amounts such as 금일십일만삼천오백육십원 into integers."""
from __future__ import annotations

_DIGITS = {"영": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SMALL_UNITS = {"십": 10, "백": 100, "천": 1000}
_LARGE_UNITS = {"만": 10**4, "억": 10**8, "조": 10**12}
HANGUL_NUMBER_CHARS = "".join([*_DIGITS, *_SMALL_UNITS, *_LARGE_UNITS])


def parse_hangul_amount(text: str) -> int | None:
    """Return the value, or ``None`` when the text is not a Hangul number."""
    body = "".join(text.split()).removeprefix("금").removesuffix("정").removesuffix("원")
    if not body or any(char not in HANGUL_NUMBER_CHARS for char in body):
        return None
    total = section = digit = 0
    for char in body:
        if char in _DIGITS:
            digit = _DIGITS[char]
        elif char in _SMALL_UNITS:
            section += (digit or 1) * _SMALL_UNITS[char]
            digit = 0
        else:
            section += digit
            total += (section or 1) * _LARGE_UNITS[char]
            section = digit = 0
    return total + section + digit
