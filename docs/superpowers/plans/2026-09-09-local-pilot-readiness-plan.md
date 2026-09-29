# Local Pilot Readiness: Next Development Plan

Date: 2026-09-09
Status: planning proposal; not a new feature admission or human UAT receipt.

2026-09-14 Goal status: technical verification and isolated UAT server preparation
completed; human UAT not performed. See Goal Execution below. The original plan
and prior receipts remain historical records, not new implementation authority.

2026-09-14 continuation: 사용자가 기존 계획의 다음 mock/local 검증과 UAT 준비
진행을 승인했다. 아래 최초 계획과 9월 9일 실행 이력은 보존한다. 새 기능이나
donor 통합의 admission, human UAT 완료 또는 외부 실행 승인으로 확대하지 않는다.

## Purpose

DecisionDoc의 다음 목표는 기능 수를 늘리는 것이 아니라, 작성자가 만든 문서를
담당 검토자가 실제로 검토하고 완료 패키지를 다시 확인할 수 있는지 검증하는 것이다.
새로운 UAT CLI나 증빙 wrapper를 만들기 전에 이미 구현된 흐름을 사용한다.
자동 검증, 사람의 사용성 판단, 외부 실증은 서로 대체하지 않는다.

이 문서는 다음 작업의 설계와 실행 순서를 제안한다. 제품의 현재 완료 상태는
[canonical snapshot](../../development-plan.md#0-current-completionreadiness-snapshot),
전체 우선순위는 [product execution plan](../../product_execution_plan.md)의 소유다.
기존 승인 decision을 수정하거나 새 기능을 승인하지 않는다.

## Grounded Baseline

- Canonical repository: `/Users/sungjin/dev/personal/DecisionDoc-AI`.
- Inspected HEAD: `618f17a2c89eb81ea09ae0186c7977a05a03afa3`.
- Branch: `codex/generated-document-review-completion-20260904`.
- 시작 시 기존 tracked modification 29개와 untracked file 6개가 있었다.
  기존 변경은 보존하며, 이 계획 문서는 별도 추가 파일이다.
- Generated-document review completion과 reviewed-package verifier CLI는 이미
  구현돼 있다. 과거 test receipt는 새 실행 결과로 합산하지 않는다.
- `docs/test_plan.md`의 Generated-document Local Completion 절에 격리된 mock
  실행 명령과 생성부터 경계 이해까지 7단계 human UAT가 이미 있다.
- 기존 future-feature gate 2개를 이번 점검에서 `--require-approved --json`으로
  검증했다. 둘 다 `status=passed`, `operational_authority_granted=false`였다.
  이는 새 기능이나 donor 채택의 승인, 승인자 신원의 독립 검증이 아니다.
- Human UAT와 M1/M2/M6의 외부 증거는 별도 미완료 조건으로 남는다.

## Options And Decision

| 선택 | 이점 | 비용과 한계 | 권고 |
|---|---|---|---|
| 기존 흐름 검증 후 관측된 문제만 수정 | 기존 구현을 사용하고 실제 공백을 찾는다 | 사람이 내용과 사용성을 검수해야 한다 | 우선 진행 |
| Procurement UAT donor 통합 | package-source binding과 관찰 receipt 후보를 활용한다 | 기존 generated-document 흐름과 계약이 다르며 별도 설계와 admission이 필요하다 | 필요가 관측될 때 재검토 |
| 새 UAT subsystem 또는 광범위 재설계 | 여러 흐름을 통합할 수 있다 | 검증되지 않은 요구를 늘리고 기존 완료 계약을 흔든다 | 현재 제외 |

사용자가 요청한 개발 진행은 기존 기능의 점검부터 시작한다. 구체적인 새 동작은
문제와 설계를 제시하고 승인받은 뒤 구현한다. 현재 선정한 새 제품 코드 범위는
0개다. 이는 개발 완료 선언이 아니라, 근거 없는 기능 추가를 하지 않는다는 뜻이다.

## Existing Architecture And Flow

기존 route → service → schema/storage/provider 경계를 유지한다.

```text
격리된 mock/local 실행
  → synthetic 문서 생성 및 프로젝트 저장
  → active 담당자에게 pending review 전달
  → 담당자의 기존 인증 경로에서 decision과 근거 기록
  → completed package 재다운로드
  → 기존 standalone CLI로 내부 무결성 확인
  → 사람이 내용, 레이아웃, 의미와 권한 경계를 확인
```

`accepted`, `changes_requested`, `rejected`는 모두 유효한 검토 결과다.
검증 성공은 운영 승인, 발급자 진위, source 최신성 또는 법적 권한을 뜻하지 않는다.
인증 실패, 담당자 불일치, source drift, 경쟁 완료, stale browser response와
손상된 ZIP은 기존 계약대로 차단돼야 한다. 새 우회 경로나 자동 복구는 추가하지 않는다.

## Model Allocation

| 역할 | 모델과 추론 강도 | 담당 범위 |
|---|---|---|
| 설계와 우선순위 | Astra medium | 현재 계약, 대안, 의존 순서, 변경 범위와 완료 기준 |
| 일반 구현과 통합 | Sol high | 기존 흐름의 기술 검증, 관측된 일반 결함의 최소 수정 |
| 좁은 테스트와 문서 | Luna max | 확정된 계약의 회귀 테스트, 사용 문서와 기록 정합성 |
| 높은 위험의 변경 | Terra xhigh | 인증, 권한, tenant 경계, 상태 전이와 오류 처리 |
| 동시성 및 불확실한 결과 | Terra xhigh | CAS, 재시도 identity, competing completion, lost-response 검증 |

위 표는 2026-09-14 사용자 지정 기준이다. 9월 9일 설계에는 Astra medium을 실제
배정했다. 당시 기존 무료 모드와 CLI의 한정된
baseline 검증에는 Sol medium을 배정했다. Luna/Terra는 향후 해당 작업이 생겼을
때의 배정 기준이며, 이번에 구현을 수행했다고 기록하지 않는다.

한 의존 경로에는 한 작업만 진행한다. 같은 파일을 두 agent가 동시에 수정하지
않으며, 구현자와 리뷰어를 분리한다. 모든 모델을 사용하기 위해 일을 만들지 않는다.
이전 Orca routing이나 외부 coordinator를 재가동하지 않는다.

## Execution Sequence

### 1. Technical Baseline

Sol high가 기존 무료 모드와 CLI 테스트부터 확인한다. 이후 UI 검수 준비 단계에서
API/storage와 browser regression으로 범위를 넓힌다. 환경과 명령을 먼저 검토하고,
기존 데이터가 아닌 별도 임시 경로의 synthetic fixture만 사용한다.

```bash
python3 -m pytest -q tests/test_free_mode.py tests/test_verify_generated_document_reviewed_package.py --tb=short
python3 -m pytest -q tests/test_generation_export_packet.py tests/storage/test_generated_document_review_store.py tests/test_generated_document_reviews.py tests/test_future_feature_gate.py --tb=short
python3 -m pytest -q tests/e2e/test_main_flow.py -k generated_document_review --browser chromium --tb=short
```

위 명령 목록은 검증 계획이다. 이 문서 자체는 실행 receipt가 아니다. 실행 시
환경변수, 격리 경로, 실제 명령, exit code, 통과/실패/skip와 warning을 구분한다.
실패는 원인을 먼저 분류하고, 누락 dependency를 자동 설치하거나 live test로 바꾸지 않는다.

### 2. Local UAT Preparation

기존 `scripts/run_free_local.py --provider mock`과 `docs/test_plan.md`의 격리
명령을 사용한다. 미사용 loopback 포트와 새 데이터 경로를 사용하며 기존 계정,
프로젝트, 설정, donor의 runtime 데이터를 가져오지 않는다.
기술 검수 결과와 사람이 수행할 항목을 구분해서 전달한다.

### 3. Human Observation

실제 작성자와 담당 검토자가 기존 7단계를 수행한다. 새 양식 대신 기존 UAT
템플릿에 예상/실제 결과, 도움받은 부분, 재현 절차와 미해결 문제를 기록한다.
문서의 의미와 표/레이아웃을 직접 열어 보고, 검토 결과가 운영 승인과 다름을
설명할 수 있는지 확인한다. Agent는 사람의 사용성 결과를 대신 작성하지 않는다.

### 4. Bounded Development

Astra medium이 관찰을 다음과 같이 분류한다.

- 기존 계약의 버그: 동일 경로의 실패 테스트로 재현하고 최소 수정한다.
- 사용 문서 문제: 동작을 바꾸지 않고 기존 안내를 고친다.
- 새로운 동작 요청: 요구와 exact file scope, acceptance criteria, authority를
  새 feature gate에 제안하고 승인 후 구현한다.
- 외부 품질/운영 문제: local mock의 성공으로 해소하지 않고 별도 승인 조건으로 남긴다.

각 구현 Goal은 재현 사례, 파일 목록, 제외 범위, 테스트 명령, 완료 조건을 먼저
고정한다. 수정 전 실패를 확인하고, 수정 후 같은 경로를 통과시킨다. 관측 전에는
관련 없어 보이는 route/service/storage 파일을 미리 writable scope로 지정하지 않는다.

### 5. Review And Close-Out

독립 리뷰에서 변경 의도, 권한, 오류 처리, 정보 노출, 회귀 위험을 확인한다.
문서와 README는 검증된 변화만 반영하고 기존 portfolio sync 경로를 사용한다.
필요할 때 관련 full regression과 browser 검증을 실행하되 과거 receipt와 합산하지 않는다.
Commit/push는 별도 요청 시 같은 목적의 변경을 묶어 진행한다.

## Donor Policy

세 후보는 다음 경로에서 source reference로만 보존한다.

- `/Users/sungjin/dev/personal/DecisionDoc-AI-donors/procurement-uat-19e`
- `/Users/sungjin/dev/personal/DecisionDoc-AI-donors/procurement-uat-content-snapshot`
- `/Users/sungjin/dev/personal/DecisionDoc-AI-donors/procurement-uat-source-hash`

서로 다른 후보를 최신판 또는 검증된 완성품으로 단정하지 않는다. 기존 UAT로
충족할 수 없는 요구가 관측될 때만 source binding, receipt, 개인정보와 파일
입출력 계약을 비교한다. 필요 부분만 native 구현에 반영하며 통째로 merge하지 않는다.

## Acceptance And Stop Rules

- 기술 단계: 지정한 현재-tree 검증의 결정적인 종료 결과가 있고 실패 원인이 분류됨.
- 사람 단계: 실제 수행자의 관찰이 있으며 자동 검증과 혼동하지 않음.
- 수정 단계: 승인된 scope의 재현 테스트와 관련 회귀가 통과하고 독립 리뷰 완료.
- 인계 단계: 사용 명령, 알려진 한계와 미해결 blocker가 기존 문서와 일치함.
- 권한 혼동, source 불일치, 잘못된 ZIP 또는 입력 유실은 해당 흐름을 중단하고
  증거를 보존한다. 임의 retry, repair, 데이터 삭제로 결과를 통과시키지 않는다.
- AWS/provider/G2B 호출, training, 배포, 공개, 입찰/법적/계약상 효과는 범위 밖이다.
- 기존 파일 drift 또는 scope 확장이 생기면 원인을 확인하고 계획을 다시 제시한다.

## Targeted Execution Evidence

2026-09-09 Sol medium worker 결과: 위 첫 단계의 두 test 파일에서 exit `0`,
`57 passed, 1 warning in 8.27s`. Warning은 기존 Starlette TestClient의 httpx
deprecation이다. Parent는 worker가 보존한 시험 전후 tracked/staged diff hash,
untracked 목록/content hash와 Git status가 같은지 직접 비교해 일치를 확인했다.
이 계획 문서는 시험 baseline에 포함돼 있었고, 시험 후 이 결과 절만 추가했다.

실행 이력의 정확한 명령은 다음과 같다. 아래 `/tmp` 경로는 보존된 시험 자료다.
다음 실행에서는 새 임시 경로를 사용하고 이 `--basetemp`를 재사용하지 않는다.

```bash
env -i \
  PATH="$PATH" HOME="$HOME" \
  TMPDIR="/tmp/decisiondoc-targeted-baseline.Tpug5e" \
  PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS= \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  ENVIRONMENT=test DECISIONDOC_ENV=dev \
  DECISIONDOC_PROVIDER=mock \
  DECISIONDOC_STORAGE=local DECISIONDOC_STATE_STORAGE=local \
  DATA_DIR="/tmp/decisiondoc-targeted-baseline.Tpug5e/data" \
  EXPORT_DIR="/tmp/decisiondoc-targeted-baseline.Tpug5e/export" \
  AWS_EC2_METADATA_DISABLED=true \
  AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null \
  python -B -c 'import dotenv, pytest; dotenv.load_dotenv = lambda *args, **kwargs: False; raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "--basetemp=/tmp/decisiondoc-targeted-baseline.Tpug5e/pytest", "tests/test_free_mode.py", "tests/test_verify_generated_document_reviewed_package.py"]))'
```

`.env` 로딩은 시험 process 안에서만 no-op으로 차단했고 repository 설정이나
제품 코드는 수정하지 않았다. Plugin autoload와 pytest cache도 비활성화했다.
따라서 이 결과는 해당 격리 조건의 두 파일에 대한 검증이며, 기본 환경의 전체
suite, API/storage 통합 재실행, browser E2E, 서버 기동과 human UAT의 증거가 아니다.
Parent가 같은 테스트를 별도로 재실행한 결과로 중복 계산하지 않는다.

계획 문서의 로컬 링크와 명시된 테스트 경로 존재를 확인했고 trailing whitespace
검사와 `git diff --check`도 통과했다. Product source, donor, 기존 승인과 README는
이번 설계/검증 작업에서 수정하지 않았다.

## 2026-09-14 Technical Verification And UAT Preparation

- [x] Astra medium: 기존 7단계 UAT와 계정 준비, 증거 범위 검토.
- [x] Sol high: fresh temporary storage로 focused regression과 selected browser 검증.
- [x] Luna max: `docs/test_plan.md`에 최초 관리자/동일 tenant의 담당자와 비담당자
  준비, SMTP 불필요, local UAT와 운영 preflight의 차이를 보완.
- [x] Parent: worker receipt/log와 UI 메뉴·등록 계약을 직접 대조하고 문서 검토.
- [ ] 실제 사람이 계정과 문서를 준비하고 7단계 UAT 수행.
- [ ] 관찰된 결함의 재현과 bounded development. 현재 새 제품 코드 변경 없음.

| 실제 실행 | 결과 | 증거 |
|---|---|---|
| Free-mode, CLI, packet, review API/storage, gate, UI-static 7개 파일 | `170 passed, 1 warning in 44.34s`, exit 0 | `focused-suite.log`, `focused-suite.receipt.json` |
| `tests/e2e/test_main_flow.py -k generated_document_review --browser chromium` | `8 passed, 103 deselected in 15.52s`, exit 0 | `e2e-suite.log`, `e2e-suite.receipt.json` |

증거 root는 `/tmp/decisiondoc-verification-20260914.WksaVe`이며 exact argv와 timeout,
실행 시간, process group은 receipt에 있다. 임시 증거는 영구 배포 receipt가 아니며
해당 basetemp를 후속 실행에서 재사용하지 않는다. Parent는 로그의 최종 count와
receipt의 exit 0 및 `timed_out=false`를 확인했다. 이전 통과 수와 합산하지 않는다.

실행 환경은 Python 3.12.12, pytest 8.3.2, pytest-playwright 0.7.2, Playwright 1.58.0이다.
`requirements.txt`의 pytest 9.0.2 고정 환경과 다르므로 lock/pinned 환경의 검증으로
표시하지 않는다. 설치는 하지 않았다. Warning은 기존 Starlette/httpx deprecation이다.
`env -i`, dotenv의 process-local no-op, plugin autoload/cache 비활성화, mock/local,
fresh DATA_DIR/EXPORT_DIR, AWS credential/config `/dev/null` 조건으로 실행했다.
Browser에는 기존 pytest-playwright plugin만 명시적으로 로드했다.

최초 focused harness는 inline Python의 escaped newline 구문 오류로 collection 전에
exit 1이었다. `focused-suite.harness-attempt1.log`와 receipt를 보존했으며 실행 명령을
수정한 다음 새 basetemp에서 얻은 결과만 위 표에 계산했다. 제품/test code는 바꾸지 않았다.
Worker의 comparison은 예상된 두 문서 변경을 제외한 tracked/untracked content가
동일함을 확인했다. Worker가 시작한 process group 잔존은 0으로 보고했다.

Browser 검증은 synthetic UI state와 intercepted response를 사용하는 계약 검증이다.
실제 UI → persisted backend 전체 연결 또는 human UAT 완료 증거로 해석하지 않는다.
계정 생성과 수동 UAT용 상시 server는 시작하지 않았다. 사용자는 `docs/test_plan.md`의
기존 격리 실행 명령과 보완된 계정 준비 절차로 이어갈 수 있다. 새 UAT 도구, donor 통합,
제품 코드/기존 데이터/승인 변경, 외부 호출, commit/push는 이번 범위에 없었다.

## 2026-09-14 Isolated UAT Launch: Not Running

사용자의 후속 진행 요청으로 Sol high가 실제 수동 UAT용 서버 기동을 시도했다.
현재 접속 가능한 UAT 서버는 없으며 계정 생성과 human UAT를 실행하지 않았다.

1. `/tmp/decisiondoc-review-uat.CKTxtN/server.log`: Python 3.12.12에서
   `ModuleNotFoundError: No module named 'annotated_doc'`로 FastAPI import 전에 종료.
   시도한 PID 34640은 종료됐다. Parent의 read-only module lookup은 해당 package가
   `/Users/sungjin/.local/lib/python3.12/site-packages`에 이미 설치돼 있음을 확인했다.
   Fresh HOME으로 바뀐 user-site 탐색 경로가 첫 실패 원인이며 미설치로 단정하지 않는다.
2. `/tmp/decisiondoc-review-uat.fSBkxt/launch.receipt`: 기존 user-site를 PYTHONPATH에
   명시하고 fresh HOME/data와 dotenv 차단을 유지한 두 번째 launch. PID 48510은
   종료됐고 `server.log`는 0 bytes다. Python diagnostic 전에 종료된 이유는 미확인이다.
   Receipt의 command에는 Python 본문이 요약돼 있어 byte-exact 재현 명령은 아니다.

실패 디렉터리는 보존했다. 추가 package 설치, 기존 data 변경, account 생성, donor
통합, 외부 호출 또는 제품 코드 변경은 하지 않았다. `/health`와 초기 UI를 검증할
수 없으므로 이전 170/8 test 결과를 이번 기동 성공으로 대신 기록하지 않는다.

다음 조건은 기존 의존성을 유지한 상태에서 foreground/supervised 실행의 stdout과
exit signal을 확보해 두 번째 실패를 진단하는 것이다. 임의 추가 background launch나
설치로 우회하지 않는다. 기동과 HTTP/UI 확인이 성공하기 전까지 human UAT 준비는
완료가 아니다. 제안됐던 `http://127.0.0.1:8787`은 현재 사용 가능한 서비스 URL이 아니다.

## 2026-09-14 Foreground UAT Launch: Running At Verification

후속 사용자 요청으로 foreground/supervised PTY 실행을 확인했다. 새로운 설치나
제품 수정 없이 기존 user-site를 PYTHONPATH에 명시하고 fresh HOME/data, process-local
dotenv no-op 및 기존 `build_free_environment`를 사용했다. `Application startup complete`
출력을 확인했다. 앞선 실패 기록은 보존하며, 이전 background launch가 무로그로
종료된 원인 자체는 아직 확정하지 않는다.

- 확인 시 URL: `http://127.0.0.1:8787/`, PID 90626, terminal session 37297.
- 새 HOME: `/tmp/decisiondoc-foreground-uat.lhN1QT`.
- DATA_DIR/EXPORT_DIR: `/tmp/decisiondoc-foreground-uat.lhN1QT/data`.
- Python: `/Users/sungjin/.local/share/mise/installs/python/3.12.12/bin/python3`.
- PYTHONPATH: `/Users/sungjin/.local/lib/python3.12/site-packages`.
- `/health`: HTTP 200, `status=ok`, `free_mode=true`, 모든 provider route `mock`.
- `/`: HTTP 200. 실제 browser에서 로그인과 관리자 계정 만들기 form을 확인하고
  빈 등록 화면을 인계했다. 계정·비밀번호 입력/제출은 하지 않았다.
- `quality_first=degraded`는 mock에 실제 cloud provider 품질 증거가 없다는 뜻이다.
  이를 해결하기 위한 provider 호출, 비용 발생 또는 운영 준비성 승격은 하지 않는다.

UAT용 서버만 유지한다. 종료는 해당 terminal에서 Ctrl+C를 사용한다. 별도 shell에서
종료해야 하면 PID 90626이 여전히 이 URL의 UAT process인지 먼저 확인한다. 이 임시
process와 경로는 영구 서비스가 아니므로 다음 작업에서 생존 여부를 재확인한다.
Human UAT, 문서 생성/완료 및 실제 내용·레이아웃 검수는 여전히 수행 전이다.

## 2026-09-14 Popup And Style Completion Slice

사용자가 팝업 표시 수정과 문서 생성·학습 보완을 요청했다. Astra medium의
소스 검토로 범위를 정하고 Sol high가 다음 세 항목을 구현한다.

1. Onboarding의 미정의 CSS token을 기존 token으로 교체하고 불투명한 배경,
   작은 화면의 줄바꿈과 내부 스크롤을 검증한다.
2. 문체 분석의 잘못된 JSON·필드·빈 예시·분석 예외는 저장하지 않는다.
   여러 파일의 부분 성공은 성공과 실패를 분리해 알리고 자동 재시도하지 않는다.
3. 생성 prompt는 bundle에 맞는 최근 유효 예시 두 개를 사용한다. 전체 저장
   예시와 수동 tone guide는 보존하며 정확도 향상 보장 문구는 제거한다.

여기서 문체 학습은 저장한 지침과 예시의 prompt 반영이다. Mock은 실제 문체
분석·생성 품질을 증명하지 않으며 model weight training, dataset upload,
provider 실호출은 실행하지 않는다. 기존 사용자 계정과 onboarding 완료 상태,
dirty worktree를 보존한다. Commit/push/deploy 및 donor 통합은 범위 밖이다.

세 항목의 구현을 완료했다. 기존 170/8 결과를 이번 변경의 새 검증으로 재사용하거나
전체 제품 완료로 확대하지 않는다. 새 검증은 다음과 같다.

- `pytest -q tests/test_style_system.py tests/test_onboarding_ui.py --tb=short`:
  **40 passed, 1 warning in 3.23s**. 분석 결과 검증, 부분 성공, mock 저장 거부,
  동기 TypeError의 단일 호출, 최근 예시의 prompt 연결과 popup 렌더링을 확인했다.
- Popup은 실제 stylesheet를 격리된 fixture에 적용한 Chromium desktop/mobile/
  short-height 검증이다. `/tmp/decisiondoc-popup-style-final-xbz_wx8r/`의
  mobile/short screenshot을 직접 확인했다. 모든 onboarding 단계의 실제 앱 동작과
  style 알림의 browser interaction까지 검증한 것은 아니다.
- 독립 read-only review에서 P1/P2 없음. 동기 TypeError 테스트 보강 권고를 반영했다.
  변경 Python compile과 `git diff --check` PASS. Full suite는 재실행하지 않았다.

- 생성 회귀: `tests/test_generate.py tests/test_stabilizer.py
  tests/test_generation_export_packet.py`를 `pytest -q --tb=short`로 실행해
  **113 passed, 1 warning in 72.86s**를 확인했다. Fresh HOME/data, dotenv no-op,
  credential 없는 mock/local 환경에서 기존 Chromium 경로를 명시했다.
- 첫 실행은 **109 passed, 4 failed**였다. 세 startup-negative 테스트는
  free-mode 차단과 일반 missing-key 오류의 기대치 차이, PDF 테스트는 임시 HOME의
  Chromium cache 미발견이었다. 제품 코드를 바꾸지 않고 해당 테스트 process의
  `DECISIONDOC_FREE_MODE=0`,
  `PLAYWRIGHT_BROWSERS_PATH=/Users/sungjin/Library/Caches/ms-playwright`로 재실행했다.
  실행 중인 UAT 서버의 free mode는 변경하지 않았다. 추가 설치·실제 provider 호출은 없다.

반영 후 동일 HOME/data로 UAT 서버를 재시작했다. 기존 process 90626은 연결 대기 뒤
두 번째 interrupt로 종료했고, 단순 socket preflight는 Address already in use로
실패했다. Listener가 없음을 확인한 뒤 uvicorn 자체 bind로 기동했다.
새 PID는 14625, terminal session은 31945다. `/health` HTTP 200, `free_mode=true`,
모든 provider route `mock`을 재확인했고 browser reload 후 관리자 로그인과 기존
onboarding 완료 상태가 유지됐다. 로컬 개발용 JWT default 경고가 있으므로 이 환경을
외부 공개하거나 운영용 인증 구성으로 취급하지 않는다.

## 2026-09-14 Manual Style Examples

사용자의 기능 완성 우선 요청에 따라 provider 없는 직접 예시 등록을 구현한다.
기본 local LLM 주소 `127.0.0.1:11434/api/tags`는 연결되지 않았다. 다른 주소나
모델의 설치 여부를 단정하지 않으며 설치·모델 다운로드·유료 호출로 우회하지 않는다.

- 기존 프로필에 예시 이름, 문장, 선택 bundle을 직접 등록한다.
- 기존 tenant-bound StyleStore와 생성 prompt 연결을 재사용한다. 서버에서 작성자와
  시각을 기록하고, AI 분석 결과로 위장하거나 tone guide를 자동 변경하지 않는다.
- 엄격한 입력 제한, 성공 후 재조회, 삭제, 최근 예시 생성 반영, 오류 시 입력 보존과
  중복 제출 차단을 검증한다. 예시와 이름은 HTML이 아닌 텍스트로 렌더링한다.
- 기존 계정·데이터·dirty 변경을 유지한다. 모델 가중치 학습과 외부 호출은 범위 밖이다.

같은 작업에서 생성 UI의 `style_profile_id`가 prompt에서 무시되는 결함도 확인했다.
Astra medium이 다음 계약을 정리했고, tenant/cache 경계를 포함하므로 Terra xhigh가
별도 생성 파일 범위에서 구현한다.

- 명시한 프로필은 현재 tenant에서만 조회한다. 없으면 기본값으로 대체하지 않는다.
- 선택 생략은 기본 프로필을 사용한다. 선택 자체가 기본 프로필 설정을 바꾸지는 않는다.
- provider 호출과 cache 조회 전에 스타일 snapshot을 만들고 cache와 prompt가 같은
  snapshot을 사용한다. 같은 ID의 예시·tone 변경이나 기본 프로필 변경도 캐시에 반영한다.
- 첨부/SSE 경로에서도 잘못된 선택은 provider 실행 전에 차단한다. 사용자 입력으로
  private snapshot을 주입할 수 없고, store 손상을 not-found로 숨기지 않는다.
- 수동 예시와 선택 반영은 fake provider/임시 storage로 검사한다. 실제 local LLM
  설치·실행·품질 검증, cloud provider와 모델 학습 완료를 의미하지 않는다.

Manual UI 검증에서는 bundle 표시의 HTML 주입과 저장 후 지연 GET이 이전 프로필을
다시 여는 문제를 각각 재현했다 (`2 failed, 2 passed`). 표시값 escaping과 응답 시점의
captured profile guard로 수정한 뒤 동일 Chromium 테스트 `4 passed in 2.19s`를 확인했다.
`tests/test_style_system.py tests/test_manual_style_ui.py`는 worker 검증에서 51 passed다.
실제 사용자의 계정에는 테스트 예시를 추가하지 않았다.

생성 snapshot 검토에서는 request-private snapshot의 다른 tenant/service 재사용 위험을
확인했다. Request에 snapshot을 보관하지 않고, route 사전 검증과 service의 실제
snapshot 확정을 분리하는 방식으로 보완한다. 사전 검증 이후 삭제된 명시 프로필은
service에서 다시 거부하고, service 내부의 cache/prompt는 같은 snapshot을 유지한다.

구현과 최종 검증을 완료했다. 관리 화면으로 가는 기존 진입 경로 누락도 수정해
생성 화면의 `스타일 관리`와 `문서 생성으로` 복귀 버튼을 연결했다. 복귀 시 유효한
선택을 유지하며, 삭제된 선택은 현재 목록에 맞게 정리한다.

최종 명령은 격리된 mock/local 환경에서 다음 pytest selection으로 실행했다.

```bash
python3 -m pytest -q tests/test_generation_style_selection.py \
  tests/test_style_system.py tests/test_manual_style_ui.py \
  tests/test_onboarding_ui.py tests/test_generate.py \
  tests/test_stabilizer.py tests/test_generation_export_packet.py --tb=short
```

- **184 passed, 1 warning in 103.98s**. 실행 root:
  `/tmp/decisiondoc-features-verified-ciy9jt1h`. `env -i`, fresh HOME/DATA_DIR,
  dotenv no-op, `DECISIONDOC_FREE_MODE=0`, mock provider와 기존 Chromium을 사용했다.
  Free-mode 전용 정책이 아니라 일반 설정 오류 기대 테스트도 포함하므로 test process만
  free flag를 껐으며 cloud credential과 provider 실호출은 없었다.
- 첫 결합 실행은 183 passed/1 failed였다. 두 service fixture가 같은 임시 HOME을
  중복 mkdir한 오류를 수정한 후 위 selection 전체를 재실행했다.
- Browser fixture 동작 6개는 저장/실패/표시/지연 응답뿐 아니라 관리 진입·복귀와
  선택 유지까지 포함한다. 독립 review의 P2들과 snapshot malformed 조합도 보완했다.
- 12개 변경 Python 파일 syntax compile, `git diff --check` PASS. Full repo suite와
  실제 AI 출력의 품질 검증은 실행하지 않았다.
- 동일 UAT data로 정상 종료/재시작했다. 새 PID 36358, terminal session 71084.
  `/health` HTTP 200, free mode true, provider routes mock. 실제 browser의 기존 관리자
  로그인, 스타일 관리 진입과 생성 화면 복귀를 확인했다. 계정이나 실제 프로필을
  생성·변경하지 않았다. 개발용 JWT default 경고는 그대로이며 운영 공개 대상이 아니다.

이 결과는 기능 경로의 local/mock completion이다. Local LLM 연결·실문서 품질,
유료 provider, dataset upload/model training, AWS/deploy, commit/push를 증명하거나
승인하지 않는다.

## 2026-09-14 Style Detail And Autosave Follow-Up

후속 사용 요청으로 실제 편집 경로의 두 결함을 보완했다. 상세 화면의 이름·설명·
추가 규칙·선호/금지 표현·bundle override가 HTML로 해석되는 문제와, 지연된 tone
autosave가 다른 프로필의 현재 입력을 읽는 문제를 Chromium에서 재현했다
(`2 failed, 6 deselected`).

- 표시에는 기존 escapeHtml을 적용하고, textarea/input의 원래 문자열은 보존했다.
- Autosave는 편집 시점의 값과 인증 headers를 캡처한다. 프로필별 debounce로 다른
  프로필 편집이 앞선 저장을 취소하지 않으며, 인증 문맥이 바뀌면 대기 요청을 보내지 않는다.
- 저장 결과 알림은 원래 편집 화면이 여전히 활성일 때만 표시한다. API/storage 계약과
  권한은 바꾸지 않았다. 이미 실행 중인 서버 write의 취소나 다중 client 동시 편집을
  검증한 것은 아니다.
- `pytest -q tests/test_manual_style_ui.py tests/test_style_system.py
  tests/test_generation_style_selection.py tests/test_onboarding_ui.py --tb=short`:
  **75 passed, 1 warning in 11.37s**. Fresh HOME/data, dotenv no-op, mock/local,
  기존 Chromium으로 검증했다. 실행 root는 `/tmp/decisiondoc-tone-verified-i1qlkfsv`다.
- `git diff --check` PASS. Full suite/실제 provider/모델 학습은 실행하지 않았다.
  Static-only 변경이므로 서버를 재시작하지 않았고, 사용자의 편집값을 보존하기 위해
  열린 탭의 강제 reload도 하지 않았다. 다음 페이지 reload부터 새 화면 코드가 적용된다.

## 2026-09-14 Style Upload Analysis Follow-Up

문서 업로드 분석 UI의 누락된 auth headers를 기존 `getAuthHeaders()`로 연결했다.
Multipart Content-Type은 browser가 생성한다. 파일 입력과 upload 버튼은 요청 중
잠그고 종료 시 복구하며, 파일 입력을 비워 같은 파일을 사용자가 다시 선택할 수 있다.
자동 retry는 없다. 결과 표시와 상세 재조회는 시작 시점의 profile, input DOM,
auth context가 유지될 때만 적용한다. 서버에서 이미 시작한 분석은 취소하지 않는다.

- 변경: `app/static/index.html`, `tests/test_manual_style_ui.py`, `docs/test_plan.md`.
- `pytest -q tests/test_manual_style_ui.py tests/test_style_system.py
  tests/test_generation_style_selection.py tests/test_onboarding_ui.py --tb=short`:
  **79 passed, 1 warning in 13.01s**. Fresh HOME/data, dotenv no-op, mock/local,
  외부 요청을 차단한 Chromium fixture. Root: `/tmp/decisiondoc-analysis-verified-9epm8e0s`.
- 첫 재현 실행은 테스트 자체가 pending Promise를 기다려 중단했다(exit 143).
  중복 호출을 기다리지 않고 count를 검사하도록 수정한 뒤 위 gate를 완료했다.
  최초 실행을 RED/PASS 증거로 사용하지 않는다.
- Full suite, 실제 provider 분석, 학습, 배포, commit/push는 실행하지 않았다.
  사용자 서버 재시작이나 열린 화면 강제 reload도 하지 않았다.

## 2026-09-14 Sketch Editing Follow-Up

`renderSketch()`가 AI 응답·검색 문구를 HTML로 삽입하는 문제를 문서형·발표형
Chromium fixture에서 재현했다(`2 failed, 1 passed in 2.02s`). 기존 `escapeHtml`을
제목·항목·페이지·슬라이드·검색 문구에 적용했다. 편집 가능한 UI는 유지하고
`_captureSketchEdits()`의 문자 보존과 빈 구성안 전환을 테스트했다.

- 변경: `app/static/index.html`, `tests/test_sketch_ui.py`, `docs/test_plan.md`.
- `pytest -q tests/test_sketch_ui.py tests/test_manual_style_ui.py
  tests/test_style_system.py tests/test_generation_style_selection.py
  tests/test_onboarding_ui.py --tb=short`: **82 passed, 1 warning in 18.00s**.
  Fresh HOME/data, dotenv no-op, mock/local 환경과 외부 요청 차단 Chromium을 사용했다.
  Root: `/tmp/decisiondoc-sketch-verified-74jv2hpk`.
- 실제 provider, 검색, 학습, full suite는 실행하지 않았다. 서버 재시작,
  사용자 탭 reload, 데이터 변경, commit/push도 하지 않았다.

## 2026-09-14 Tone Save Ordering Follow-Up

같은 프로필의 자동저장 PUT이 중첩되는 문제를 지연 응답 fixture로 재현했다
(`3 failed, 14 deselected in 8.08s`). 프로필별 Promise chain으로 요청을 순차
전송한다. 실패한 요청을 자동 retry하지 않고 사용자가 입력한 후속 편집을 처리한다.
전송 직전 auth context를 다시 확인하고 현재 form 값과 다른 이전 응답의 알림은
표시하지 않는다. API/storage/auth 계약은 변경하지 않았다.

- 변경: `app/static/index.html`, `tests/test_manual_style_ui.py`, `docs/test_plan.md`.
- `pytest -q tests/test_sketch_ui.py tests/test_manual_style_ui.py
  tests/test_style_system.py tests/test_generation_style_selection.py
  tests/test_onboarding_ui.py --tb=short`: **85 passed, 1 warning in 25.86s**.
  Fresh HOME/data, dotenv no-op, mock/local 환경과 외부 요청 차단 Chromium 사용.
  Root: `/tmp/decisiondoc-tone-order-verified-mgyl2s5q`.
- 보장은 현재 page의 요청 순서에 한정한다. 여러 탭·client 동시 편집,
  응답 유실 후 서버 commit 순서, page 종료 시 대기 저장 보존은 범위 밖이다.
- 실제 provider/학습/full suite, 서버 재시작, 사용자 탭 reload, commit/push는
  실행하지 않았다.

## 2026-09-14 Sketch Response Ordering Follow-Up

겹친 `runSketch()` 요청의 이전 응답이 최신 구성안·오류 상태를 덮어쓰거나
새 요청의 버튼을 해제하는 문제를 재현했다(`3 failed, 3 deselected in 11.85s`).
Page-local request sequence로 최신 호출만 결과, 오류, 자체 finally를 반영한다.
공통 retry/auth refresh와 서버 실행은 변경하지 않았다.

- 변경: `app/static/index.html`, `tests/test_sketch_ui.py`, `docs/test_plan.md`.
- `pytest -q tests/test_sketch_ui.py tests/test_manual_style_ui.py
  tests/test_style_system.py tests/test_generation_style_selection.py
  tests/test_onboarding_ui.py --tb=short`: **88 passed, 1 warning in 20.97s**.
  Fresh HOME/data, dotenv no-op, mock/local 및 외부 요청 차단 Chromium fixture.
  Root: `/tmp/decisiondoc-sketch-order-verified-41wc0wye`.
- 검증은 구성안 요청 순서와 결과 반영에 한정한다. 로그인 전환, 바깥 generate
  handler 전체의 동시 실행, 요청 취소·서버 실행 중단은 검증하지 않았다.
  Full suite, 실제 provider/학습, 서버 재시작, 사용자 탭 reload, commit/push는 없다.

## 2026-09-14 Manual Style To DOCX Lifecycle

개별 기능을 잇는 API 통합 테스트를 `tests/test_generation_style_selection.py`에
추가했다. 수동 예시 등록, 선택 스타일의 generation prompt 반영, mock 문서 생성,
사용자 편집 후 DOCX export, profile 불변 확인, 예시 삭제 후 다음 prompt 제외까지
한 흐름으로 검증한다. DOCX는 실제 builder로 생성하고 ZIP 무결성과 document XML의
편집 텍스트를 확인했다. 이 경로에서 새 결함은 발견되지 않아 제품 코드는 수정하지 않았다.

- 단일 lifecycle: **1 passed, 14 deselected, 1 warning in 1.52s**.
- `pytest -q tests/test_sketch_ui.py tests/test_manual_style_ui.py
  tests/test_style_system.py tests/test_generation_style_selection.py
  tests/test_onboarding_ui.py tests/test_export_edited.py --tb=short`:
  **112 passed, 1 warning in 26.42s**. Fresh HOME/data, dotenv no-op, mock/local,
  외부 요청 차단 Chromium. Root: `/tmp/decisiondoc-lifecycle-verified-sadzqw9t`.
- 예시 등록과 edited export에 추가 provider 호출이 없는 것을 검사했다.
  실제 provider 문체 재현, 모델 학습, DOCX 시각적 레이아웃, 인증된 운영 환경의
  전체 사용자 여정, full suite는 이 검증의 완료 주장에 포함하지 않는다.
- 사용자 데이터·서버·열린 화면을 변경하지 않았고 commit/push도 하지 않았다.

## 2026-09-14 DOCX Table Pagination

Bundled documents skill renderer로 실제 `build_docx()`의 30행 합성 표를 검수했다.
첫 한국어 렌더에서 반복 머리글 부재, 페이지 경계의 행 분리와 한글 표시 누락을
관찰했다. `_add_markdown_table()`에 `w:tblHeader`와 `w:cantSplit`을 추가했다.
영문 본문 fixture로 재렌더링한 6개 PNG 전부를 확인해 표 머리글 반복과 행 보존을
확인했다. 표지·공통 label의 한글 누락은 남아 있어 전체 시각 검수 PASS가 아니다.

- 변경: `app/services/docx_service.py`, `tests/test_docx_endpoint.py`, `docs/test_plan.md`.
- `pytest -q tests/test_docx_endpoint.py tests/test_export_edited.py
  tests/test_generation_style_selection.py --tb=short`: **48 passed, 1 warning in 5.58s**.
  Fresh HOME/data, dotenv no-op, mock/local 환경. 최초 실행은 Chromium 경로 누락으로
  PDF 3건이 실패했고 기존 `PLAYWRIGHT_BROWSERS_PATH`를 지정해 통과했다. 설치는 없다.
- Renderer: bundled Python/LibreOffice, 실제 DOCX builder의 기존 dependency를
  PYTHONPATH로 연결했다. QA script: `/tmp/decisiondoc-layout-qa-20260914.py`.
  수정 전 render: `/var/folders/n7/g1vxvrg97t11t_nxzvdk0dpr0000gn/T/decisiondoc-layout-qa-vd9pwfq4/render`.
  수정 후 render: `/var/folders/n7/g1vxvrg97t11t_nxzvdk0dpr0000gn/T/decisiondoc-layout-qa-jz7qmbrb/render`.
- 한글 renderer/font 원인 진단과 한국어 재렌더가 남아 있다. 실제 AI, full suite,
  운영 Word 환경, 한 페이지보다 큰 표 행은 검증하지 않았다.
  사용자 데이터·서버·열린 탭을 변경하지 않았고 외부 호출/commit/push도 없다.
  Backend 변경은 현재 장기 실행 서버의 다음 재시작부터 적용된다.

## 2026-09-14 Korean DOCX Renderer Verification

한글이 누락된 기존 DOCX를 그대로 재렌더링했다. `SAL_FONTPATH`만 설정한 시도는
누락이 유지됐고, system font directories와 Malgun Gothic/맑은 고딕의 Apple SD Gothic
Neo 대체를 명시한 `FONTCONFIG_FILE`에서는 한글이 표시됐다. 제품 DOCX 내용 변경 없이
해소돼 이번 이슈는 해당 bundled renderer의 font discovery/substitution 범위로 분류한다.

- `tests/fixtures/docx_fontconfig_macos.conf`와 `docs/test_plan.md`에 macOS QA 전용
  process-local 설정을 남겼다. 시스템 폰트·bundle 파일·전역 config는 변경하지 않았다.
- 최신 builder로 한국어 30행 fixture를 생성한 후 재렌더했다. PNG **7페이지 전부**를
  열어 한글 제목·본문·표, 반복 머리글, 행 보존을 확인했다. 최신 render:
  `/var/folders/n7/g1vxvrg97t11t_nxzvdk0dpr0000gn/T/decisiondoc-layout-qa-yt2odee4/render`.
- 이전 절의 한글 누락 blocker는 이 local QA 환경에서 해소됐다. 기본 렌더 설정이나
  다른 OS/Word에서 자동으로 해결됐다는 의미는 아니다. 원본 DOCX에 폰트를 embed하거나
  기본 폰트를 변경하지 않았고 full suite/실제 AI/학습은 실행하지 않았다.
- 사용자 서버·문서·열린 화면, provider/network, 설치, commit/push에 변경은 없다.

## 2026-09-14 Core Export Document Labels

렌더링에서 보인 `Adr`를 조사해 공통 `export_labels.py`에 기본 4종 매핑이 없는
것을 확인했다. ADR/Onepager/Eval Plan/Ops Checklist의 한국어 표시 이름만 추가했다.
문서 ID, API/schema, 파일 경로, Markdown 본문은 변경하지 않는다. 공통 helper를
사용하는 export 요약, DOCX, PDF, Excel, HWP 및 PPTX fallback에 적용된다.

- 변경: `app/services/export_labels.py`, `tests/test_export_outline.py`,
  `tests/test_docx_endpoint.py`, `docs/test_plan.md`.
- `pytest -q tests/test_export_outline.py tests/test_docx_endpoint.py
  tests/test_export_edited.py tests/test_excel_endpoint.py tests/test_hwp_endpoint.py
  tests/test_pdf_endpoint.py --tb=short`: **79 passed, 1 warning in 15.80s**.
  Fresh HOME/data, dotenv no-op, mock/local 및 기존 Chromium 경로 사용.
  Root: `/tmp/decisiondoc-export-labels-verified-jbeg8v1e`.
- 최초 테스트의 잘못된 summary.doc_type 가정으로 1건 실패했으며, 실제 label과
  입력 doc_type 보존 검사로 수정 후 전체 관련 gate를 다시 통과했다.
- 이번 label 변경 후 별도 DOCX 시각 재렌더, full suite, 실제 provider/학습은
  실행하지 않았다. 사용자 서버·데이터·탭을 보존했고 commit/push는 없다.
  장기 실행 서버에는 다음 재시작부터 적용된다.

## 2026-09-14 Four Document Pagination Review

최신 기본 4종 label을 한국어 합성 DOCX로 검수했다. 문서명은 잘리지 않았지만
9페이지 중 4/6/8페이지가 footer만 있는 빈 페이지였다. 표 뒤의 별도 page-break
문단 대신 각 일반 문서 시작 badge에 `page_break_before`를 적용해 해결했다.
공문서 전용 경로는 변경하지 않았다. 재렌더한 6페이지 전부를 확인했다.

- 변경: `app/services/docx_service.py`, `tests/test_docx_endpoint.py`, `docs/test_plan.md`.
- `pytest -q tests/test_docx_endpoint.py tests/test_export_edited.py
  tests/test_generation_style_selection.py --tb=short`: **49 passed, 1 warning in 16.30s**.
  Fresh HOME/data, dotenv no-op, mock/local, 기존 Chromium 사용.
- QA script: `/tmp/decisiondoc-four-doc-qa-20260914.py`.
  수정 전 render: `/var/folders/n7/g1vxvrg97t11t_nxzvdk0dpr0000gn/T/decisiondoc-four-doc-qa-vai1wjr_/render`.
  수정 후 render: `/var/folders/n7/g1vxvrg97t11t_nxzvdk0dpr0000gn/T/decisiondoc-four-doc-qa-q3vwzy5q/render`.
  Bundled renderer와 repo macOS Fontconfig로 동일 fixture를 검수했다.
- 표지 요약표 마지막 행이 2페이지에 따로 이어져 여백이 큰 점은 남아 있다.
  빈 페이지 결함 해소와 전체 편집 디자인 완성은 구분한다. 다른 OS/Word, full suite,
  실제 AI/학습은 검증하지 않았다. 서버 재시작·사용자 데이터 변경·commit/push는 없다.

## 2026-09-14 Cover Summary Spacing Follow-up

앞 절에서 남은 표지 요약표 마지막 행의 다음 페이지 이동을 수정했다. 표지의
빈 문단 두 개를 제거하고 제목은 다음 문단과 함께 유지한다. 문서 목록은
120% 줄간격과 4pt after-spacing, 요약표 셀은 0pt after-spacing을 사용한다.
요약표에는 반복 머리글과 행 분할 방지를 추가했다. 본문 글자 크기·줄간격과
문서 내용은 변경하지 않았다.

- 변경: `app/services/docx_service.py`, `tests/test_docx_endpoint.py`, `docs/test_plan.md`.
- `pytest -q tests/test_docx_endpoint.py tests/test_export_edited.py
  tests/test_generation_style_selection.py --tb=short`: **49 passed, 1 warning in 12.28s**.
  Fresh HOME/data, dotenv no-op, mock/local 및 기존 Chromium 사용.
  Test root: `/tmp/decisiondoc-cover-spacing-5lv_rz94`.
- 동일 `/tmp/decisiondoc-four-doc-qa-20260914.py` fixture를 bundled renderer와
  repo macOS Fontconfig로 재생성·렌더했다. **6페이지에서 5페이지**로 정리됐고
  PNG 5페이지 전부에서 한글·표·문서 경계가 보존되고 잘림이 없음을 확인했다.
  표지는 요약표의 마지막 행까지 1페이지에 들어간다.
  Render: `/var/folders/n7/g1vxvrg97t11t_nxzvdk0dpr0000gn/T/decisiondoc-four-doc-qa-3fr7xjog/render`.
- 긴 제목·문서 수 증가 시 단일 표지를 보장하지 않는다. 다른 OS/Word, full suite,
  실제 provider/학습은 검증하지 않았다. 사용자 서버 재시작·데이터 변경·설치·
  commit/push는 없다. 실행 중인 서버에는 이번 backend 변경을 반영하지 않았다.

## 2026-09-14 Combined Local Regression

최근 popup, manual style, sketch, generation style selection, edited DOCX와
export outline 변경을 하나의 pytest 실행에서 재검증했다. **128 passed,
1 warning in 52.54s**, exit 0. 기존 Starlette/httpx deprecation warning 외
실패는 없었으며 이 단계에서는 제품 코드를 추가 수정하지 않았다.

재현 명령 (repo root, 기존 Python/Chromium 설치 사용):

```bash
env -i \
  PATH=/Users/sungjin/.local/share/mise/installs/python/3.12.12/bin:/usr/bin:/bin \
  PYTHONPATH=/Users/sungjin/.local/lib/python3.12/site-packages \
  PLAYWRIGHT_BROWSERS_PATH=/Users/sungjin/Library/Caches/ms-playwright \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 -B -c '
import os, tempfile
from pathlib import Path
import dotenv
dotenv.load_dotenv = lambda *a, **kw: False
root = tempfile.mkdtemp(prefix="decisiondoc-combined-regression-")
os.environ["HOME"] = root
from scripts.run_free_local import build_free_environment
os.environ.update(build_free_environment(os.environ, provider="mock", data_dir=Path(root)/"data"))
os.environ["DECISIONDOC_FREE_MODE"] = "0"
print(root, flush=True)
import pytest
raise SystemExit(pytest.main([
    "-q", "tests/test_onboarding_ui.py", "tests/test_manual_style_ui.py",
    "tests/test_sketch_ui.py", "tests/test_style_system.py",
    "tests/test_generation_style_selection.py", "tests/test_docx_endpoint.py",
    "tests/test_export_edited.py", "tests/test_export_outline.py", "--tb=short",
]))
'
```

- Test root: `/tmp/decisiondoc-combined-regression-_gnmmgdy`.
- API regression에서 기능을 검사하도록 해당 test process의 free-mode flag만
  해제했다. Provider는 mock, storage는 local이며 dotenv/credential 상속을
  차단했다. 이는 무료 모드 전체 동작 또는 production 검증이 아니다.
- Browser 검사는 격리된 synthetic fixture이며 사용자 계정으로 이어지는 실제
  end-to-end UAT는 아니다. 이 실행에서는 DOCX를 새로 시각 렌더하지 않았다.
  직전 절의 5페이지 검수와 자동 XML/API 검증을 구분한다.
- 다음 사용자 검수는 최신 backend를 적용한 로컬 서버에서 예시 등록, 스타일
  선택, 문서 생성, 편집, DOCX 다운로드 순서로 진행한다. 서버 재시작 전에는
  기존 실행 프로세스와 데이터 경로를 다시 확인하고 사용자 데이터를 보존한다.
- 전체 suite, 실제 AI 문체 품질, model training, 다른 OS/Word는 미검증이다.
  사용자 서버/데이터 변경, 설치, 외부 provider, commit/push는 실행하지 않았다.

## 2026-09-14 Style Creation Modal And Browser Lifecycle

실제 격리 서버의 browser 동선에서 스타일 생성 후 창이 남아 예시 저장 클릭을
차단하는 결함을 재현했다. `document.querySelector('.modal-overlay')`가 먼저
등장하는 숨겨진 문서 업로드 modal을 제거하고 생성 modal은 남기는 것이 원인이다.
생성 handler에 해당 modal을 전달하고 입력 조회와 성공 시 제거를 그 객체로
한정했다. 다른 modal이나 API/auth/storage 동작은 변경하지 않았다.

- 변경: `app/static/index.html`, `tests/e2e/test_main_flow.py`, `docs/test_plan.md`.
  해당 파일들의 기존 dirty 변경은 보존했다.
- 새 `test_manual_style_generation_and_edited_docx_download`는 DOM 조작으로
  스타일 생성, 예시 저장, 선택, 생성, 편집, DOCX 다운로드까지 진행한다.
  생성 요청의 profile ID, 두 기존 업로드 modal 보존과 실제 다운로드 XML의
  편집 문장 보존을 검사한다. Fixture는 별도 포트와 임시 계정/data를 사용한다.
- 수정 전 **1 failed in 34.26s**: modal pointer interception.
  Root: `/tmp/decisiondoc-style-e2e-e6wsqhdx`.
  수정 후 동일 테스트 **1 passed in 5.60s**.
  Root: `/tmp/decisiondoc-style-e2e-es4phl1p`.
- 앞 절 Combined Local Regression과 동일 격리 실행 설정으로 pytest 인자에
  `-p pytest_playwright.pytest_playwright`와 다음 세 node를 추가했다:
  `tests/e2e/test_main_flow.py::test_manual_style_generation_and_edited_docx_download`,
  `tests/e2e/test_main_flow.py::test_generate_from_documents_modal_flow`,
  `tests/e2e/test_main_flow.py::test_export_flow`.
  **131 passed, 1 warning in 36.49s**, exit 0. 기존 Starlette/httpx 경고만 남았다.
  Root: `/tmp/decisiondoc-style-e2e-gate-3tb63du2`. `git diff --check` PASS.
- Playwright는 실제 browser/server 연결 검증에, UI skill은 static 변경 경계에
  사용했다. 기존 pytest E2E fixture를 재사용했으며 설치는 하지 않았다.
- `127.0.0.1:8787`의 기존 PID 36358 서버는 재시작하거나 조작하지 않았다.
  실제 AI 품질/model training, 전체 suite, 사용자 계정 UAT, 시각 재렌더는
  이번 검증 범위가 아니다. Provider 호출, 배포, commit/push는 실행하지 않았다.

## 2026-09-14 Style Creation Single Flight

스타일 생성 handler를 응답 대기 중 두 번 호출하면 POST가 두 번 발생했다.
해당 modal의 submit disabled 상태로 재진입을 차단하고 요청 중 input/button을
잠근다. 성공 시 해당 창만 닫으며 HTTP/네트워크 오류 시 입력을 유지한다.
finally에서 controls와 aria-busy를 복구한다. 자동 재전송은 추가하지 않았다.

- 변경: `app/static/index.html`, `tests/test_manual_style_ui.py`, `docs/test_plan.md`.
- 지연 응답 fixture의 success/http_error/network_error 세 경우가 수정 전
  `createRequests.length == 2`로 실패했다: **3 failed, 17 deselected in 2.27s**.
- 앞 절과 동일한 mock/local, fresh HOME/data, dotenv 차단 및 기존 Chromium
  환경에서 `pytest -p pytest_playwright.pytest_playwright -q
  tests/test_manual_style_ui.py tests/test_style_system.py
  tests/e2e/test_main_flow.py::test_manual_style_generation_and_edited_docx_download
  --tb=short`: **68 passed, 1 warning in 22.98s**, exit 0.
  Root: `/tmp/decisiondoc-create-guard-e_j7awop`.
  기존 Starlette/httpx deprecation warning만 남았다. `git diff --check` PASS.
- 보장은 동일 창의 진행 중 요청에 한정된다. 다른 탭 또는 응답 유실 후 사용자
  재시도의 서버 측 exactly-once는 보장하지 않는다. 실제 AI/학습, 전체 suite,
  사용자 계정 UAT는 실행하지 않았다. 기존 서버/데이터, 설치, commit/push는
  변경하지 않았다.

## 2026-09-14 Free Mode And Free Account E2E

기존 E2E fixture가 무조건 enterprise 계정을 생성하므로 무료 사용 동선의
검증 근거가 부족했다. `tests/e2e/conftest.py`는 free mode에서 기본 free
계정을 유지하고 plan ID를 assert하도록 수정했다. 일반 모드는 기존 enterprise
fixture를 유지한다. 제품 billing/권한/provider 코드는 변경하지 않았다.

- 최초 free-mode flag만 켠 lifecycle은 **1 passed in 6.76s**였으나 enterprise
  fixture를 사용했으므로 free 계정 검증으로 채택하지 않았다.
- 앞 절의 격리 실행 방식에서 `DECISIONDOC_FREE_MODE=0` override를 제거해
  `build_free_environment(..., provider="mock", ...)`의 free mode를 유지했다.
  Pytest 인자: `-p pytest_playwright.pytest_playwright -q
  tests/e2e/test_main_flow.py::test_manual_style_generation_and_edited_docx_download
  tests/e2e/test_main_flow.py::test_generate_from_documents_modal_flow
  tests/e2e/test_main_flow.py::test_export_flow tests/test_free_mode.py --tb=short`.
  **28 passed, 1 warning in 10.68s**, exit 0.
  Root: `/tmp/decisiondoc-free-account-verified-74mr1ufh`.
- 일반 모드 호환성은 같은 격리 환경에서 free-mode flag만 0으로 설정하고
  위 E2E 세 node만 실행했다: **3 passed in 10.86s**, exit 0.
  Root: `/tmp/decisiondoc-standard-e2e-check-8m3a1jt2`.
- `git diff --check` PASS. 실제 provider/로컬 LLM·학습·사용자 계정 UAT·전체 suite는
  실행하지 않았다. 기존 서버/사용자 데이터, 설치, commit/push는 변경하지 않았다.

## 2026-09-14 Mobile Style Modal Lifecycle

390px E2E에서 mobile-bottom-nav(z-index 4000)가 생성 modal(z-index 2000)의
만들기 버튼을 가려 클릭이 timeout되는 문제를 재현했다. 스타일 생성 창에만
`style-create-modal` class를 추가하고 z-index 5000, 불투명 panel 배경,
viewport 기반 높이 제한과 내부 스크롤을 적용했다. 공통 modal/nav는 변경하지 않았다.

- 변경: `app/static/index.html`, `tests/e2e/test_main_flow.py`, `docs/test_plan.md`.
- 수정 전 desktop/mobile: **1 passed, 1 failed in 42.51s**.
  Root: `/tmp/decisiondoc-mobile-style-e2e-qt1mu9ua`.
- 최종 free-mode/free-account E2E는 1280x900, 390x844, 390x420에서
  스타일 생성부터 edited DOCX 다운로드까지 진행하고 modal 경계와 가로 넘침을
  검사한다. **3 passed in 17.71s**, exit 0.
  Root: `/tmp/decisiondoc-mobile-e2e-verified-fd6yme8z`.
- 동일 격리 설정에서 plugin 없이 `pytest -q tests/test_manual_style_ui.py
  tests/test_onboarding_ui.py tests/test_free_mode.py --tb=short`:
  **49 passed, 1 warning in 21.46s**, exit 0.
  Root: `/tmp/decisiondoc-mobile-ui-verified-0nrttd3a`.
- 최초 combined gate는 E2E 뒤의 자체 sync_playwright fixture가 plugin session의
  asyncio loop와 충돌했다: **1 failed, 31 passed, 20 errors in 21.13s**.
  통과 증빙으로 사용하지 않고 두 process로 분리해 위 결과를 확보했다.
  Shared fixture lifetime 재설계는 하지 않았다.
- 생성 창의 desktop/mobile/short-mobile 스크린샷을 확인했다. 중간 render 증빙:
  `/tmp/decisiondoc-mobile-style-fixed-abrozv65/pytest`와
  `/tmp/decisiondoc-mobile-style-gate-5vuvyz52/pytest`.
  결과 스크린샷에는 일시적인 알림이 겹쳐 있으며 전체 UI 디자인 완성으로
  해석하지 않는다. 실제 기기/Safari/가상 키보드와 실제 AI 품질은 미검증이다.
- `git diff --check` PASS. 기존 서버/데이터, provider 호출, 설치, commit/push는
  변경하거나 실행하지 않았다.

## 2026-09-14 Bounded Notification Stack

성공 알림이 누적되어 화면을 가리고 긴 알림이 좁은 viewport 밖으로 나가는
문제를 synthetic browser fixture로 재현했다. 같은 내용·종류의 현재 알림만
중복 생성을 차단한다. 서로 다른 메시지와 error는 삭제하지 않고 제한된 영역에서
스크롤로 확인한다. 기존 5초 timeout은 유지하며 중복 호출로 연장하지 않는다.
다운로드 후 action 알림은 문장과 버튼을 두 줄로 배치한다.

- 변경: `app/static/index.html`, `tests/test_notification_ui.py`, `docs/test_plan.md`.
- 수정 전 **4 failed, 1 passed in 7.87s**: 중복 알림, 높이 초과와 좁은 화면
  가로 넘침. 중간 검증에서 등장 animation 완료 전 scrollWidth를 읽는 문제가
  있어 animation.finished를 기다리도록 수정하고 가로 스크롤을 차단했다.
- 격리 HOME/dotenv 차단/기존 Chromium으로
  `pytest -q tests/test_notification_ui.py tests/test_manual_style_ui.py
  tests/test_onboarding_ui.py --tb=short`: **30 passed in 27.25s**.
- 이후 action 문장 줄바꿈 보완 후 `pytest -q tests/test_notification_ui.py
  --tb=short`: **6 passed in 4.43s**. Root:
  `/tmp/decisiondoc-notification-layout-final-y8e394sl`.
  해당 root의 `pytest/test_post_download_actions_rem0/notification-actions.png`를
  열어 390x420 화면에서 오류, 완료 문장과 버튼 배치를 확인했다.
- 별도 process에서 기존 free-mode/free-account 실행 설정으로
  `pytest -p pytest_playwright.pytest_playwright -q
  tests/e2e/test_main_flow.py::test_manual_style_generation_and_edited_docx_download
  --tb=short`: **3 passed in 16.18s** (desktop/mobile/short-mobile).
  Root: `/tmp/decisiondoc-notification-e2e-ldiu5q2d`. `git diff --check` PASS.
- 실제 기기/Safari, 전체 suite, 실제 AI/학습은 미검증이다. 임시 toast 변경이며
  저장된 알림/audit 기록, 권한, provider, 서버/사용자 데이터는 변경하지 않았다.
  설치, commit/push는 실행하지 않았다.

## 2026-09-14 Style Reload Continuity

기존 style lifecycle E2E에 예시 저장 직후 browser reload를 추가했다. 스타일
목록에서 같은 profile ID를 열고 실제 GET 응답의 ID, 예시 개수·label·문장을
확인한 뒤 기존 생성·편집·DOCX 다운로드를 이어간다. 제품 코드 변경은 없다.

- 변경: `tests/e2e/test_main_flow.py`, `docs/test_plan.md`.
- 기존 격리 free-mode/free-account, mock/local, dotenv 차단 환경에서
  `pytest -p pytest_playwright.pytest_playwright -q
  tests/e2e/test_main_flow.py::test_manual_style_generation_and_edited_docx_download
  --tb=short`: **3 passed in 11.46s**, exit 0.
  Desktop/mobile/short-mobile 모두 통과했다.
  Root: `/tmp/decisiondoc-style-reload-e2e-q2xzz64v`.
- `git diff --check` PASS. Browser reload 검증이며 server process 재시작,
  여러 기기 동기화, 실제 provider 문체 재현이나 model training 검증은 아니다.
  사용자 서버/데이터, 설치, commit/push는 변경하지 않았다.

## 2026-09-14 Sketch Failure Recovery

기존 style lifecycle E2E의 생성 직전에 `/generate/sketch` HTTP 422를 주입했다.
오류 표시, 버튼 복구, 제목·목표·선택 profile ID 보존, 결과/구성안 미표시,
실패 요청 1회를 확인한다. 주입 해제 후 새 클릭으로 실제 mock/local 생성과
edited DOCX 다운로드를 완료했다. 제품 코드는 변경하지 않았다.

- 변경: `tests/e2e/test_main_flow.py`, `docs/test_plan.md`.
- 기존 free-mode/free-account 격리 설정으로
  `pytest -p pytest_playwright.pytest_playwright -q
  tests/e2e/test_main_flow.py::test_manual_style_generation_and_edited_docx_download
  --tb=short`: **3 passed in 12.33s**, exit 0.
  Root: `/tmp/decisiondoc-generation-recovery-e2e-eq6g8ofo`.
- Desktop/mobile/short-mobile에서 같은 실패 복구 동선을 검증했다.
  Synthetic 422는 browser route에서 반환하며 실제 provider 호출은 없다.
  스트리밍 중단, timeout, retry 대상 5xx, 응답 유실 후 server commit은
  검증하지 않았다. `git diff --check` PASS.
- 사용자 서버/데이터, 설치, commit/push는 변경하지 않았다.

## 2026-09-14 Incomplete SSE Recovery

본문 생성 SSE가 complete 없이 EOF로 끝나면 기존 loop가 정상 종료되어
생성 중 status와 progress가 남았다. Loop 종료 후 resolved를 검사해 기존
catch/finally로 보내도록 수정했다. 이 경로에서 timeout 정리, 오류 표시,
progress 숨김과 버튼 복구가 수행된다. 성공 이벤트 처리와 API는 변경하지 않았다.

- 변경: `app/static/index.html`, `tests/e2e/test_main_flow.py`, `docs/test_plan.md`.
- 빈 stream/progress-only 두 fixture에서 수정 전 **2 failed in 15.86s**.
  Root: `/tmp/decisiondoc-stream-red-5r9htu14`.
- 기존 격리 free-mode/free-account, mock/local 환경에서
  `pytest -p pytest_playwright.pytest_playwright -q
  tests/e2e/test_main_flow.py::test_incomplete_generation_stream_recovers_without_success
  tests/e2e/test_main_flow.py::test_manual_style_generation_and_edited_docx_download
  --tb=short`: **5 passed in 15.05s**, exit 0.
  Root: `/tmp/decisiondoc-stream-verified-yv4weihc`.
- 실패 후 입력 보존과 정상 mock 재생성, 기존 3-viewpoint DOCX 다운로드 동선
  유지까지 확인했다. 실제 timeout, 사용자 취소, malformed complete payload,
  provider-side 취소는 별도 검증 범위다. `git diff --check` PASS.
- 기존 서버/사용자 데이터, 실제 provider/학습, 설치, commit/push는 변경하거나
  실행하지 않았다.

## 2026-09-14 Goal Execution

사용자의 Goal 실행 요청에 따라 현재 task의 Goal 도구로 아래 Next Goal Text의
기술 검증과 UAT 준비 범위를 실행했다. Orca나 외부 coordinator를 재가동하지
않았고 모델을 전환했다고 기록하지 않는다. 제품 코드는 이번 Goal에서 수정하지
않았다. 인간 관찰과 실제 provider 품질은 자동 검증 완료와 구분한다.

모든 테스트는 `env -i`, 기존 Python 3.12/Chromium, dotenv no-op, fresh HOME/data,
mock provider/local storage에서 수행했다. 기준 환경 구성은 앞 절의 재현 명령을
사용했다. Browser와 자체 Playwright fixture는 별도 process로 유지했다.

1. `pytest -q tests/test_free_mode.py tests/test_verify_generated_document_reviewed_package.py
   tests/test_generation_export_packet.py tests/storage/test_generated_document_review_store.py
   tests/test_generated_document_reviews.py tests/test_future_feature_gate.py --tb=short`:
   **163 passed, 1 warning in 21.71s**, exit 0.
   Root: `/tmp/decisiondoc-goal-review-gate-ladz8akt`.
   일반 API gate는 FREE_MODE=0이며 free-mode tests는 자체 fixture로 제한을 켠다.
2. `pytest -p pytest_playwright.pytest_playwright -q tests/e2e/test_main_flow.py
   -k 'generated_document_review or manual_style_generation or incomplete_generation_stream'
   --tb=short`: **13 passed, 103 deselected in 21.26s**, exit 0.
   Root: `/tmp/decisiondoc-goal-browser-gate-g2vj90st`. FREE_MODE=1/free account.
   Review browser tests의 응답은 synthetic contract fixtures이며 실제 human review
   또는 전체 review UI-to-persistence lifecycle 증거는 아니다.
3. `pytest -q tests/test_generated_document_review_ui_static.py tests/test_infrastructure.py
   -k generated_document_review --tb=short`:
   **9 passed, 178 deselected, 1 warning in 0.24s**, exit 0.
   Root: `/tmp/decisiondoc-goal-static-gate-s891toba`. FREE_MODE=0.

Warnings는 기존 Starlette/httpx deprecation이다. 전체 suite는 실행하지 않았고
과거 통과 수를 이번 결과에 합산하지 않았다. `git diff --check` PASS.

### Prepared Human UAT Runtime

- URL: `http://127.0.0.1:8788/`. 사용 전 비어 있는 loopback port임을 확인했다.
- HOME: `/tmp/decisiondoc-goal-human-uat-x6d7dlr6`.
- DATA_DIR/EXPORT_DIR: `/tmp/decisiondoc-goal-human-uat-x6d7dlr6/data`.
- PID 9191, terminal session 26057. 기존 사용자 서버/데이터는 조작하지 않았다.
- `build_free_environment(..., provider="mock", data_dir=...)`를 새 HOME과
  dotenv 차단 process에 적용한 뒤 `uvicorn.run("app.main:app", host="127.0.0.1",
  port=8788, ws="none")`로 기동했다. Credentials를 상속하지 않았다.
- `curl --fail --silent http://127.0.0.1:8788/health`: status ok, free_mode true,
  provider/routes mock, storage ok. `/`는 HTTP 200.
- quality_first degraded는 mock runtime의 명시된 품질 한계다. 실제 provider
  호출로 전환하지 않았다. 이 임시 runtime의 계정/문서는 생성하지 않았다.

### Completion Boundary

이번 Goal의 기술 검증과 UAT 준비는 완료했다. 작성자·담당 검토자가 수행할
7단계 human UAT는 `docs/test_plan.md`의 기존 표대로 남긴다. 사용자 계정 생성,
synthetic 문서 검토, 실제 Office 앱의 내용/레이아웃 확인과 경계 이해 기록은
사람이 수행해야 한다. 그 결과 없이 인간 검토/전체 제품/production 완료로
표시하지 않는다. 외부 호출, 학습, 설치, 배포, commit/push는 실행하지 않았다.

## Next Goal Text

설계 방향 승인 후 사용할 첫 실행 Goal의 본문:

> DecisionDoc의 기존 generated-document review 흐름을 격리된 mock/local 환경에서
> 검증하고 실제 검토자 UAT가 가능한 상태로 준비한다. 기존 무료 모드, review
> API/storage, completed-package CLI와 browser 동선을 확인하고 실패를 분류한다.
> 기술 검증과 사람이 해야 할 내용/레이아웃/이해도 검수를 분리한다. 새 UAT 도구,
> donor 통합, 기존 데이터 변경, 외부 호출, 설치, 배포와 commit/push는 제외한다.
> 새로운 기능이나 구조 변경이 필요하면 exact scope와 설계를 먼저 제시한다.

다음 구현 Goal은 이 준비 과정 또는 실제 UAT에서 재현된 문제를 기준으로 별도
정의한다. 전체 제품을 무조건 완벽하다고 선언하는 열린 Goal로 대체하지 않는다.
