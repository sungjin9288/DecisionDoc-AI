# 공고별 판단 보존과 체크리스트 적용 여부 설계

상태: 작업 1-8의 격리 API·브라우저·요구사항 이력·N/A export 통합을 local/fake-S3로 검증. 기본 앱·실사용 데이터 전환은 미완료. 갱신일: 2026-09-22.
실사용 데이터 전환 및 외부 효과는 미승인.

사용자는 계획한 기능의 완성을 우선하며, 지금은 무료 로컬 검증을 유지한다.
이번 설계는 FR1의 다중 공고와 체크리스트 N/A 의미를 구체화한다.
두 기능은 데이터와 권한에 미치는 영향이 달라 별도의 도입 기록으로 관리한다.
초안 검토 후 사용자의 “좋아 이어서 완벽하게 계획 세워서 진행하자”를
이 설계의 로컬·fake-S3 구현 진행 승인으로 기록했다. 기존 dirty 변경,
원본 파일, 완료된 검토 증빙은 보존한다.

## 1. 목표와 현재 차이

담당자는 같은 프로젝트에서 공고 A와 B를 오가더라도 각각의 평가, 검토,
문서가 어느 공고에 속하는지 알 수 있어야 한다. 검토자는 요구사항이
해당하지 않는다는 판단을 이유와 원문 근거로 남길 수 있어야 한다.
자료가 없다는 사실을 해당 없음이나 준비 완료로 바꾸어서는 안 된다.

현재 코드에서 확인한 경계:

| 근거 | 확인한 현재 동작 | 설계에 미치는 영향 |
|---|---|---|
| `app/storage/procurement_store.py:_owned_records` | 같은 프로젝트의 두 record를 중복 오류로 거부 | 단순 append로 다중 공고를 구현할 수 없음 |
| `app/routers/projects/procurement.py:import_project_procurement_g2b_endpoint` | 현재 공고 교체, snapshot 누적, 파생 판단 초기화 | 과거 snapshot을 독립된 평가 기록으로 소급 해석하지 않음 |
| `app/storage/decision_council_store.py:build_session_key` | project/use_case/target_bundle로 최신 세션 식별 | 공고 식별자를 키에 추가해야 A와 B의 세션이 덮이지 않음 |
| `app/services/decision_council/binding.py` | decision ID와 updated_at으로 신선도 판정 | 기존 binding을 보존하면서 공고별 revision 추가 |
| `app/storage/project_store.py:ProjectDocument` | Council·review 출처는 있으나 모든 문서에 공통된 공고 binding은 없음 | 생성·저장·재열기·내보내기에 공고 식별자를 함께 전달 |
| `app/schemas/procurement.py:ProcurementChecklistItem` | 공통 범주 중심 상태, N/A enum 없음 | 범주 전체를 임의로 제외하는 toggle은 부적절 |
| `app/services/procurement_decision_package/package_builder.py:_package_checklist_status` | blocked/needs_review 외에는 ready로 변환 | 새 상태 추가 전에 변환기를 명시적인 분기로 바꿔야 함 |
| `app/services/procurement_decision_package/package_constants.py` | 패키지 상태는 blocked/needs_review/ready | 기존 패키지와 새 상세 요구사항 표현의 버전 구분 필요 |

최근 355/40/2 통과 기록은 기존 보완의 증거다. 이 설계의 새 기능이
통과했다는 증거로 사용하지 않는다.

## 2. 대안과 권고

- 공고마다 별도 프로젝트: 지금도 가능한 우회 방법이다. 프로젝트 공통 지식,
  담당자, 문서를 중복 관리하며 FR1의 다중 공고 요구를 충족하지 못한다.
- 여러 공고를 저장하되 단일 판단 record만 교체: 변경은 작지만 평가·Council·
  검토 이력을 섞을 수 있어 제외한다.
- **프로젝트 안에 공고별 판단을 보존하고 하나를 선택**: 권고안이다.
  저장 계약과 consumer 수정이 필요하지만 요구사항과 증빙 경계를 함께 충족한다.

비교 점수표, 자동 최적 공고 선택, 일괄 수집·평가, 공고 삭제·병합,
외부 제출은 포함하지 않는다. 선택은 사용자의 문맥 전환이며 평가 실행이 아니다.

## 3. 공고 식별과 저장 계약

새로운 별도 opportunity UUID를 중복 도입하지 않고 `decision_id`를 공고별
안정적인 내부 식별자로 사용한다. UI에는 공고번호와 제목을 표시한다.

- 같은 tenant/project 안의 `source_kind + source_id`를 정확히 비교한다.
  G2B 차수·정정 식별자를 제거하거나 제목으로 합치지 않는다.
- 처음 가져온 공고에는 새 decision ID를 부여한다. 같은 source ID의 재수집은
  그 공고에 새 snapshot을 추가하고 해당 공고의 파생 판단만 무효화한다.
