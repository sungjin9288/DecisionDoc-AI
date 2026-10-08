#!/usr/bin/env python3
"""Export the bundle catalog as DocumentOps document-type data (merge prep).

The merged local tool takes Markdown manuscripts written by the session, so it
needs each bundle's documents, required headings and writing guidance, not the
JSON schema, Jinja2 templates or few-shot examples (see
docs/superpowers/specs/2026-10-08-documentops-merge-port-spec.md §2-3).

    python3 scripts/export_documentops_type_catalog.py            # rewrite the tracked file
    python3 scripts/export_documentops_type_catalog.py --check    # fail if it is stale
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA_VERSION = "decisiondoc.documentops_type_catalog.v1"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "integration" / "documentops-type-catalog-v1.json"
TEMPLATE_DIR = REPO_ROOT / "app" / "templates" / "v1"
STYLE_GUIDE_PATH = REPO_ROOT / "app" / "bundle_catalog" / "style_guide.yaml"
# Concrete amounts or ratios in guidance would push the writer toward unsupported numbers.
AMOUNT_PATTERN = re.compile(r"\d[\d,.]*\s*(?:억|만\s*원|천\s*원|원|%|퍼센트)")


def _template_heading_lines(template_file: str) -> list[str]:
    path = TEMPLATE_DIR / template_file
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.lstrip().startswith("#")]


def _ordered_required_headings(doc: Any) -> list[str]:
    """Union of lint and validator headings, in the order the template writes them."""
    required = list(dict.fromkeys([*doc.lint_headings, *doc.validator_headings]))
    lines = _template_heading_lines(doc.template_file)

    def position(heading: str) -> int:
        return next((index for index, line in enumerate(lines) if heading in line), len(lines))

    return sorted(required, key=lambda heading: (position(heading), required.index(heading)))


def _json_field_names(doc: Any) -> set[str]:
    return set((doc.json_schema or {}).get("properties", {}))


def _bundle_entry(spec: Any, overrides: dict[str, Any]) -> dict[str, Any]:
    documents = [
        {
            "key": doc.key,
            "required_headings": _ordered_required_headings(doc),
            "non_empty_headings": list(doc.critical_non_empty_headings),
        }
        for doc in spec.docs
    ]
    field_names = set().union(*(_json_field_names(doc) for doc in spec.docs))
    guidance = spec.prompt_hint.strip()
    style_rules = list((overrides.get(spec.id) or {}).get("extra_rules", []))
    return {
        "id": spec.id,
        "name_ko": spec.name_ko,
        "category": spec.category,
        "documents": documents,
        "guidance": guidance,
        # The guidance was written for JSON output; these field names need rewording for Markdown.
        "guidance_json_fields": sorted(name for name in field_names if name in guidance),
        "style_rules": style_rules,
        "amount_mentions": sorted({match.group(0) for match in AMOUNT_PATTERN.finditer(guidance + "\n".join(style_rules))}),
        "few_shot_excluded": bool(spec.few_shot_example),
    }


def build_catalog() -> dict[str, Any]:
    import yaml

    from app.bundle_catalog.registry import BUNDLE_REGISTRY
    from app.bundle_catalog.system_prompt import QUALITY_IMPROVEMENTS

    style_guide = yaml.safe_load(STYLE_GUIDE_PATH.read_text(encoding="utf-8")) or {}
    overrides = style_guide.get("bundle_overrides", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "DecisionDoc-AI app/bundle_catalog (bundles, style_guide.yaml, system_prompt.py)",
        "heading_match": "substring; a heading ending with ':' is followed by the document title",
        "excluded": ["json_schema", "jinja2_templates", "stabilizer_defaults", "few_shot_examples", "prompt_variants"],
        "common": {
            "quality_rules": QUALITY_IMPROVEMENTS.strip(),
            "style_guide": style_guide.get("global", {}),
            "language": style_guide.get("language", {}),
        },
        "types": [_bundle_entry(spec, overrides) for spec in sorted(BUNDLE_REGISTRY.values(), key=lambda item: item.id)],
    }


def render(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--check", action="store_true", help="Fail when the output file differs from the catalog.")
    args = parser.parse_args(argv)
    output = Path(args.output)
    text = render(build_catalog())
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != text:
            print(f"stale: {output}; rerun without --check", file=sys.stderr)
            return 1
        print(f"up to date: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
