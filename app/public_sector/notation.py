"""Official Korean notation checks for agency documents and submitted proposals/reports.

Basis (조회 2026-10-19):
- 「행정업무의 운영 및 혁신에 관한 규정」(대통령령 제36728호) 제7조⑤: dates with dots in
  place of 연·월·일, times in the 24-hour clock with a colon.
- 같은 규정 시행규칙(행정안전부령 제408호) 제2조①: item symbol order 1., 가., 1), 가),
  (1), (가), ①, ㉮; 제2조②: amounts in digits followed by Hangul in parentheses;
  제4조⑤: the "끝" mark or "이하 빈칸".
These bind documents written by administrative agencies (kind ``agency``). For proposals
and reports submitted to them (kind ``submission``) the same rules are advice, so they are
warnings; a digit amount that disagrees with its Hangul amount is an error in both.
Indentation is not checked: its only source is the 2012 handbook.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from app.public_sector.hangul_numbers import HANGUL_NUMBER_CHARS, parse_hangul_amount
from app.public_sector.readers import SourceDocument

DocKind = Literal["agency", "submission"]
_HANGUL_SEQUENCE = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허"
_CIRCLED_DIGITS = "".join(chr(code) for code in range(0x2460, 0x2474))  # ①-⑳
_CIRCLED_HANGUL = "".join(chr(code) for code in range(0x326E, 0x327C))  # ㉮-㉻
_MAX_ITEM_NUMBER = 99
_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]\s+)?")
_ITEM_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (1, re.compile(r"^(\d{1,2})\.\s+\S")),
    (2, re.compile(rf"^([{_HANGUL_SEQUENCE}])\.\s+\S")),
    (3, re.compile(r"^(\d{1,2})\)\s+\S")),
    (4, re.compile(rf"^([{_HANGUL_SEQUENCE}])\)\s+\S")),
    (5, re.compile(r"^\((\d{1,2})\)\s+\S")),
    (6, re.compile(rf"^\(([{_HANGUL_SEQUENCE}])\)\s+\S")),
    (7, re.compile(rf"^([{_CIRCLED_DIGITS}])\s*\S")),
    (8, re.compile(rf"^([{_CIRCLED_HANGUL}])\s*\S")),
)
_SYMBOL_EXAMPLE = {1: "1.", 2: "가.", 3: "1)", 4: "가)", 5: "(1)", 6: "(가)", 7: "①", 8: "㉮"}
_DATE_WITH_CHARS_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_DATE_WITH_SEPARATOR_RE = re.compile(r"(?<![\d.])(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")
_DATE_WITHOUT_END_DOT_RE = re.compile(r"(?<![\d.])(\d{4})\.\s?(\d{1,2})\.\s?(\d{1,2})(?!\d)(?!\s?\.)")
_TIME_MERIDIEM_RE = re.compile(r"(오전|오후)\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?")
_TIME_CHARS_RE = re.compile(r"(?<![\d:])(\d{1,2})\s*시\s*(\d{1,2})\s*분")
_AMOUNT_WITH_HANGUL_RE = re.compile(rf"(\d[\d,]*)\s*원\s*\(\s*(금?[\s{HANGUL_NUMBER_CHARS}]+원?정?)\s*\)")
_AMOUNT_RE = re.compile(r"(?<![\d,])(\d{1,3}(?:,\d{3})+|\d{4,})\s*원(?!\s*\()")
_END_MARKS = ("끝.", "끝", "이하 빈칸")

_BASIS = {
    "item_order": "행정업무규정 시행규칙 제2조①",
    "date": "행정업무규정 제7조⑤",
    "time": "행정업무규정 제7조⑤",
    "amount_mismatch": "행정업무규정 시행규칙 제2조②",
    "amount_hangul_missing": "행정업무규정 시행규칙 제2조②",
    "end_mark": "행정업무규정 시행규칙 제4조⑤",
}


def _item(text: str) -> tuple[int, int, str] | None:
    """(level, position in its sequence, symbol) for a line that starts with an item symbol."""
    body = _LIST_PREFIX_RE.sub("", text, count=1)
    for level, pattern in _ITEM_PATTERNS:
        match = pattern.match(body)
        if not match:
            continue
        token = match.group(1)
        if token.isdigit():
            if int(token) > _MAX_ITEM_NUMBER:
                return None
            return level, int(token), match.group(0).split()[0]
        sequence = {7: _CIRCLED_DIGITS, 8: _CIRCLED_HANGUL}.get(level, _HANGUL_SEQUENCE)
        return level, sequence.index(token) + 1, token if level >= 7 else match.group(0).split()[0]
    return None


class _Checker:
    def __init__(self, document: SourceDocument, kind: DocKind) -> None:
        self.document = document
        self.kind = kind
        self.paths = document.heading_paths()
        self.findings: list[dict[str, Any]] = []

    def add(self, rule: str, index: int, message: str, *, suggestion: str = "", always_error: bool = False) -> None:
        block = self.document.blocks[index] if index >= 0 else None
        self.findings.append({
            "rule": rule,
            "severity": "error" if always_error or self.kind == "agency" else "warning",
            "message": message,
            "suggestion": suggestion,
            "basis": _BASIS[rule],
            "heading_path": self.paths[index] if block else "",
            "page": block.page if block else None,
            "excerpt": block.text[:120] if block else "",
        })

    def item_order(self) -> None:
        stack: list[tuple[int, int]] = []  # (level, position) of open items
        for index, block in enumerate(self.document.blocks):
            item = _item(block.text)
            if block.heading_level is not None:
                stack = [item[:2]] if item else []
                continue
            if item is None:
                continue
            level, position, symbol = item
            if stack and level > stack[-1][0] + 1:
                expected = _SYMBOL_EXAMPLE[stack[-1][0] + 1]
                self.add("item_order", index, f"'{symbol}' 앞에 '{expected}' 단계가 없다", suggestion=f"{expected} 단계를 거치거나 기호를 바꾼다")
            stack = [entry for entry in stack if entry[0] <= level]
            if stack and stack[-1][0] == level:
                if position not in (1, stack[-1][1] + 1):
                    self.add("item_order", index, f"'{symbol}' 번호가 이어지지 않는다")
                stack.pop()
            stack.append((level, position))

    def dates_and_times(self) -> None:
        for index, block in enumerate(self.document.blocks):
            text = block.text
            for match in [*_DATE_WITH_CHARS_RE.finditer(text), *_DATE_WITH_SEPARATOR_RE.finditer(text), *_DATE_WITHOUT_END_DOT_RE.finditer(text)]:
                year, month, day = (int(group) for group in match.groups())
                self.add("date", index, f"날짜 '{match.group(0)}'", suggestion=f"{year}. {month}. {day}.")
            meridiem_spans = []
            for match in _TIME_MERIDIEM_RE.finditer(text):
                hour = int(match.group(2)) % 12 + (12 if match.group(1) == "오후" else 0)
                minute = int(match.group(3) or 0)
                meridiem_spans.append(match.span())
                self.add("time", index, f"시각 '{match.group(0)}'", suggestion=f"{hour:02d}:{minute:02d}")
            for match in _TIME_CHARS_RE.finditer(text):
                if any(start <= match.start() < end for start, end in meridiem_spans):
                    continue
                self.add("time", index, f"시각 '{match.group(0)}'", suggestion=f"{int(match.group(1)):02d}:{int(match.group(2)):02d}")

    def amounts(self) -> None:
        for index, block in enumerate(self.document.blocks):
            for match in _AMOUNT_WITH_HANGUL_RE.finditer(block.text):
                digits = int(match.group(1).replace(",", ""))
                hangul = parse_hangul_amount(match.group(2))
                if hangul is not None and hangul != digits:
                    self.add("amount_mismatch", index, f"숫자 {digits:,}원과 한글 '{match.group(2)}'({hangul:,}원)이 다르다", always_error=True)
            if self.kind == "agency":
                for match in _AMOUNT_RE.finditer(block.text):
                    self.add("amount_hangul_missing", index, f"금액 '{match.group(0)}' 뒤에 한글 금액이 없다", suggestion="숫자 다음 괄호 안에 한글로 적는다")

    def end_mark(self) -> None:
        if self.kind != "agency":
            return
        last = len(self.document.blocks) - 1
        text = self.document.blocks[last].text if last >= 0 else ""
        if not text.rstrip().endswith(_END_MARKS):
            self.add("end_mark", last, "본문 끝에 '끝' 표시가 없다", suggestion="마지막 글자에서 한 글자 띄우고 '끝.'을 쓴다")


def check_notation(document: SourceDocument, kind: DocKind = "submission") -> dict[str, Any]:
    checker = _Checker(document, kind)
    checker.item_order()
    checker.dates_and_times()
    checker.amounts()
    checker.end_mark()
    findings = checker.findings
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in ("error", "warning")}
    return {
        "document": document.path,
        "kind": kind,
        "counts": counts,
        "findings": findings,
        "passed": counts["error"] == 0,
        "not_checked": ["들여쓰기(근거가 2012년 편람뿐)", "자동 번호 매기기로 만든 항목 기호(DOCX·HWPX 본문 텍스트에 없음)"],
    }
