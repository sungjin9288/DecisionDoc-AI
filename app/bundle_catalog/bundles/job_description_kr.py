"""job_description_kr bundle — 채용공고 (한국어).

4개 문서:
  1. job_overview       — 포지션 개요
  2. requirements       — 자격 요건
  3. benefits_culture   — 복리후생 & 조직문화
  4. hiring_process     — 채용 프로세스
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

JOB_DESCRIPTION_KR = BundleSpec(
    id="job_description_kr",
    name_ko="채용공고",
    name_en="Job Description",
    description_ko="스타트업·중견기업 채용공고를 위한 포지션개요·자격요건·복리후생·채용프로세스 4종 문서",
    icon="💼",
    prompt_language="ko",
    prompt_hint=(
        "당신은 10년 경력의 HR 전문가로, 우수 인재가 지원하고 싶게 만드는 채용공고 작성에 능숙합니다.\n"
        "작성 전, 내부적으로 다음을 검토하세요: (1) 이 포지션의 핵심 가치는 무엇인가, "
        "(2) 지원자가 가장 궁금해할 정보는 무엇인가, (3) 우리 회사만의 차별화 매력 포인트는 무엇인가.\n"
        "- 직무 설명은 구체적인 일상 업무와 기대 성과를 명시하세요.\n"
        "- 자격 요건은 필수와 우대를 명확히 구분하고, 과도한 요건으로 지원 장벽을 높이지 마세요.\n"
        "- 복리후생은 경쟁사 대비 차별화된 요소를 강조하세요.\n"
        "- 채용 프로세스는 각 단계의 목적과 소요 기간을 명시하세요.\n"
        "- 모든 내용을 한국어로 작성하세요."
    ),
    category="internal",
    few_shot_example=(
        "## 직무 개요\n"
        "카카오페이 결제 플랫폼팀에서 월 거래액 3조 원 규모의 결제 코어 시스템을 설계·운영합니다.\n"
        "MSA 전환 프로젝트(2026년 완료 목표)의 기술 리더로서 8명 규모 팀을 이끕니다.\n"
        "\n"
        "## 자격 요건\n"
        "**필수**\n"
        "- Java/Kotlin 실무 경력 5년 이상 (Spring Boot 기반 대용량 시스템 설계 경험)\n"
        "- 분산 시스템 설계 및 장애 대응 경험 (TPS 10,000 이상)\n"
        "- 기술 문서 작성 및 팀 내 지식 공유 활성화 경험\n"
        "\n"
        "**우대**\n"
        "- 결제·핀테크 도메인 경험 (PCI-DSS 이해)\n"
        "- Kotlin Coroutine 실무 적용 경험\n"
    ),
    docs=[
        DocumentSpec(
            key="job_overview",
            template_file="job_description_kr/job_overview.md.j2",
            json_schema={
                "type": "object",
                "required": ["position_summary", "team_context", "key_responsibilities",
                             "daily_work", "growth_opportunity"],
                "properties": {
                    "position_summary":   {"type": "string"},
                    "team_context":       {"type": "string"},
                    "key_responsibilities": {"type": "array", "items": {"type": "string"}},
                    "daily_work":         {"type": "array", "items": {"type": "string"}},
                    "growth_opportunity": {"type": "string"},
                },
            },
            stabilizer_defaults={
                "position_summary":    "",
                "team_context":        "",
                "key_responsibilities": [],
                "daily_work":          [],
                "growth_opportunity":  "",
            },
            lint_headings=["# 포지션 개요:", "## 포지션 소개", "## 팀 소개", "## 주요 업무"],
            validator_headings=["## 포지션 소개", "## 팀 소개", "## 주요 업무",
                                "## 일상 업무", "## 성장 기회"],
            critical_non_empty_headings=["## 포지션 소개", "## 주요 업무"],
        ),
        DocumentSpec(
            key="requirements",
            template_file="job_description_kr/requirements.md.j2",
            json_schema={
                "type": "object",
                "required": ["required_qualifications", "preferred_qualifications",
                             "required_skills", "preferred_skills", "work_conditions"],
                "properties": {
                    "required_qualifications":  {"type": "array", "items": {"type": "string"}},
                    "preferred_qualifications": {"type": "array", "items": {"type": "string"}},
                    "required_skills":          {"type": "array", "items": {"type": "string"}},
                    "preferred_skills":         {"type": "array", "items": {"type": "string"}},
                    "work_conditions":          {"type": "string"},
                },
            },
            stabilizer_defaults={
                "required_qualifications":  [],
                "preferred_qualifications": [],
                "required_skills":          [],
                "preferred_skills":         [],
                "work_conditions":          "",
            },
            lint_headings=["# 자격 요건:", "## 필수 자격", "## 우대 자격", "## 필수 기술"],
            validator_headings=["## 필수 자격", "## 우대 자격", "## 필수 기술",
                                "## 우대 기술", "## 근무 조건"],
            critical_non_empty_headings=["## 필수 자격", "## 필수 기술"],
        ),
        DocumentSpec(
            key="benefits_culture",
            template_file="job_description_kr/benefits_culture.md.j2",
            json_schema={
                "type": "object",
                "required": ["compensation", "benefits", "culture_values",
                             "work_environment", "unique_perks"],
                "properties": {
                    "compensation":     {"type": "string"},
                    "benefits":         {"type": "array", "items": {"type": "string"}},
                    "culture_values":   {"type": "array", "items": {"type": "string"}},
                    "work_environment": {"type": "string"},
                    "unique_perks":     {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "compensation":     "",
                "benefits":         [],
                "culture_values":   [],
                "work_environment": "",
                "unique_perks":     [],
            },
            lint_headings=["# 복리후생 & 조직문화:", "## 보상 & 급여", "## 복리후생", "## 조직 문화"],
            validator_headings=["## 보상 & 급여", "## 복리후생", "## 조직 문화",
                                "## 근무 환경", "## 특별 혜택"],
            critical_non_empty_headings=["## 복리후생", "## 조직 문화"],
        ),
        DocumentSpec(
            key="hiring_process",
            template_file="job_description_kr/hiring_process.md.j2",
            json_schema={
                "type": "object",
                "required": ["stages", "timeline", "evaluation_criteria",
                             "application_tips", "contact_info"],
                "properties": {
                    "stages":               {"type": "array", "items": {"type": "string"}},
                    "timeline":             {"type": "string"},
                    "evaluation_criteria":  {"type": "array", "items": {"type": "string"}},
                    "application_tips":     {"type": "array", "items": {"type": "string"}},
                    "contact_info":         {"type": "string"},
                },
            },
            stabilizer_defaults={
                "stages":              [],
                "timeline":            "",
                "evaluation_criteria": [],
                "application_tips":    [],
                "contact_info":        "",
            },
            lint_headings=["# 채용 프로세스:", "## 전형 단계", "## 일정 안내", "## 평가 기준"],
            validator_headings=["## 전형 단계", "## 일정 안내", "## 평가 기준",
                                "## 지원 팁", "## 문의"],
            critical_non_empty_headings=["## 전형 단계", "## 평가 기준"],
        ),
    ],
)