- 다른 source ID를 가져오면 독립 decision을 추가한다. 다른 공고의 메모,
  평가, 검토, snapshot을 복사하지 않는다.
- 기존 단일 record는 기존 decision ID, timestamps, notes, snapshot 참조를
  유지해 한 개의 공고로 읽는다. 과거에 교체된 공고의 snapshot은
  legacy source history로 표시하며 존재하지 않는 평가를 복구하지 않는다.

저장은 기존 tenant별 state 파일과 StateBackend의 CAS를 재사용한다.
새 schema `procurement.project.v2`의 프로젝트 aggregate는 tenant/project,
`active_decision_id`, `selection_revision`, 공고별 record와
`decision_revision`, 중복 요청 receipt를 포함한다. 한 CAS에서 해당 프로젝트
aggregate만 변경하고 다른 프로젝트와 private mutation 이력은 보존한다.
기존 v1 row와 새 aggregate를 읽을 수 있어야 하며, 같은 프로젝트가 둘로
존재하거나 active ID가 존재하지 않는 상태는 fail closed로 거부한다.

GET은 절대 전환·수정하지 않는다. 승인된 v2 write에서만 기존 row를
aggregate로 감싸며 내부의 기존 record 의미를 보존한다. 로컬 fixture와
fake-S3에서 전환을 검증한다. 기존 사용자의 DATA_DIR 전환은 별도 승인
대상이며 이번 후보의 허용 효과에 포함되지 않는다.

선택·가져오기·평가 저장은 expected revision과 operation ID를 받는다.
같은 ID/같은 payload는 기존 결과를 반환하고 다른 payload는 409로 거부한다.
CAS 충돌 시 오래된 payload를 최신 상태 위에 자동 재적용하지 않는다.
실패한 snapshot 저장 뒤의 참조되지 않은 파일은 자동 삭제하지 않는다.
snapshot과 aggregate의 다중 파일 원자성을 주장하지 않는다.

## 4. API와 요청 중 문맥 고정

아래 다섯 경로는 격리 local/fake-S3 테스트 앱에서 구현했다.
factory의 Python keyword opt-in에서만 등록하며 기본 앱에서는 비활성이다.
실사용 가능한 전체 기능이나 사용자 데이터 전환 완료라는 뜻은 아니다.

| 경로 | 동작 |
|---|---|
| GET `/projects/{project_id}/procurement/opportunities` | 활성 ID, selection revision, 공고 요약 목록 |
| GET `/projects/{project_id}/procurement/opportunities/{decision_id}` | 해당 공고의 현재 평가와 revision |
| POST `/projects/{project_id}/procurement/selection` | decision_id, expected_selection_revision, operation_id로 활성 공고 변경 |
| POST `/projects/{project_id}/procurement/opportunities/{decision_id}/evaluate` | 해당 공고의 expected_decision_revision에 대해 평가 |
| POST `/projects/{project_id}/procurement/opportunities/{decision_id}/recommend` | 해당 공고에 대해 재평가 및 추천 저장 |

선택·평가·추천 응답은 `{project_id, receipt}`이고 receipt에는 operation ID,
request SHA, decision ID/revision, selection revision이 들어간다. 재전송은
시간 의존 평가를 다시 계산하지 않고 최초 receipt를 반환한다. 이후 detail GET은
현재 상태이므로 과거 receipt의 결과 본문으로 취급하지 않는다. 성공 감사 로그에는
receipt 식별자를, 충돌 로그에는 요청 ID와 expected revision을 남긴다.

기존 import는 source identity로 추가/갱신할 공고를 결정하며 결과에 선택된
decision ID와 revisions를 반환한다. 다른 공고 추가 시 활성 공고 변경도
같은 CAS에 포함한다. 공고 목록 첫 읽기 및 UI 응답에는 본문 대신
title/source_id/updated_at/recommendation 요약만 담는다.

기존 project-only GET은 활성 공고와 선택 revision을 반환한다.
공고가 하나이면 기존 mutation/generation 호출은 그 공고를 사용한다.
두 개 이상이면 예전 mutation/generation 호출은 명시적 decision ID 없이는
409 `procurement_opportunity_selection_required`로 거부한다. 임의의 첫 공고나
서버의 최신 선택으로 요청을 바꾸지 않는다. 이 다중 공고에서의 호환성 차이는
API 문서에 명시하며 단일 공고 client 회귀 테스트를 유지한다.

