from typing import Any

from app.providers.base import Provider


class MockProvider(Provider):
    name = "mock"

    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
    ) -> dict[str, Any]:
        assumptions = requirements.get("assumptions") or [
            "Current requirements are stable for this MVP.",
            "Windows local development is the primary environment.",
        ]
        checks = [
            "Validate document section completeness.",
            "Confirm output readability for mixed audience.",
        ]

        return {
            "adr": {
                "decision": "Use FastAPI API-only service with schema-first provider bundle generation.",
                "options": [
                    "Option A: Keep mock provider default and add adapters.",
                    "Option B: Immediate full LLM dependency (deferred).",
                ],
                "risks": [
                    "Provider SDK integration may fail due to missing keys or environment setup.",
                    "Generated bundle may violate schema if provider output drifts.",
                ],
                "assumptions": assumptions,
                "checks": checks,
                "next_actions": [
                    "Run live-provider tests in secured CI or local env.",
                    "Add provider-specific prompt/version tracking.",
                ],
            },
            "onepager": {
                "problem": "Decision documentation workflows are inconsistent and manual.",
                "recommendation": "Generate standardized bundle once, then render all docs from templates.",
                "impact": [
                    "Improves consistency across ADR, onepager, eval plan, and ops checklist.",
                    "Enables regression testing for structure and validator conformance.",
                ],
                "checks": checks,
            },
            "eval_plan": {
                "metrics": ["Generation success rate", "Validator pass rate", "Response latency"],
                "test_cases": [
                    "Minimal payload with defaults",
                    "Invalid input returns 422",
                    "Provider failure returns PROVIDER_FAILED",
                ],
                "failure_criteria": [
                    "Missing required bundle keys",
                    "Rendered docs fail validator checks",
                ],
                "monitoring": [
                    "Track status codes and provider name in metadata.",
                    "Avoid logging raw payloads containing sensitive text.",
                ],
            },
            "ops_checklist": {
                "security": [
                    "Use environment variables for provider API keys only.",
                    "Never include keys in source, logs, or docs examples.",
                ],
                "reliability": [
                    "Enforce one provider call per request with timeout guard.",
                    "Fail closed on JSON/schema validation errors.",
                ],
                "cost": [
                    "Default provider is mock for offline and low-cost operation.",
                    "Use optional cache to reduce repeated live-provider calls.",
                ],
                "operations": [
                    "Use provider env switch: mock|openai|gemini.",
                    "Run networked tests only with pytest -m live.",
                ],
            },
        }
