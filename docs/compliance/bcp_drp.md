# 업무연속성 및 재해복구 계획서 (BCP/DRP)
## DecisionDoc AI v1.0

---

## 1. 개요

| 항목 | 내용 |
|------|------|
| RTO (복구 목표 시간) | 4시간 이내 |
| RPO (복구 목표 시점) | 24시간 이내 (최대 데이터 손실) |
| 백업 주기 | 매일 새벽 2시 자동 백업 |
| 백업 보존 기간 | 30일 |

---

## 2. 위협 시나리오별 대응

### 시나리오 A: 애플리케이션 장애

**탐지**: `/health` 헬스체크 실패, Slack 알림

**대응 절차**:
1. 장애 확인 (5분): `docker compose ps`
2. 로그 확인 (10분): `docker compose logs app --tail=200`
3. 재시작 시도 (15분): `docker compose restart app`
4. 이전 정상 이미지 태그로 재배포 (30분): `./scripts/deploy.sh production <previous_tag>`
5. 에스컬레이션 (1시간): 담당 개발자 호출

### 시나리오 B: 데이터 손상/삭제

**탐지**: 애플리케이션 오류, 사용자 신고

**대응 절차**:
1. 서비스 일시 중단 (유지보수 모드)
2. 손상 범위 파악: `tar tzf /backup/decisiondoc/data-YYYYMMDD-HHMMSS.tar.gz | head`
3. 최신 정상 백업 확인: `ls -lt /backup/decisiondoc/`
4. 데이터 복구: `./scripts/restore.sh /backup/decisiondoc/data-YYYYMMDD.tar.gz`
5. 무결성 검증 후 서비스 재개

### 시나리오 C: 서버 전체 장애

**탐지**: 서버 접속 불가

**대응 절차**:
1. 대기 서버 활성화 (1시간)
2. DNS 절체 (TTL 60초 사전 설정)
3. 백업 데이터 복구
4. 서비스 재개 확인
5. 원인 분석 및 보고

### 시나리오 D: 사이버 침해 사고

**탐지**: 감사 로그 이상, 보안 솔루션 알림

**대응 절차**:
1. 즉시 네트워크 격리
2. 침해 범위 파악
3. 한국인터넷진흥원(KISA) 신고: 118
4. 증거 보전 (로그 백업)
5. 복구 및 재발 방지 대책 수립

---

## 3. 백업 및 복구 절차

### 자동 백업
```bash
# cron 등록 (매일 새벽 2시)
0 2 * * * /opt/decisiondoc/scripts/backup.sh >> /var/log/decisiondoc-backup.log 2>&1
```

### 수동 백업
```bash
./scripts/backup.sh
BACKUP_KEEP_DAYS=14 ./scripts/backup.sh
```

### 복구
```bash
# 백업 목록 확인
ls -lt /backup/decisiondoc/

# 특정 시점으로 복구
./scripts/restore.sh /backup/decisiondoc/data-20250317-020000.tar.gz
```

---

## 4. 재해복구 훈련

| 훈련 항목 | 주기 | 담당 |
|-----------|------|------|
| 백업 복구 테스트 | 분기 1회 | 시스템 관리자 |
| 장애 복구 시뮬레이션 | 반기 1회 | 개발팀 |
| BCP 전체 훈련 | 연 1회 | 전 팀원 |

### 훈련 실행
```bash
python scripts/dr_test.py --scenario backup_restore
python scripts/dr_test.py --scenario app_restart
python scripts/dr_test.py --scenario full_recovery
```

---

## 5. 비상 연락망

| 역할 | 담당자 | 연락처 |
|------|--------|--------|
| 시스템 관리자 | [담당자명] | 010-XXXX-XXXX |
| 개발 책임자 | [담당자명] | 010-XXXX-XXXX |
| 보안 담당자 | [담당자명] | 010-XXXX-XXXX |
| KISA 침해사고 신고 | | 118 |

---

## 6. 문서 관리

| 항목 | 내용 |
|------|------|
| 작성일 | 2025년 3월 |
| 검토 주기 | 연 1회 |
| 승인자 | [승인자명] |
| 버전 | v1.0 |
