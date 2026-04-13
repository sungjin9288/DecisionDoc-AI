# MarkItDown 기반 지식 문서 인제션

DecisionDoc AI의 입력 품질을 높이기 위해, 외부 문서(PDF, DOCX, PPTX, XLSX 등)를
Markdown으로 변환해 요구사항/근거 자료로 재사용하는 흐름이다.

MarkItDown은 다양한 파일 포맷을 Markdown으로 변환하는 Python 유틸리티이며,
LLM 입력에 적합한 구조(헤더, 리스트, 테이블 등)를 보존하는 데 초점을 둔다.  
PDF, PowerPoint, Word, Excel, 이미지, 오디오, HTML, CSV/JSON/XML, ZIP, YouTube 등
여러 포맷을 지원한다.

또한 MarkItDown은 LLM 앱 연동을 위한 MCP 서버도 제공한다.  
이번 저장소에서는 로컬 CLI 스크립트로 변환을 수행하고, MCP 서버 연결은 선택 사항으로 둔다.

---

## 1) 설치

선택 의존성을 설치한다. 운영 배포에는 포함하지 않고, 인제션 작업용 로컬 환경에서만 사용한다.

```bash
pip install -r requirements-integrations.txt
```

혹은 MarkItDown 전체 옵션만 단독 설치한다:

```bash
pip install 'markitdown[all]'
```

---

## 2) 변환 스크립트 사용

```bash
python3 scripts/markitdown_ingest.py ./samples/요구사항정의서.docx
```

기본 출력 경로: `data/ingest/<원본파일명>.md`  
다른 디렉터리로 저장하려면:

```bash
python3 scripts/markitdown_ingest.py ./samples/요구사항정의서.docx \
  --output-dir ./data/ingest
```

플러그인을 활성화하려면:

```bash
python3 scripts/markitdown_ingest.py ./samples/요구사항정의서.pdf \
  --enable-plugins
```

---

## 3) DecisionDoc에 반영하는 방법

1. 변환된 `.md`를 열어 핵심 요구사항/근거 섹션을 추린다.  
2. DecisionDoc 요청 payload의 `requirements`에 붙여 넣는다.  
3. 원문 문서를 보관해야 하면 `data/ingest/`에 원본과 변환본을 같이 저장한다.

이 흐름은 문서 인제션을 “하네스” 형태로 반복 가능하게 만드는 가장 가벼운 방법이다.
