"""tech_decision bundle — existing 4-doc set migrated to BundleSpec.

This is a direct migration of the hardcoded constants in:
  - app/domain/schema.py  (BUNDLE_JSON_SCHEMA_V1, _STABILITY_CHECKLIST)
  - app/providers/stabilizer.py (_REQUIRED_STRUCTURE)
  - app/domain/headings.py (LINT_HEADINGS, VALIDATOR_HEADINGS, CRITICAL_NON_EMPTY_HEADINGS)

Behaviour is identical to the pre-catalog pipeline.
"""
from app.bundle_catalog.spec import BundleSpec, DocumentSpec

TECH_DECISION = BundleSpec(
    id="tech_decision",
    name_ko="기술 의사결정",
    name_en="Tech Decision",
    description_ko="소프트웨어 아키텍처 및 기술 결정을 위한 ADR, Onepager, Eval Plan, Ops Checklist 4종 문서",
    icon="⚙️",
    prompt_language="en",
    prompt_hint=(
        "You are a senior software architect with 15+ years of experience designing large-scale systems.\n"
        "Before writing, internally reason through: (1) what tradeoffs are most critical, "
        "(2) what risks are most likely to materialize, (3) what options a strong engineer would consider.\n"
        "- options: include 3+ real alternatives with concrete names (e.g. 'PostgreSQL', 'Kafka'), not generic placeholders.\n"
        "- risks: cover technical, operational, cost, and security dimensions; each risk must include a specific mitigation.\n"
        "- next_actions: each action must have an implied owner role (e.g. 'DevOps team') and a concrete deliverable.\n"
        "- decision: state the chosen option in one assertive sentence and explain the primary reason.\n"
        "- Do not write vague or template-like content. Use specific, context-aware details from the requirements."
    ),
    category="consulting",
    few_shot_example=(
        "## Goal\n"
        "Decide whether to migrate KakaoPay's payment service (20M monthly transactions) from monolith to MSA.\n"
        "Current 3-week deployment cycles and cascading failures are causing measurable business impact.\n"
        "\n"
        "## Decision\n"
        "**Adopt Strangler Fig pattern** — new features built as independent microservices; legacy monolith decomposed in 3 phases by Q3 2026.\n"
        "\n"
        "## Options\n"
        "- **Option A (Selected): Strangler Fig** — risk distribution, 18-month roadmap, no service interruption\n"
        "- **Option B: Big Bang Rewrite** — 6-month full stop, unacceptable for 24/7 payment service\n"
        "- **Option C: Status Quo** — bottleneck reaches critical point within 12 months; not viable\n"
    ),
    docs=[
        DocumentSpec(
            key="adr",
            template_file="adr.md.j2",
            json_schema={
                "type": "object",
                "required": ["decision", "options", "risks", "assumptions", "checks", "next_actions"],
                "properties": {
                    "decision": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                    "checks": {"type": "array", "items": {"type": "string"}},
                    "next_actions": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "decision": "",
                "options": [],
                "risks": [],
                "assumptions": [],
                "checks": [],
                "next_actions": [],
            },
            lint_headings=["# ADR:", "## Goal", "## Decision", "## Options"],
            validator_headings=["## Goal", "## Decision", "## Options", "## Risks", "## Assumptions", "## Checks", "## Next actions"],
            critical_non_empty_headings=["## Goal", "## Decision", "## Options"],
        ),
        DocumentSpec(
            key="onepager",
            template_file="onepager.md.j2",
            json_schema={
                "type": "object",
                "required": ["problem", "recommendation", "impact", "checks"],
                "properties": {
                    "problem": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "impact": {"type": "array", "items": {"type": "string"}},
                    "checks": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "problem": "",
                "recommendation": "",
                "impact": [],
                "checks": [],
            },
            lint_headings=["# Onepager:", "## Problem", "## Recommendation", "## Impact"],
            validator_headings=["## Problem", "## Recommendation", "## Impact", "## Checks"],
            critical_non_empty_headings=["## Problem", "## Recommendation", "## Impact"],
        ),
        DocumentSpec(
            key="eval_plan",
            template_file="eval_plan.md.j2",
            json_schema={
                "type": "object",
                "required": ["metrics", "test_cases", "failure_criteria", "monitoring"],
                "properties": {
                    "metrics": {"type": "array", "items": {"type": "string"}},
                    "test_cases": {"type": "array", "items": {"type": "string"}},
                    "failure_criteria": {"type": "array", "items": {"type": "string"}},
                    "monitoring": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "metrics": [],
                "test_cases": [],
                "failure_criteria": [],
                "monitoring": [],
            },
            lint_headings=["# Eval Plan:", "## Metrics", "## Test cases", "## Failure criteria"],
            validator_headings=["## Metrics", "## Test cases", "## Failure criteria", "## Monitoring"],
            critical_non_empty_headings=["## Metrics", "## Test cases", "## Failure criteria", "## Monitoring"],
        ),
        DocumentSpec(
            key="ops_checklist",
            template_file="ops_checklist.md.j2",
            json_schema={
                "type": "object",
                "required": ["security", "reliability", "cost", "operations"],
                "properties": {
                    "security": {"type": "array", "items": {"type": "string"}},
                    "reliability": {"type": "array", "items": {"type": "string"}},
                    "cost": {"type": "array", "items": {"type": "string"}},
                    "operations": {"type": "array", "items": {"type": "string"}},
                },
            },
            stabilizer_defaults={
                "security": [],
                "reliability": [],
                "cost": [],
                "operations": [],
            },
            lint_headings=["# Ops Checklist:", "## Security", "## Reliability", "## Cost", "## Operations"],
            validator_headings=["## Security", "## Reliability", "## Cost", "## Operations"],
            critical_non_empty_headings=["## Security", "## Reliability", "## Cost", "## Operations"],
        ),
    ],
)
