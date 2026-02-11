from copy import deepcopy
from typing import Any


_INTERNAL_MARKER_KEY = "_stabilized"

_REQUIRED_STRUCTURE: dict[str, dict[str, Any]] = {
    "adr": {
        "decision": "",
        "options": [],
        "risks": [],
        "assumptions": [],
        "checks": [],
        "next_actions": [],
    },
    "onepager": {
        "problem": "",
        "recommendation": "",
        "impact": [],
        "checks": [],
    },
    "eval_plan": {
        "metrics": [],
        "test_cases": [],
        "failure_criteria": [],
        "monitoring": [],
    },
    "ops_checklist": {
        "security": [],
        "reliability": [],
        "cost": [],
        "operations": [],
    },
}


def stabilize_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    working = deepcopy(bundle) if isinstance(bundle, dict) else {}
    patched: list[str] = []

    for top_key, required_fields in _REQUIRED_STRUCTURE.items():
        section = working.get(top_key)
        if not isinstance(section, dict):
            working[top_key] = {}
            section = working[top_key]
            patched.append(f"top_level:{top_key}")

        for field, default in required_fields.items():
            value = section.get(field)
            if isinstance(default, str):
                if not isinstance(value, str):
                    section[field] = ""
                    patched.append(f"{top_key}.{field}")
            elif isinstance(default, list):
                if not isinstance(value, list):
                    section[field] = []
                    patched.append(f"{top_key}.{field}")

    if patched:
        working[_INTERNAL_MARKER_KEY] = {"patched": patched}
    return working


def strip_internal_bundle_fields(bundle: dict[str, Any]) -> dict[str, Any]:
    clean = deepcopy(bundle)
    clean.pop(_INTERNAL_MARKER_KEY, None)
    return clean