생성 요청은 decision ID/revision을 받는다. router에서 소유권을 확인하고
service가 한 번 읽은 immutable context를 provider 입력, cache identity,
review/Council 연결, 최종 문서 메타데이터까지 전달한다. 생성 도중 선택만
바뀌면 결과는 처음 공고에 저장하되 다른 공고 화면에 표시하지 않는다.
저장 직전 같은 공고의 source/decision revision 변경이 확인되면
409 `procurement_context_changed`를 반환한다. 확인과 문서 저장 사이의
다른 store 쓰기까지 원자적이라고 주장하지 않는다. 문서에는 캡처한 revision을
항상 남기고 저장 직후 및 이후 조회 때 현재 상태와 다시 비교한다. 뒤늦게
발견한 차이는 stale로 반환하며 저장된 과거 산출물을 삭제하거나 최신으로
재귀속하지 않는다. provider 자동 재호출은 없다.
멀티 공고 API-key 호환 client도 명시적 ID/revision 검사를 생략할 수 없다.

새 request 모델은 strict/extra-forbid이며 UUID·revision·operation ID를
서버에서 검증한다. decision revision은 source/evaluation/applicability 변경에
증가하며 선택만의 변경이나 기존 notes-only override 기록으로 불필요하게
증가시키지 않는다. 저장 CAS version과 선택 revision은 별개다.

## 5. 검토와 문서의 출처

Council 최신 세션 키는 tenant/project/decision/use_case/target_bundle이다.
기존 세션은 저장된 source_procurement_decision_id로 연결한다.
source ID가 없거나 맞지 않는 자료를 현재 공고로 임의 재귀속하지 않는다.

새 패키지 manifest와 문서 메타데이터는 project/decision ID, decision revision,
원본 snapshot SHA를 함께 담는다. 패키지 검증기는 새 형식을 명시적으로
검증하며, 기존 형식은 종전 규칙으로 읽는다. 기존 ZIP과 완료 receipt를
재작성하지 않는다. review 목록은 공고별로 필터링하되 기존 tenant/session/
assignee 제한을 그대로 적용한다. 공고 필터는 권한을 부여하지 않는다.

### 작업 4의 내부 계약과 활성화 조건

`ProcurementSourceBinding`은 `procurement.source_binding.v1` 형식으로
tenant/project/decision, decision revision, source kind/ID/timestamp,
canonical record SHA-256과 snapshot별 ID/exact-byte SHA-256/size를 고정한다.
캡처 시 소속을 검증한 backend 경로에서 원문 bytes를 읽는다. 적어도 하나의
snapshot이 필요하며 원문 없는 record는 legacy/unbound 경로에 남는다. 중복 snapshot,
bool revision/size, 알 수 없는 필드, 잘못된 소속 또는 누락된 원문은 거부한다.

binding이 명시된 Council만 decision ID를 포함한 새 키를 사용한다. 기존
project-only 키를 재작성하지 않으며 legacy fallback은 session과 handoff의
source decision ID가 모두 요청 ID와 일치할 때만 허용한다. bound session의
신선도는 현재 캡처와 전체 binding을 비교하므로 같은 timestamp에서 변경된
record/revision/raw bytes도 stale이다. 현재 binding을 확인하지 못하면 current가 아니다.

`decisiondoc.procurement_review_packet.v2`는 위 binding을 manifest에 추가하고
package/scenario/source ID와 timestamp를 교차 검증한다. v1 생성과 ZIP은
유지한다. receipt와 reviewed-package는 실제 내장 packet 버전을 확인하며,
외부 envelope의 v2(reviewer attestation)와 내장 packet v2는 별개의 버전이다.
저장 전과 재조회 때 v2의 scope·receipt 검증은 optional validator 설정과
무관하게 필수다. 검토 완료가 원문 변경 후에도 보존되는 것은 역사 증빙의
불변성을 뜻하며 현재 공고에 대한 유효성이나 실행 승인을 뜻하지 않는다.

휴대용 ZIP에는 원문을 추가로 넣지 않는다. verifier가 확인하는 것은
해시 선언과 패키지의 내부 결속이며 반환값 `source_bytes_verified=false`로
원문을 다시 조회하지 않았음을 표시한다. 외부 서명이나 사실 진실성 증명도 아니다.
기존 review 목록의 `decision_id` query는 담당자·프로젝트 권한 확인 후 적용한다.
v1 자료는 공고 binding을 추정하지 않으므로 명시적 v2 공고 필터에서 제외한다.

기본 앱에서 공고별 Council 실행·packet 생성·신규 완료는 아직 연결하지 않는다.
현재 project-only 완료 경로는 v1 재생성 hash와 일치하지 않는 pending v2를
거부한다. 활성화 전에 저장된 binding의 정확한 decision ID/revision/raw hash로
원문을 resolve하도록 연결하고, 현재 선택된 다른 공고를 대체 사용하지 않는
통합 검사를 완료해야 한다. 이미 완료된 ZIP의 동일 요청 replay는 원본 bytes를
유지해야 한다. 생성·편집본·share의 공통 binding 및 화면 연결은 작업 5·6이다.

