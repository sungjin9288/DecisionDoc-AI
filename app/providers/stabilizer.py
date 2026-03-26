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


def stabilize_bundle(
    bundle: dict[str, Any],
    structure: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Patch missing fields in a provider bundle with safe defaults.

    Args:
        bundle:    The raw dict returned by the provider.
        structure: Per-doc field defaults to enforce.  When *None* (default)
                   the legacy ``_REQUIRED_STRUCTURE`` for the tech_decision
                   bundle is used, preserving backward compatibility.
    """
    effective = structure if structure is not None else _REQUIRED_STRUCTURE
    working = deepcopy(bundle) if isinstance(bundle, dict) else {}
    patched: list[str] = []

    for top_key, required_fields in effective.items():
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
            elif isinstance(default, int):
                if not isinstance(value, int):
                    section[field] = default
                    patched.append(f"{top_key}.{field}")
            elif isinstance(default, list):
                if not isinstance(value, list):
                    section[field] = []
                    patched.append(f"{top_key}.{field}")
                else:
                    # Coerce non-string items in arrays (e.g. int → str).
                    # Dict items (slide_outline objects) are kept as-is.
                    section[field] = [
                        str(item) if not isinstance(item, (str, dict)) else item
                        for item in value
                    ]

    if patched:
        working[_INTERNAL_MARKER_KEY] = {"patched": patched}
    return working


def strip_internal_bundle_fields(bundle: dict[str, Any]) -> dict[str, Any]:
    clean = deepcopy(bundle)
    clean.pop(_INTERNAL_MARKER_KEY, None)
    return clean
