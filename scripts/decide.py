#!/usr/bin/env python3
"""CLI tool for generating decision documents without a running HTTP server.

Usage examples:
    # Basic (mock provider, no API key needed)
    DECISIONDOC_PROVIDER=mock python scripts/decide.py \\
        --title "Redis 도입" --goal "세션 캐싱 성능 개선"

    # Write to directory
    DECISIONDOC_PROVIDER=mock python scripts/decide.py \\
        --title "Redis 도입" --goal "세션 캐싱" \\
        --output ./docs/redis-decision

    # OpenAI provider
    DECISIONDOC_PROVIDER=openai OPENAI_API_KEY=sk-... python scripts/decide.py \\
        --title "Redis 도입" --goal "세션 캐싱" --doc-types "adr,onepager"

    # Read args from JSON file (used by GitHub Actions to avoid shell injection)
    python scripts/decide.py --from-json /tmp/decide_args.json --output ./decide-output
"""
import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

# Ensure the project root is on sys.path so `app.*` imports work when running
# this script directly (e.g. `python scripts/decide.py`) without PYTHONPATH.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_DOC_TYPES = {"adr", "onepager", "eval_plan", "ops_checklist"}
DEFAULT_DOC_TYPES = ["adr", "onepager", "eval_plan", "ops_checklist"]
DOC_TYPE_ORDER = ["adr", "onepager", "eval_plan", "ops_checklist"]
METADATA_FILENAME = "_metadata.json"


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate decision documents (ADR, Onepager, Eval Plan, Ops Checklist).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--title", help="Decision title (required unless --from-json)")
    parser.add_argument("--goal", help="Goal / objective (required unless --from-json)")
    parser.add_argument("--context", default="", help="Background context (optional)")
    parser.add_argument("--constraints", default="", help="Constraints (optional)")
    parser.add_argument(
        "--priority",
        default="maintainability > security > cost > performance > speed",
        help="Priority order string",
    )
    parser.add_argument("--audience", default="mixed", help="Target audience (default: mixed)")
    parser.add_argument(
        "--doc-types",
        default=",".join(DEFAULT_DOC_TYPES),
        help="Comma-separated doc types to generate (default: all 4). "
        "Valid: adr, onepager, eval_plan, ops_checklist",
    )
    parser.add_argument(
        "--output",
        metavar="DIR",
        help="Output directory. Each doc_type saved as {doc_type}.md. "
        "If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--from-json",
        metavar="FILE",
        help="Load args from a JSON file (overrides CLI args). "
        "Used by GitHub Actions to avoid shell injection.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress metadata summary on stderr.",
    )
    return parser


# ---------------------------------------------------------------------------
# Provider validation
# ---------------------------------------------------------------------------

def _validate_provider_env(provider_names: list[str]) -> None:
    """Fail fast if required API keys are missing for non-mock providers."""
    if "openai" in provider_names and not os.getenv("OPENAI_API_KEY", "").strip():
        raise SystemExit("Error: OPENAI_API_KEY is required when DECISIONDOC_PROVIDER=openai.")
    if "gemini" in provider_names and not os.getenv("GEMINI_API_KEY", "").strip():
        raise SystemExit("Error: GEMINI_API_KEY is required when DECISIONDOC_PROVIDER=gemini.")
    if "claude" in provider_names and not os.getenv("ANTHROPIC_API_KEY", "").strip():
        raise SystemExit("Error: ANTHROPIC_API_KEY is required when DECISIONDOC_PROVIDER=claude.")


# ---------------------------------------------------------------------------
# Service construction (mirrors app/main.py pattern)
# ---------------------------------------------------------------------------

def _build_service():
    """Construct GenerationService directly (no HTTP server needed)."""
    from app.providers.factory import get_provider
    from app.services.generation_service import GenerationService

    template_version = os.getenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    # scripts/ is one level below the project root
    template_dir = Path(__file__).resolve().parent.parent / "app" / "templates" / template_version
    if not template_dir.is_dir():
        raise SystemExit(f"Error: Template directory not found: {template_dir}")

    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return GenerationService(
        provider_factory=get_provider,
        template_dir=template_dir,
        data_dir=data_dir,
        storage=None,
    )


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------

def _parse_doc_types(raw: str) -> list[str]:
    """Parse and validate comma-separated doc type string."""
    types = [t.strip().lower() for t in raw.split(",") if t.strip()]
    unknown = [t for t in types if t not in VALID_DOC_TYPES]
    if unknown:
        raise SystemExit(
            f"Error: Unknown doc_types: {unknown}. "
            f"Valid values: {sorted(VALID_DOC_TYPES)}"
        )
    if not types:
        raise SystemExit("Error: --doc-types must not be empty.")
    return types