A에서 작성한 문서는 B를 선택해도 A에 속한다. A로 돌아왔다는 사실만으로
과거 문서가 최신이 되지 않는다. 본인의 source revision과 현재 A의 revision을
비교한다. A 변경은 B의 freshness를 바꾸지 않는다. 생성 문맥에 공통 지식을
사용했다면 기존 knowledge freshness 규칙도 별도로 적용한다.

검토 완료는 operational_approval=false를 유지한다. 명시적 NO_GO override
사유도 공고 A에서 B로 전이되지 않는다. 기존 public share, generated review,
evidence map consumer까지 출처를 확인해야 통합 완료로 본다.

### 작업 5의 생성 계약

`GenerateRequest`의 `procurement_decision_id`와
`expected_procurement_decision_revision`은 함께 제공하고 `project_id`가 필요하다.
명시 주입된 `ProcurementGenerationResolver`만 새 경로를 사용한다. 기본 factory는
비활성이며, 비활성 경로에 명시적 공고 생성을 요청하면 거부한다. 지원되는 조달
번들에서 공고가 하나이면 ID 생략이 가능하지만 여러 개면 선택을 추정하지 않는다.

resolver는 해당 record와 원문 bytes의 binding을 캡처한다. prompt, Council,
완료 review, evidence refs와 cache identity는 이 캡처를 공유한다. bound 생성에
legacy/unbound Council·review를 적용하지 않는다. 다른 공고의 NO_GO 예외 사유는
사용할 수 없다. 결과 저장 전 동일 ID의 revision·record·원문을 다시 확인하며,
선택만 바뀌면 허용하고 원문이 바뀌면 중단한다. 이미 발생한 provider 사용량 기록은
보존하므로 이를 모든 상태에 대한 zero-write transaction으로 표현하지 않는다.

일반 생성의 source 충돌은 HTTP 409다. SSE는 응답이 시작된 뒤이므로 HTTP 200
스트림의 `error` event에 같은 `procurement_context_changed` code를 전달하고
`complete`는 보내지 않는다. bound 결과를 프로젝트에 연결하지 못한 경우도
`PROJECT_DOCUMENT_UNAVAILABLE` error다. 이때 이미 생성된 bundle·export source·
history는 남을 수 있으며 자동 삭제나 재생성을 하지 않는다.

응답 metadata와 각 doc, 저장된 ProjectDocument, 편집본은 동일한
`source_procurement_binding`을 전달한다. 편집본이 물려받는 것은 출처이지 기존
검토 승인 상태가 아니다. binding 없는 기존 산출물의 source hash와 v1 ZIP 형식은
보존한다. binding이 있는 ZIP에는 v2 manifest를 사용하고 원문 재조회·사실 진실성·
운영 승인과 내부 해시 검증을 구분한다.

문서의 공고 출처 상태와 기존 Council/review 상태는 별도 필드다. 기존 unbound
문서의 Council/review 호환 표시를 지우지 않지만, 그것을 exact source binding의
`current` 증거로 사용하지 않는다. bound 문서의 승인 fingerprint에는 저장된
binding뿐 아니라 현재 캡처한 binding도 포함한다. 이미 stale인 상태에서 원문이
다시 바뀌어도 timestamp가 같다는 이유로 이전 acknowledgement를 재사용하지 않는다.
unbound 문서의 기존 fingerprint 계산은 유지한다.

직접 바이너리 생성 다운로드는 공고 ID/revision/binding SHA 응답 헤더와 해당
request ID의 durable export source를 남긴다. 별도 ZIP을 요청해 manifest와 함께
보관할 수 있지만, 헤더가 사라진 DOCX/PDF 등의 파일만으로 출처가 휴대용 검증되는
것은 아니다. 브라우저 공고 선택은 작업 6에서 격리 검증했지만 기본 앱 활성화와
기존 사용자 데이터 전환은 하지 않았다.

### 작업 6의 scoped lifecycle 계약

`create_app(procurement_multi_opportunity_enabled=True)`는 명시적 opt-in이다.
테스트에서만 임시 backend를 주입하며 환경변수에 따른 자동 전환은 추가하지 않았다.
기존 import의 stale selection은 collector 전에, stale source revision은 수집된
identity 확인 후 parser/provider/snapshot 전에 차단한다. replay는 원래 receipt만
반환하며 현재 record를 과거 결과처럼 섞지 않는다.

Council GET/run과 review packet은 `decision_id`/`expected_decision_revision`
query pair를 검증한다. override는 같은 scope의 JSON과 operation ID를 사용한다.
pending v2 completion은 packet의 immutable binding을 재포착하고 package 검증 후
저장 직전에도 원문을 확인한다. Council 실행 중 원문 변경은 stale로 표시한다.
서로 다른 store의 확인·저장을 원자적 transaction이라고 주장하지 않는다.

