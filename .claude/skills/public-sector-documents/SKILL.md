---
name: public-sector-documents
description: Check a Korean public-sector proposal or report (공공기관·공기업·지자체·국책과업) against its RFP and official rules — requirement trace table (요구사항 대비표), evaluation cross-reference table (조견표) with PDF pages, and unknown RFP conditions. Use when the user works on a 제안서, 사업수행계획서 or project report for a public agency, or gives an RFP/제안요청서/과업지시서.
---

# 공공 과업 문서 검사

세션이 RFP를 읽고 조건을 정리하면, `scripts/publicdoc.py`가 원고를 RFP와 공식 기준에 대조한다. 서버, provider, 외부 서비스는 쓰지 않는다. 원고는 이 세션이 직접 쓴 것이든 `decisiondoc-authoring`으로 만든 것이든 상관없다.

## 1. RFP 읽기

- RFP·과업지시서가 HWPX·DOCX·PDF이면 전체 텍스트를 쪽·제목 표시와 함께 뽑는다. 웹 앱의 첨부 추출과 달리 자르지 않는다.

  ```bash
  python3 scripts/publicdoc.py text <RFP 파일> --out work/<과업>/rfp.txt
  python3 scripts/publicdoc.py scan-requirements <RFP 파일> --out work/<과업>/candidates.json
  ```

- `scan-requirements`의 결과는 후보다. RFP 원문과 대조해 확정한다. 접두어(SFR 등)는 RFP마다 다를 수 있으므로 `--prefix`로 좁힐 수 있다.

## 2. RFP 조건 카드 쓰기

`work/<과업>/rfp_profile.json`을 쓴다. 형식은 `app/public_sector/models.py`의 `RfpProfile`이다(`schema_version: "publicdoc.rfp_profile.v1"`).

- `requirements`: 고유번호, 분류, 명칭, 출처(예: "제안요청서 p.23")
- `evaluation_items`: 평가항목, 배점, 정량·정성, 이 항목에 답하는 제안서 목차 제목(`headings`)
- `submission`: 제출 형식, 용량, 별도 파일, 쪽수 제한, 블라인드 평가 여부
- `scoring`: 기술·가격 배점, 협상적격 기준(예: 0.85)

RFP에 없는 값은 비워 둔다. 짐작으로 채우지 않는다. 비운 값은 검사에서 "확인 필요"로 나온다.

```bash
python3 scripts/publicdoc.py check-profile work/<과업>/rfp_profile.json
```

## 3. 제안서 쓰기

공공 제안서는 고정 번들 목차 대신 RFP의 목차와 평가항목을 따른다.

- RFP 제안서 작성 요령에 지정 목차가 있으면 조건 카드 `outline`에 적는다. 목차마다 답하는 평가항목, 요구사항 번호, 작성 요령을 함께 적는다. 지정 목차가 없으면 비워 둔다. 그러면 평가항목마다 장을 만든다.
- 뼈대를 만들고 그 파일에 직접 쓴다. `[작성 필요]` 줄은 모두 내용으로 바꾸고, 요구사항 고유번호는 본문에 적는다.

  ```bash
  python3 scripts/publicdoc.py proposal-skeleton --profile work/<과업>/rfp_profile.json --out work/<과업>/제안서.md
  python3 scripts/publicdoc.py proposal-check --profile work/<과업>/rfp_profile.json work/<과업>/제안서.md
  python3 scripts/publicdoc.py export work/<과업>/제안서.md --title "<제안서 제목>" --out-dir work/<과업>/제출 --name 정성제안서
  ```

- `export`는 서버 없이 HWPX·DOCX·PDF를 만들고 DecisionDoc 표지를 넣지 않는다.

## 4. 원고 검사

