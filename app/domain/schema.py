SCHEMA_VERSION = "v1"


BUNDLE_JSON_SCHEMA_V1: dict = {
    "type": "object",
    "required": ["adr", "onepager", "eval_plan", "ops_checklist"],
    "properties": {
        "adr": {
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
        "onepager": {
            "type": "object",
            "required": ["problem", "recommendation", "impact", "checks"],
            "properties": {
                "problem": {"type": "string"},
                "recommendation": {"type": "string"},
                "impact": {"type": "array", "items": {"type": "string"}},
                "checks": {"type": "array", "items": {"type": "string"}},
            },
        },
        "eval_plan": {
            "type": "object",
            "required": ["metrics", "test_cases", "failure_criteria", "monitoring"],
            "properties": {
                "metrics": {"type": "array", "items": {"type": "string"}},
                "test_cases": {"type": "array", "items": {"type": "string"}},
                "failure_criteria": {"type": "array", "items": {"type": "string"}},
                "monitoring": {"type": "array", "items": {"type": "string"}},
            },
        },
        "ops_checklist": {
            "type": "object",
            "required": ["security", "reliability", "cost", "operations"],
            "properties": {
                "security": {"type": "array", "items": {"type": "string"}},
                "reliability": {"type": "array", "items": {"type": "string"}},
                "cost": {"type": "array", "items": {"type": "string"}},
                "operations": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}
