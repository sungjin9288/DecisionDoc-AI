#!/usr/bin/env python3
"""Validate the first-party DocumentOps skill registry without executing skills."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Running a repository script by path puts ``scripts/`` on sys.path, not the
# repository root. Resolve the local package explicitly without importing or
# executing anything from the inspected skill directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.skill_registry import SkillRegistry


RESULT_SCHEMA_VERSION = "document_ops_skill_registry_validation_v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry-dir",
        "--skills-dir",
        dest="registry_dir",
        type=Path,
        default=None,
        help="directory containing first-party .md skills (default: app/agents/skills)",
    )
    parser.add_argument("--json", action="store_true", help="kept for explicit JSON contract compatibility")
    args = parser.parse_args(argv)
    try:
        catalog = SkillRegistry.from_directory(args.registry_dir).catalog()
    except (OSError, UnicodeError, ValueError) as exc:
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "status": "failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 1

    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "passed",
        "skill_count": len(catalog["skills"]),
        "skills": catalog["skills"],
        "catalog_fingerprint": catalog["catalog_fingerprint"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
