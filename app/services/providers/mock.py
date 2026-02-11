from app.schemas import DocType, GenerateRequest
from app.services.providers.base import Provider


class MockProvider(Provider):
    @property
    def name(self) -> str:
        return "mock"

    def build_context(self, doc_type: DocType, request: GenerateRequest) -> dict:
        assumptions = request.assumptions or [
            "Current requirements are stable for the next 2 weeks.",
            "Windows local development is the primary environment.",
        ]
        checks = [
            "Validate output structure and section completeness.",
            "Confirm generated markdown can be reviewed by mixed audience.",
        ]

        base_context = {
            "title": request.title,
            "goal": request.goal,
            "context": request.context or "No additional context provided.",
            "constraints": request.constraints or "No explicit constraints provided.",
            "priority": request.priority,
            "audience": request.audience,
            "assumptions": assumptions,
            "checks": checks,
        }

        if doc_type == DocType.adr:
            return {
                **base_context,
                "decision": "Use FastAPI with a mock provider and template-first generation.",
                "options": [
                    "Option A: Build API-only MVP with MockProvider and filesystem persistence.",
                    "Option B: Add real LLM integration now (rejected for MVP stability).",
                ],
                "risks": [
                    "Generated content quality may be simplistic before LLM integration.",
                    "Storing request payloads may include sensitive text if users ignore warnings.",
                ],
                "next_actions": [
                    "Add provider adapter interface tests.",
                    "Introduce authenticated storage and retention policy in next iteration.",
                ],
            }

        if doc_type == DocType.onepager:
            return {
                **base_context,
                "problem": "Decision documentation is inconsistent and slow without a standard pipeline.",
                "recommendation": "Generate four standardized markdown documents from a single request.",
                "impact": [
                    "Faster decision record creation and review.",
                    "Repeatable artifact format for future automation.",
                ],
            }

        if doc_type == DocType.eval_plan:
            return {
                **base_context,
                "metrics": [
                    "Generation success rate",
                    "Median response time",
                    "Template section completeness",
                ],
                "test_cases": [
                    "Minimal payload with default doc types",
                    "Custom doc_types order is preserved",
                    "Invalid payload is rejected by strict schema",
                ],
                "failure_criteria": [
                    "Any required section missing in rendered markdown",
                    "Response schema mismatch or non-200 for valid request",
                ],
                "monitoring": [
                    "Track request count and error count only",
                    "Avoid logging full request payload to protect sensitive data",
                ],
            }

        return {
            **base_context,
            "security": [
                "Do not log sensitive request text.",
                "Disallow hardcoded secrets in source.",
            ],
            "reliability": [
                "Persist each request atomically to disk.",
                "Keep provider behavior deterministic for tests.",
            ],
            "cost": [
                "No external API calls in MVP.",
                "Run fully on local environment with free-tier tooling.",
            ],
            "operations": [
                "Run service via uvicorn.",
                "Review generated JSON records in DATA_DIR for troubleshooting.",
            ],
        }
