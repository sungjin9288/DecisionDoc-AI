# `decisiondoc.kr` DNS 설정 가이드

이 문서는 `decisiondoc.kr` 도메인을 기준으로 사무실, 회사 A, 회사 B를 분리 운영하기 위한 DNS 설정 가이드입니다.

## 운영 구조

- 사무실: `office.decisiondoc.kr`
- 회사 A: `company-a.decisiondoc.kr`
- 회사 B: `company-b.decisiondoc.kr`

각 서브도메인은 서로 다른 장소의 서버 IP를 가리켜야 합니다.

## DNS 레코드

아래 A 레코드를 등록합니다.

| Type | Host | Value | 용도 |
|------|------|-------|------|
| A | `office` | `<office-public-ip>` | 사무실 접속 주소 |
| A | `company-a` | `<company-a-public-ip>` | 회사 A 접속 주소 |
| A | `company-b` | `<company-b-public-ip>` | 회사 B 접속 주소 |

IPv6를 사용하면 AAAA 레코드도 같은 방식으로 추가합니다.

## 확인 방법

DNS 등록 후 아래처럼 확인합니다.

```bash
dig +short office.decisiondoc.kr
dig +short company-a.decisiondoc.kr
dig +short company-b.decisiondoc.kr
```

각 결과가 해당 장소의 서버 공인 IP와 일치해야 합니다.

## 배포 연결

DNS가 반영되면 각 장소의 `.env.prod`에 아래처럼 반영합니다.

- 사무실: `ALLOWED_ORIGINS=https://office.decisiondoc.kr`
- 회사 A: `ALLOWED_ORIGINS=https://company-a.decisiondoc.kr`
- 회사 B: `ALLOWED_ORIGINS=https://company-b.decisiondoc.kr`

## SSL

각 장소 서버에서 해당 서브도메인 기준으로 인증서를 발급합니다.

예:

- 사무실 서버: `office.decisiondoc.kr`
- 회사 A 서버: `company-a.decisiondoc.kr`
- 회사 B 서버: `company-b.decisiondoc.kr`

DNS 반영이 끝난 뒤 SSL 설정을 진행해야 합니다.

## 아직 필요한 정보

다음 값이 있어야 실제 설정을 끝낼 수 있습니다.

1. 사무실 서버 공인 IP
2. 회사 A 서버 공인 IP
3. 회사 B 서버 공인 IP

이 세 값이 정해지면 DNS 설정과 배포값을 확정할 수 있습니다.