- 요구사항 추적은 내보내기 전 원고(`.md`·`.docx`·`.hwpx`)로 한다. 내보낸 파일은 표지 요약이 본문을 반복해 위치가 여러 개 잡힐 수 있다.
- 번들처럼 원고가 여러 파일이면 제출본과 같은 순서로 모두 준다. `trace`·`crosswalk`·`notation`은 여러 파일을 한 문서로 읽는다.

  ```bash
  python3 scripts/publicdoc.py trace work/<과업>/rfp_profile.json <원고> --table work/<과업>/요구사항_대비표.md
  ```

- 누락(`missing`)은 원고에 대응 내용을 쓰고 고유번호를 적는다. RFP에 없는 번호(`unknown_ids`)는 오타인지, 제안사 추가 제안인지 확인한다.
- 조견표는 제출할 PDF를 만든 뒤 원고와 함께 준다. 원고의 제목 다음 본문으로 PDF 쪽을 확인한다.

  ```bash
  python3 scripts/publicdoc.py crosswalk work/<과업>/rfp_profile.json <원고> --pdf <제출 PDF> --table work/<과업>/조견표.md
  ```

- 쪽에 "(확인 필요)"가 붙으면 본문으로 확인하지 못한 추정이다. PDF에서 직접 확인한다.

- 공공 표기(항목 기호 순서, 날짜·시각, 금액 한글 병기, "끝")를 검사한다. 행정기관이 내는 공문형 문서(착수계 공문 등)는 `--kind agency`, 제안서·보고서는 기본값(`submission`, 권고라 경고)이다.

  ```bash
  python3 scripts/publicdoc.py notation <원고> --kind submission
  ```

## 5. 과업 단계 보고서

- 사업수행계획서, 착수·중간·완료보고서, 정책연구 보고서, 사업계획서, 타당성 검토 유형이 있다. `report-types`로 섹션과 근거를 본다.
- 조건 카드에 `tasks`(과업지시서 항목)와 `commitments`(제안서에서 약속한 인력·일정·산출물)를 적으면, 보고서의 과업 이행 대비표가 모든 항목을 다루는지 검사한다.

  ```bash
  python3 scripts/publicdoc.py report-skeleton --type interim_report --profile work/<과업>/rfp_profile.json --out work/<과업>/중간보고서.md
  python3 scripts/publicdoc.py report-check work/<과업>/중간보고서.md --type interim_report --profile work/<과업>/rfp_profile.json
  ```

- 뼈대의 `[작성 필요]`는 모두 내용으로 바꾼다. 남아 있으면 오류다.

## 6. 제출 전 검사

- 제출할 파일 또는 폴더를 조건 카드와 대조한다. 블라인드 평가면 회사명·약칭·대표자명 등을 `--identifier`로 모두 준다. 본문, 파일 이름, 메타데이터를 검사한다.

  ```bash
  python3 scripts/publicdoc.py submission work/<과업>/rfp_profile.json work/<과업>/제출/ --identifier "(주)회사명" --identifier "회사 약칭"
  ```

- 작성용 흔적(`[작성 필요]`, "확인 필요", "PPT 구성 가이드", TODO·TBD)이 경고로 나오면 제출 전에 모두 해소하거나 지운다.

종료 코드: 0 통과, 1 고칠 것 있음, 2 입력을 읽을 수 없음.

## 작성 규칙

- **기준의 출처:** 공식 기준은 설계 문서(`docs/superpowers/specs/2026-10-19-public-sector-specialization-design.md`)에 출처와 기준일이 있다. RFP마다 다른 조건(쪽수, 블라인드, 배점, 목차)은 RFP 조건 카드가 기준이다.
- **사실 생성 금지:** 실적, 인력, 자격, 인증, 수치를 만들어 쓰지 않는다. 근거가 없으면 "확인 필요"로 둔다.
- **판정의 범위:** 검사 통과는 제출·평가 결과·승인을 뜻하지 않는다.
- **자료 보안:** 고객 RFP와 원고는 `work/`나 `output/`처럼 git이 추적하지 않는 곳에 둔다.