opt-in evidence map과 Guided handoff는 선택 공고의 문서·review 및 그 문서에
연결된 approval/workflow만 사용한다. 거부 시 감사 건수도 필터 후 값으로 기록한다.
member는 선택 공고의 배정도 있어야 하며 다른 공고 배정으로 접근할 수 없다.
프로젝트 전체 문서는 별도 목록에 원래 공고 출처와 함께 보존한다. 공고 변경 시
담당 역할 기본값을 다시 계산한다. project API에는 service-worker cache fallback을
사용하지 않으며 늦은 생성·평가 결과가 새 선택의 화면을 덮지 않도록 한다.
새로고침 후에도 같은 scope인지 확인하고 프로젝트 페이지 이탈 시 요청을 무효화한다.

## 6. 화면과 예외

프로젝트 상세에 공고 선택 메뉴와 현재 공고번호를 표시한다. 선택은 조회만
수행하며 추천·Council·검토 완료를 자동 실행하지 않는다. 선택 도중 이전
화면의 문서를 새 공고 문서처럼 보여주지 않는다.

browser는 tenant/user/auth revision/project/decision/selection revision과
request sequence를 캡처한다. 늦은 응답은 해당 scope가 여전히 일치할 때만
표시한다. 실패 시 서버 상태를 다시 읽고 오류를 표시하며 자동 재전송하지
않는다. 권한 없는 tenant/project/decision 조합은 기존 not-found 정책을 따른다.

검증용 목록은 두 공고부터 시작하되 저장 모델은 둘로 제한하지 않는다.
목록은 서버 pagination을 사용하고 선택된 공고가 현재 페이지 밖에 있어도
선택 표시를 유지한다. 페이지 크기는 기본 20, 최대 100이다.

## 7. N/A 의미와 증빙

공통 체크리스트 열 개 범주는 계속 유지한다. N/A는 그 아래 **개별 요구사항**
단위의 검토 주석으로 도입한다. 범주 전체를 없애거나 필수 자격 검사를
끈다는 뜻이 아니다. 두 번째 후보는 이 세부 요구사항과 근거 기록까지 포함한다.

요구사항은 서버가 발급한 requirement ID, 소속 category, title, 원본 snapshot
ID/SHA, 정확한 인용 구간을 가진다. 현재 모델에 자동 추출 기능이 있다고
가정하지 않는다. 1차 입력은 세션 결합 관리자가 원문 구간을 지정하는
명시적 로컬 작성이며 LLM·키워드 부재로 비적용을 추정하지 않는다.

적용 여부는 `applies | not_applicable | unknown`이다. 생성 직후는 unknown이다.
N/A 기록에는 non-empty rationale, snapshot ID/SHA, 인용 구간, server-derived
actor ID와 UTC 시간, expected decision revision, operation ID가 필수다.
원문 구간 일치 검증은 의미의 진실성 검증이 아니며 UI에 사람의 판단으로
표시한다. 자료 부족이나 원문 부재는 unknown으로 남긴다.
snapshot SHA는 저장된 JSON 파일의 정확한 bytes를 대상으로 한다. 첫 범위의
인용 대상은 snapshot의 `announcement.raw_text`이며 시작·끝은 Unicode
code-point offset으로 검증한다. 생성된 structured_context나 추천 요약을
원문 근거로 대체하지 않는다. 원문이 없는 자료는 N/A 확정에 사용할 수 없다.

작성·변경·철회는 `require_session_bound_admin`으로 제한한다. API key,
Ops key, 비담당 member만으로는 적용 여부를 확정하지 못한다. 이는 외부
자격 확인 권한을 부여하는 정책이 아니다. 검토자는 기존 배정 범위에서
근거를 읽고 패키지를 검토하며 새 편집 권한을 자동 부여받지 않는다.

제안 route는 해당 공고 경로 아래 `POST /requirements`와
`POST /requirements/{requirement_id}/applicability`이다. 전자는 title,
category, source snapshot binding과 인용 범위를 받아 unknown 요구사항을
추가한다. 후자는 적용 여부와 근거를 추가하고 unknown 변경을 철회로 기록한다.
둘 다 expected decision revision/operation ID를 검증한다. 삭제 endpoint는
만들지 않는다. GET은 같은 `/opportunities/{decision_id}/requirements` 전용 경로에서
요구사항·변경 이력을 반환한다. 기존 API-key 공고 상세에는 이력을 추가하지 않는다.
세션 admin 또는 해당 공고의 검증된 bound packet에 안정적 user ID로 배정된 member만
조회하며, member에게 내부 actor ID를 노출하지 않는다. 이 배정은 packet 단위로
보존되므로 원문 변경 뒤에도 읽기 권한은 유지되지만 현재 근거나 승인으로 승계되지는
않는다. 비활성 계정·폐기된 세션은 기존 인증 정책으로 차단한다.

