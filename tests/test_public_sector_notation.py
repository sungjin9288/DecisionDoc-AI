"""Official notation checks: item symbols, dates, times, amounts and the end mark."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.public_sector.hangul_numbers import parse_hangul_amount
from app.public_sector.notation import check_notation
from app.public_sector.readers import read_document

FLAWED_MEMO = """# [합성] 착수 보고 회의 개최 알림

1. 관련: 문서관리시스템 고도화 사업 계약(2026-09-30)
2. 착수 보고 회의를 다음과 같이 개최합니다.
  가. 일시: 2026년 10월 21일 오후 2시 30분
  나. 장소: 본관 3층 회의실
  라. 참석: 사업 담당자
    1) 발주기관 담당 부서
    (1) 세부 참석자는 별도 안내
3. 사업비: 금113,560원(금일십일만삼천원)
4. 예산 총액 50,000,000원
5. 다음 점검일: 2026.11.05
"""

CLEAN_MEMO = """# [합성] 착수 보고 회의 개최 알림

1. 관련: 문서관리시스템 고도화 사업 계약(2026. 9. 30.)
2. 착수 보고 회의를 다음과 같이 개최합니다.
  가. 일시: 2026. 10. 21. 14:30
  나. 장소: 본관 3층 회의실
  다. 참석: 사업 담당자
    1) 발주기관 담당 부서
      가) 세부 참석자는 별도 안내
3. 사업비: 금113,560원(금일십일만삼천오백육십원)
4. 다음 점검일: 2026.11.5.
  가. 24시각제로 적는다.  끝.
"""


def _read(tmp_path: Path, text: str):
    path = tmp_path / "memo.md"
    path.write_text(text, encoding="utf-8")
    return read_document(path)


@pytest.mark.parametrize(
    ("text", "value"),
    [("금일십일만삼천오백육십원", 113560), ("삼억오천만원", 350_000_000), ("금십만원정", 100_000), ("일조이억", 1_000_200_000_000), ("사과", None)],
)
def test_hangul_amounts_parse_to_integers(text: str, value: int | None) -> None:
    assert parse_hangul_amount(text) == value


def test_agency_memo_reports_each_official_rule_as_an_error(tmp_path: Path) -> None:
    report = check_notation(_read(tmp_path, FLAWED_MEMO), kind="agency")

    found = [(f["rule"], f["suggestion"]) for f in report["findings"]]
    assert ("item_order", "") in found  # 나. → 라. skips 다.
    assert ("item_order", "가) 단계를 거치거나 기호를 바꾼다") in found  # 1) → (1) skips 가)
    assert ("date", "2026. 9. 30.") in found and ("date", "2026. 10. 21.") in found and ("date", "2026. 11. 5.") in found
    assert [s for rule, s in found if rule == "time"] == ["14:30"]
    assert sum(rule == "amount_mismatch" for rule, _ in found) == 1
    assert sum(rule == "amount_hangul_missing" for rule, _ in found) == 1
    assert ("end_mark", "마지막 글자에서 한 글자 띄우고 '끝.'을 쓴다") in found
    assert report["counts"] == {"error": 9, "warning": 0} and report["passed"] is False


def test_clean_agency_memo_passes(tmp_path: Path) -> None:
    report = check_notation(_read(tmp_path, CLEAN_MEMO), kind="agency")

    assert report["findings"] == []
    assert report["passed"] is True


def test_submissions_get_warnings_except_a_wrong_hangul_amount(tmp_path: Path) -> None:
    report = check_notation(_read(tmp_path, FLAWED_MEMO), kind="submission")

    rules = {(f["rule"], f["severity"]) for f in report["findings"]}
    assert ("amount_mismatch", "error") in rules
    assert ("amount_hangul_missing", "error") not in rules and not any(rule == "end_mark" for rule, _ in rules)
    assert report["counts"] == {"error": 1, "warning": 6}


def test_headings_and_new_parents_restart_item_sequences(tmp_path: Path) -> None:
    text = "# 제목\n\n## 1. 개요\n가. 목적\n나. 범위\n\n## 2. 추진\n가. 일정\n1) 착수\n2) 완료\n나. 체계\n"

    assert check_notation(_read(tmp_path, text), kind="agency")["findings"] == [
        {
            "rule": "end_mark", "severity": "error", "message": "본문 끝에 '끝' 표시가 없다",
            "suggestion": "마지막 글자에서 한 글자 띄우고 '끝.'을 쓴다", "basis": "행정업무규정 시행규칙 제4조⑤",
            "heading_path": "제목 > 2. 추진", "page": None, "excerpt": "나. 체계",
        }
    ]