def _build_request(args: argparse.Namespace):
    """Convert parsed CLI args to a GenerateRequest."""
    from app.schemas import GenerateRequest, DocType

    doc_types_raw = getattr(args, "doc_types", ",".join(DEFAULT_DOC_TYPES)) or ",".join(DEFAULT_DOC_TYPES)
    doc_type_strs = _parse_doc_types(doc_types_raw)

    return GenerateRequest(
        title=args.title,
        goal=args.goal,
        context=getattr(args, "context", "") or "",
        constraints=getattr(args, "constraints", "") or "",
        priority=getattr(args, "priority", "maintainability > security > cost > performance > speed") or "maintainability > security > cost > performance > speed",
        audience=getattr(args, "audience", "mixed") or "mixed",
        doc_types=[DocType(t) for t in doc_type_strs],
        assumptions=[],
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _write_output_dir(output_dir: Path, docs: list[dict], metadata: dict, quiet: bool) -> None:
    """Write docs and workflow metadata to output_dir."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(f"Error: Cannot create output directory {output_dir}: {e}") from e

    written = []
    for doc in docs:
        doc_type = doc["doc_type"]
        filename = output_dir / f"{doc_type}.md"
        try:
            filename.write_text(doc["markdown"], encoding="utf-8")
            written.append(str(filename))
        except OSError as e:
            raise SystemExit(f"Error: Cannot write {filename}: {e}") from e

    meta_path = output_dir / METADATA_FILENAME
    try:
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        raise SystemExit(f"Error: Cannot write {meta_path}: {e}") from e

    if not quiet:
        for path in written:
            print(f"  wrote: {path}", file=sys.stderr)
        print(f"  wrote: {meta_path}", file=sys.stderr)


def _write_stdout(docs: list[dict]) -> None:
    """Print all docs to stdout with separators, in canonical order."""
    ordered = sorted(docs, key=lambda d: DOC_TYPE_ORDER.index(d["doc_type"]) if d["doc_type"] in DOC_TYPE_ORDER else 99)
    for i, doc in enumerate(ordered):
        if i > 0:
            print("\n" + "─" * 72 + "\n")
        print(doc["markdown"])


def _print_metadata(metadata: dict, quiet: bool) -> None:
    """Print metadata summary to stderr."""
    if quiet:
        return
    provider = metadata.get("provider", "unknown")
    bundle_id = metadata.get("bundle_id", "")
    cache_hit = metadata.get("cache_hit")
    timings = metadata.get("timings_ms", {})

    parts = [f"provider={provider}", f"bundle_id={bundle_id[:12]}..."]
    if cache_hit is not None:
        parts.append(f"cache_hit={cache_hit}")
    if timings:
        total_ms = sum(v for v in timings.values() if isinstance(v, (int, float)))
        parts.append(f"total_ms={total_ms:.0f}")

    print(f"[decide] {' | '.join(parts)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    load_dotenv()
    parser = _build_arg_parser()
    args = parser.parse_args()

    # --from-json: override args with JSON file content (GitHub Actions safe path)
    if args.from_json:
        json_path = Path(args.from_json)
        if not json_path.is_file():
            raise SystemExit(f"Error: --from-json file not found: {json_path}")
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise SystemExit(f"Error: Cannot read --from-json file: {e}") from e

        # Override each field if present in JSON (don't override non-None CLI values)
        for field in ("title", "goal", "context", "constraints", "priority", "audience"):
            if field in data and data[field]:
                setattr(args, field, data[field])
        if "doc_types" in data and data["doc_types"]:
            setattr(args, "doc_types", data["doc_types"])
        # output from CLI takes precedence over JSON
        if not args.output and data.get("output"):
            args.output = data["output"]

    # Validate required fields
    if not getattr(args, "title", None):
        parser.error("--title is required (or provide via --from-json)")
    if not getattr(args, "goal", None):
        parser.error("--goal is required (or provide via --from-json)")

    # Provider validation
    configured_provider = os.getenv("DECISIONDOC_PROVIDER", "mock").lower()
    provider_names = [n.strip() for n in configured_provider.split(",") if n.strip()]
    _validate_provider_env(provider_names)

    # Build service and request
    try:
        service = _build_service()
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error: Failed to initialize service: {e}", file=sys.stderr)
        return 1

    try:
        req = _build_request(args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error: Invalid request: {e}", file=sys.stderr)
        return 1

    # Generate documents
    request_id = str(uuid4())
    if not args.quiet:
        print(f"[decide] Generating documents... (provider={configured_provider})", file=sys.stderr)

    try:
        from app.services.generation_service import EvalLintFailedError, ProviderFailedError
        result = service.generate_documents(req, request_id=request_id)
    except ProviderFailedError as e:
        print(f"Error: Provider failed: {e}", file=sys.stderr)
        return 1
    except EvalLintFailedError as e:
        print("Error: Quality checks failed:", file=sys.stderr)
        for err in e.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: Generation failed: {e}", file=sys.stderr)
        return 1

    docs = result["docs"]
    metadata = result["metadata"]

    # Output
    if args.output:
        output_dir = Path(args.output)
        _write_output_dir(output_dir, docs, metadata, args.quiet)
    else:
        _write_stdout(docs)

    _print_metadata(metadata, args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