같은 범주에 fail/unknown인 관련 hard filter가 있으면 N/A 확정을 거부한다.
category와 hard-filter 대응은 서버의 기존 체크리스트 정의를 재사용하며
client가 제시한 임의 filter 목록을 신뢰하지 않는다. 기존 blocked 상태,
soft-fit 점수, GO/NO_GO 추천, 승인 플래그는 N/A 입력으로 변경하지 않는다.
부분 요구사항 하나의 N/A를 범주 전체 READY로 집계하지 않는다.
세부 요구사항의 unknown/stale 건수는 상위 평가 상태와 별도로 표시한다.
원래의 점수가 높다는 이유로 미확인 세부 요구사항을 숨기지 않는다.

변경·철회는 이력을 추가하고 이전 actor/reason/source binding을 보존한다.
새 원문 snapshot이 생기면 해당 주석을 stale로 처리하고 현재 적용 여부는
unknown으로 표시한다. 재검토 전 자동 승계하지 않는다. 적용 여부 변경은
decision revision을 올려 기존 review/Council/document freshness를 무효화한다.
요구사항의 원래 snapshot/hash/인용은 주석으로 바꿀 수 없다. 새 근거로 판단하려면
새 요구사항을 작성하며 이전 요구사항과 이력은 남긴다. source-set fingerprint는
decision revision과 분리하므로 주석 자체가 자기 근거를 stale로 만들지는 않는다.
원문 bytes를 확인할 수 없으면 조회를 503으로 거부하며 current로 대체하지 않는다.
작성 시 원문을 재확인하지만 원문 파일과 aggregate CAS는 서로 다른 저장 단위다.
둘을 원자적 transaction으로 주장하지 않으며 이후 조회에서도 source set을 비교한다.

새 패키지 형식은 세부 요구사항과 적용 여부를 명시적으로 담는다.
기존 세 가지 package checklist 상태와 혼합하거나 N/A를 READY로
downgrade하지 않는다. 미지원 형식은 오류로 거부한다. 모든 상태 변환기,
validator, HTML/Markdown/DOCX 렌더러가 새 표현을 보존하기 전에는 UI에서
N/A 작성 기능을 노출하지 않는다.

### 작업 8의 구현 계약

`create_app(procurement_multi_opportunity_enabled=True)`인 격리 앱에서만
요구사항 편집과 source-bound v3 검토 패키지를 연결한다. 전역 환경변수로
기본 앱을 활성화하거나 실제 데이터를 전환하지 않는다.

- GET requirements에 `expected_decision_revision`을 전달하고 응답의 decision/revision을
  확인한다. `/requirements/sources`는 관리자 세션과 해당 revision을 요구한다.
  원문 선택은 `announcement.raw_text`를 읽기 전용으로 제공하며 브라우저의
  UTF-16·CRLF 선택 범위를 원래 Unicode code point로 변환한다.
- 관리자 작성 → 적용 여부·근거 기록 → 명시적 검토자 지정 → 기존 POST
  `/procurement/review-packet`으로 검토 패키지 생성 순서다. 배정 검토자는 읽기
  전용이다. 미배정 검토자는 이미 존재하는 요구사항을 self-prepare로 획득할 수 없다.
- 패키지 문서는 `procurement_decision_package.v2`, 바깥 검토 ZIP은
  `decisiondoc.procurement_review_packet.v3`이며, 하위
  `procurement.requirement_applicability.v1` projection을 source binding에 결속한다.
  JSON·체크리스트 Markdown·검토 HTML과 추가 `requirement_applicability.docx`가
  같은 적용 여부·인용·이력을 보존한다. 내부 actor ID는 portable projection에서 제외한다.
- v3 verifier는 DOCX 누락, 미지원 상태, schema downgrade와 다시 hash를 계산한
  렌더링 변조도 거부한다. receipt는 추가 산출물을 포함한 전체 ZIP hash를 검증한다.
  v1/v2 builder 기본값과 기존 pending 패키지의 버전별 완료 검증은 보존한다.
- 저장 직전 같은 entry/revision/source set을 재확인한다. source 장애는 503,
  변경 충돌은 409이며 자동 재시도하지 않는다. source 파일·aggregate·review store는
  하나의 transaction이 아니므로 재확인 이후의 동시 변경까지 원자적으로 막는다고
  주장하지 않는다. 완료된 패키지는 이후 변경에도 최초 바이트로 재조회한다.
- 다운로드 및 저장 성공 표시 직전에 원래 auth/user/tenant/project/decision/selection과
  새로고침 load ID를 다시 확인한다. 페이지·공고·인증 문맥이 바뀌면 원문 폼과
  다운로드 링크를 폐기하며, 늦은 응답은 현재 화면을 갱신하지 않는다.

