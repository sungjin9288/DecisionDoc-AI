# Evidence Checklist

## 1. 검증 완료

| 체크 항목 | 상태 | 증거 |
|---|---|---|
| 프로젝트 루트 확인 | 완료 | `<repo_root>` |
| 테스트 실행 | 완료 | `evidence/cli-logs/pytest_generate_auth_storage.log` |
| 로컬 서버 실행 | 완료 | `http://127.0.0.1:8787` |
| Health API 응답 저장 | 완료 | `evidence/api-responses/health.json` |
| Version API 응답 저장 | 완료 | `evidence/api-responses/version.json` |
| Bundle catalog 응답 저장 | 완료 | `evidence/api-responses/bundles.json` |
| Generate API 응답 저장 | 완료 | `evidence/api-responses/generate-tech-decision.json` |
| Export API 응답 저장 | 완료 | `evidence/api-responses/generate-export-tech-decision.json` |
| Export 산출물 저장 | 완료 | `evidence/output-artifacts/export_adr.md`, `evidence/output-artifacts/export_onepager.md` |
| UI screenshot 저장 | 완료 | `evidence/screenshots/web-ui-home.png` |
| Architecture diagram 생성 | 완료 | `evidence/architecture/system-architecture.md` |
| Sequence diagram 생성 | 완료 | `evidence/architecture/generation-sequence.md` |
| 입력 샘플 저장 | 완료 | `evidence/input-samples/` |
| 생성 결과 샘플 저장 | 완료 | `evidence/generated-samples/` |
| Swagger/OpenAPI 저장 | 완료 | `evidence/swagger/openapi.json`, `evidence/swagger/swagger-ui.html`, `evidence/swagger/openapi-summary.md` |
| 문서 생성 API 실행 로그 저장 | 완료 | `evidence/execution-logs/document_generation_api_capture.log` |

## 2. 검증 실패

| 체크 항목 | 상태 | 사유 |
|---|---|---|
| 실패로 확정된 구현 기능 | 없음 | 이번 수집 범위의 테스트/API/UI screenshot은 성공 |

## 3. 검증 필요

| 체크 항목 | 상태 | 필요한 후속 작업 |
|---|---|---|
| Live provider 호출 | 검증 필요 | 실제 API key가 있는 별도 안전 환경에서 live smoke 실행 |
| Production deployment | 검증 필요 | 배포 URL, post-deploy smoke log, 운영 접근성 확인 |
| 로그인 이후 전체 UI flow | 검증 필요 | 테스트 계정으로 생성 화면, 결과 화면, export 버튼 screenshot 추가 |
| Swagger UI 브라우저 렌더링 | 검증 필요 | 로컬 HTML은 저장했으나 CDN 리소스 오류로 screenshot은 빈 화면이어서 `/openapi.json`으로 대체 |
| 사용자 성과 수치 | 현재 없음 | 실제 사용자 피드백 또는 측정 지표 확보 전까지 사용 금지 |

## 4. 민감정보 제외 점검

- `.env`, `.env.*`: evidence package에 포함하지 않음
- API key/token/password 파일: 포함하지 않음
- 고객/기관 내부자료: 포함하지 않음
- 소스코드 전체 폴더: portfolio zip에는 포함하지 않음
- generated runtime data: zip에는 포함하지 않음
