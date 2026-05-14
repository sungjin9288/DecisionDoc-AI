# Report Quality Rubric

이 rubric은 DecisionDoc 보고서/제안서 결과물을 fine-tuning 후보로 넣기 전에 평가하는 기준이다.

점수는 `0.0`부터 `1.0`까지 기록한다. 학습 후보로 인정하려면 `overall_score >= 0.80`이고, 핵심 dimension은 모두 `0.75` 이상이어야 한다.

## Hard Fail

아래 항목 중 하나라도 있으면 학습 후보에서 제외한다.

- 확인되지 않은 통계, 기관명, 예산, 실적, KPI를 확정 사실처럼 썼다.
- 공공사업/제안서 맥락에서 금지되거나 과장된 표현이 남아 있다.
- 개인정보, 영업비밀, 보안상 민감한 내용이 redaction 없이 포함되어 있다.
- 원본 첨부파일 본문, base64, raw file bytes, secret 값이 artifact에 들어 있다.
- 문서 유형이 요청과 다르다.
- PPT/DOCX/PDF export가 깨지거나 검증 불가능하다.
- 장표별 핵심 메시지가 없거나 전체 narrative가 이어지지 않는다.
- 사람이 최종 승인하지 않았다.

## Dimension Scores

| Dimension | Minimum | 평가 기준 |
|---|---:|---|
| `logic` | `0.75` | 문제 정의, 원인, 해결 방향, 실행 방법, 기대효과가 연결되어 있는가 |
| `evidence` | `0.75` | 확인된 근거, 추정, TODO가 분리되어 있고 허위 주장이 없는가 |
| `audience_fit` | `0.75` | PM, 대표, 공공기관 담당자 등 대상 독자의 의사결정에 맞는가 |
| `slide_structure` | `0.75` | 장표별 제목, 메시지, 근거, 시각자료, 결론이 분명한가 |
| `visual_design` | `0.70` | 정보 밀도, 표/그래프/도식 배치, 페이지 균형이 충분한가 |
| `public_sector_tone` | `0.75` | 공공사업/제안서 톤이 절제되어 있고 실행 가능성을 보여주는가 |
| `export_readiness` | `0.80` | PPTX/PDF/DOCX/HWPX 등 산출물이 열리고 구조가 유지되는가 |
| `learning_value` | `0.75` | 이 샘플이 모델의 논리/기획/장표 설계 능력을 개선할 만큼 좋은가 |

## Correction Rationale

사람이 고친 결과는 단순히 최종본만 저장하지 않는다. 아래 이유를 반드시 기록한다.

- 어떤 문장이 논리적으로 약했는가
- 어떤 근거가 확인/추정/TODO로 분리되어야 했는가
- 어떤 장표가 너무 복잡하거나 빈약했는가
- 어떤 시각자료가 필요한가
- 어떤 문구가 공공/제안서 톤에 맞지 않았는가
- export 후 어떤 구조 문제가 있었는가

## Learning Candidate Decision

학습 후보 판정:

- `accepted_for_learning=true`: small SFT 후보로 사용 가능
- `accepted_for_learning=false`: 학습 제외. 단, 실패 유형 분석에는 사용할 수 있음
- `human_review_status=changes_requested`: 수정 후 재검토
- `human_review_status=blocked`: 민감정보, 허위 주장, 권한 문제 등으로 사용 금지

## First SFT Target

초기 fine-tuning은 PPT 디자인 자체보다 아래 narrow task를 먼저 대상으로 한다.

- 기획안 구조화
- 장표별 핵심 메시지 설계
- 근거 gap 탐지
- 공공/제안서 톤 보정
- 정책 논리와 실행계획 연결

디자인 품질은 먼저 template, layout rule, visual asset checklist, export QA로 끌어올린 뒤 학습 데이터를 쌓는다.