독립 파일로 받은 패키지는 실제 원문 보유 여부를 검증하지 않으므로
`source_bytes_verified=false`를 유지한다. Word의 줄바꿈 표현은 LF로 정규화하지만
JSON 원문 인용에는 CRLF를 포함한 원래 문자를 보존한다. N/A 집계와 검토 완료는
상위 점수·추천·운영 승인으로 승격되지 않는다.

## 8. 검증과 완료 기준

아래 표는 전체 수용 기준이다. 실제 완료 범위와 실행 결과는 연결된 구현 계획과
procurement STATUS에서 확인한다. 작업 8의 검증도 기본 앱이 아닌 격리 앱에서 수행했다.

| 범위 | 필수 수용 결과 |
|---|---|
| 공고 식별 | A/B를 추가한 뒤 각각 다른 decision ID 유지. 같은 source 재수집은 해당 ID만 갱신 |
| 저장 | local/fake-S3 CAS에서 동시 추가, 선택 충돌, 중복 operation, 장애 후 재조회 검증 |
| 호환성 | v1 fixture 무변경 GET, 승인된 첫 write 전환, legacy snapshots의 소급 평가 금지 |
| 평가 | A의 실패/추천/override가 B에 섞이지 않음. A 재수집은 B 평가를 무효화하지 않음 |
| 검토 | A/B의 Council·review 분리, 다른 tenant·비담당자 차단, 기존 ZIP 바이트 보존 |
| 생성 | A 생성 중 B 선택 시 결과는 A에만 연결. A revision 변경을 저장 전 발견하면 거부, 저장 경합은 stale 표시 |
| 화면 | 선택/새로고침/재열기/다운로드와 늦은 응답을 모바일·데스크톱에서 검증 |
| N/A | actor/source/reason 없는 쓰기 거부, fail/unknown hard filter 우회 거부, 점수/승인 불변 |
| 이력 | N/A 변경·철회 및 source 변경 후 stale 표시, 과거 package/review 보존 |
| 내보내기 | N/A 및 unknown이 ready로 바뀌지 않음, 새 형식 명시 검증, 기존 형식 유지 |

공고별 저장·선택·binding을 먼저 완성하고 N/A를 그 identity 위에 추가한다.
각 후보는 schema/store, service/route, browser/consumer 순으로 통합하되
화면만 열린 상태를 완료로 선언하지 않는다. 기존 평가·검토 회귀, 새 local/
fake-S3 통합, 실제 로컬 API/browser lifecycle이 모두 필요하다.
사용자 데이터 전환, live G2B/AWS/provider, 모델 학습, 배포, commit/push는
별도 승인 범위다. 실제 사용한 Agent 역할·모델과 리뷰 범위는 실행 계획에 기록하고,
현재 task 자체의 모델 전환이나 branch 전체 독립 리뷰로 확대하지 않는다.

## 활성화 전 오프라인 상태 검사

`scripts/procurement_transition_preflight.py`는 운영 앱과 분리된 읽기 전용 CLI다.
승인된 오프라인 복사본의 경로와 tenant를 명시해서 사용한다. 이 명령은 사용법이며
현재 사용자 데이터에 실행한 기록이 아니다.

```bash
python3 -B scripts/procurement_transition_preflight.py \
  --state-file /absolute/path/to/offline-copy/procurement_decisions.json \
  --tenant-id TENANT_ID \
  --expected-sha256 EXACT_SHA256
```

`--expected-sha256`은 선택 사항이며 지정하면 파싱 전에 exact-byte 일치를 요구한다.
자동 디렉터리 검색, .env 로드, 앱/backend 초기화, 원문 조회, 수정·복구·전환은 없다.
stdout JSON에 파일 SHA/크기, 검증된 프로젝트·공고·요구사항·snapshot 참조 건수와
행 번호/차단 코드만 출력한다. 경로·tenant/project/decision ID·메모·인용·상세 오류는
출력하지 않는다. 입력 leaf symlink/특수 파일/16 MiB 초과/관찰된 변경은 거부한다.
읽기는 파일 접근시간 등 OS 메타데이터에 영향을 줄 수 있으며 동시 작성자에 대한
lock이나 미래 데이터의 불변성을 보장하지 않는다.

종료 0/`state_contract_status=pass`는 해당 bytes의 v1/v2 구조만 확인한 것이다.
종료 2는 입력/계약 실패다. 일부 row가 실패하면 합계와 legacy 호환 여부도 unknown
(`null`)으로 남기며, 다른 tenant row나 비객체 row를 정상으로 건너뛰지 않는다.
`activation_allowed=false`, `source_bytes_verified=false`, `writes_performed=false`는
성공 시에도 유지한다. 원문 bytes, 프로젝트 존재·권한, 문서/검토 ZIP·receipt,
환경 설정, backup/복구 가능성은 별도 검증이 필요하다.

