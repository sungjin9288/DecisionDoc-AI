# `decisiondoc.kr` DNS 설정 가이드

이 문서는 `decisiondoc.kr` 도메인을 기준으로 `admin` 환경과 `dawool` 환경을 분리 운영하기 위한 DNS 설정 가이드입니다.

## 운영 구조

- 운영자 공용 환경: `admin.decisiondoc.kr`
- Dawool 전용 환경: `dawool.decisiondoc.kr`

각 서브도메인은 서로 다른 환경의 서버 IP를 가리켜야 합니다.

## DNS 레코드

아래 A 레코드를 등록합니다.

| Type | Host | Value | 용도 |
|------|------|-------|------|
| A | `admin` | `<admin-public-ip>` | 운영자 공용 환경 |
| A | `dawool` | `<dawool-public-ip>` | Dawool 전용 환경 |

IPv6를 사용하면 AAAA 레코드도 같은 방식으로 추가합니다.

## 확인 방법

DNS 등록 후 아래처럼 확인합니다.

```bash
dig +short admin.decisiondoc.kr
dig +short dawool.decisiondoc.kr
```

각 결과가 해당 환경의 서버 공인 IP와 일치해야 합니다.

## 배포 연결

DNS가 반영되면 각 환경의 `.env.prod`에 아래처럼 반영합니다.

- `admin`: `ALLOWED_ORIGINS=https://admin.decisiondoc.kr`
- `dawool`: `ALLOWED_ORIGINS=https://dawool.decisiondoc.kr`

## SSL

각 환경 서버에서 해당 서브도메인 기준으로 인증서를 발급합니다.

예:

- 운영자 서버: `admin.decisiondoc.kr`
- Dawool 서버: `dawool.decisiondoc.kr`

DNS 반영이 끝난 뒤 SSL 설정을 진행해야 합니다.

## 아직 필요한 정보

다음 값이 있어야 실제 설정을 끝낼 수 있습니다.

1. `admin` 서버 공인 IP
2. `dawool` 서버 공인 IP

이 두 값이 정해지면 DNS 설정과 배포값을 확정할 수 있습니다.