v2 row가 하나라도 있으면 기존 reader와 호환되지 않는다. 첫 v2 write 뒤에 단순히
factory flag를 끄거나 tenant state 파일 하나만 과거로 되돌리는 것을 복구로 보지
않는다. 실제 전환 전에는 쓰기 일관성이 확보된 복사본에서 원문·문서·검토 이력을
함께 대조하고, 첫 write와 재시작을 검증해야 한다. 실사용 전환/복구는 대상과
backup 범위가 승인된 경우에만 수행하며 이번 CLI에 자동 실행 경로를 넣지 않는다.

### 전환 후 기존 검토의 호환성

opt-in 앱에서 v2 row를 저장한 tenant에는 v1/v2가 섞일 수 있다. 미완료 v1
검토 완료 시 기존 단일-record store로 tenant 전체를 읽으면 다른 프로젝트의
v2 row 때문에 실패한다. 이 경로는 opt-in project store로 해당 tenant/project를
읽고, 이미 검증된 packet의 `package_id`와 정확히 일치하는 record를 찾는다.
현재 선택된 공고나 목록의 첫 공고를 fallback으로 쓰지 않는다.

담당자 session/identity 검사는 그대로 먼저 수행하며 기존 v1 builder의 전체
packet SHA가 일치해야 완료할 수 있다. 저장 직전 record를 다시 읽어 변경은 409,
손상/조회 불가는 503으로 거부한다. 최종 재검사와 review store CAS는 별개의
작업이므로 다중 store 원자성을 주장하지 않는다. 원문 bytes 검증이나 공고별
접근 권한을 v1 자료에 새로 부여하지 않으며, 공고 필터에서 v1이 제외되는 기존
계약과 ZIP·receipt bytes는 유지한다. 이미 완료된 검토의 동일 요청은 보존된
ZIP을 반환한다. 사용자가 실제 앱의 플래그를 끄는 rollback은 지원하지 않는다.

local/fake-S3 fixture로 기본 앱 종료 후 opt-in 앱을 만들고, 첫 v2 write 후
다시 새 앱/backend 인스턴스를 만들어 원본·receipt·검토 ZIP을 비교했다.
이 작업 10 검증은 동일 Python 프로세스의 앱 재생성이며 실제 데이터 전환이나
OS 프로세스 재시작, backup 복구 완료 증거는 아니다.

후속 작업 11은 임시 local fixture에서 네 별도 Python 프로세스로 정상 종료 후
전환·재개·오프라인 복구를 검증한다. 앱이 닫힌 상태의 전체 fixture를 백업하고,
새 디렉터리에 복사한 뒤 파일별 SHA inventory가 일치하는지 확인한다. 전환된
복사본의 v2 상태를 단일 파일로 되돌리지 않고, 별도 복구 디렉터리에서 이전
v1 snapshot을 연다. 공고 상태와 원문·v1/v3 패킷·완료 ZIP·receipt 보존을 확인하되
로그인/요청으로 생성되는 감사·세션 기록은 복구 앱에서 정상 추가될 수 있다.
원본·백업과 전환 복사본은 그대로 보존한다. 이 방식의 복구 시점 이후 신규
데이터는 이전 백업에 포함되지 않으며 자동 병합하지 않는다.

자식 프로세스는 dotenv 비활성, 명시적인 mock/local 환경, socket 연결 차단 아래
실제 ASGI 앱에 TestClient로 요청한다. 네트워크 서버나 서비스 관리자를 재시작한
시험은 아니다. 동시 작성 중 backup, 비정상 종료·장애 주입, 운영 데이터 복구,
외부 저장소 복구 및 실제 활성화는 이 테스트의 완료 범위에 포함하지 않는다.

## 9. 이번 산출물의 상태

두 도입 기록은 사용자 응답을 근거로 `approved`로 갱신했으며,
`--require-approved` 검증을 통과했다. 이 승인은 로컬·fake-S3 개발만 허용하고
실사용 데이터 전환이나 외부 실행 권한을 부여하지 않는다.
[구현 계획](../plans/2026-09-21-procurement-opportunity-and-applicability.md)에
저장 → API → 검토·문서 출처 → 화면 → 적용 여부 이력 → export 순서와
검증 기준을 기록했다. 문서·JSON 승인 검증은 기능 완료 증거가 아니다.
v2 store·scoped API·Council/review·생성/문서 binding·선택 UI는 factory opt-in으로
연결했다. 임시 local/fake-S3와 mock provider, collector stub를 사용해 검증했으며
desktop/mobile의 import부터 검토·생성·reload·ZIP export까지 실행했다.
작업 7-8의 개별 요구사항 적용 여부/N/A, 배정 검토자 조회, export 및 원문 변경 후
stale 표시를 연결했다. 기본 factory는 계속 비활성이다. 실사용 데이터 전환·운영
활성화·native Word 열기/편집/저장은 미검증이며 제품 전체 완료를 뜻하지 않는다.
