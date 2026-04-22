#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_BUNDLE = _load_module("create_pilot_delivery_bundle.py", "decisiondoc_create_pilot_delivery_bundle")
_MANIFEST = _load_module("create_pilot_delivery_manifest.py", "decisiondoc_create_pilot_delivery_manifest")
_RECEIPT = _load_module("create_pilot_delivery_receipt.py", "decisiondoc_create_pilot_delivery_receipt")
_VERIFY = _load_module("verify_pilot_delivery_bundle.py", "decisiondoc_verify_pilot_delivery_bundle")

build_pilot_delivery_bundle_payload = _BUNDLE.build_pilot_delivery_bundle_payload
parse_pilot_delivery_manifest = _MANIFEST.parse_pilot_delivery_manifest
build_pilot_delivery_receipt_payload = _RECEIPT.build_pilot_delivery_receipt_payload
verify_pilot_delivery_bundle = _VERIFY.verify_pilot_delivery_bundle


def _derive_delivery_paths(closeout_file: Path) -> dict[str, Path]:
    bundle_file = closeout_file.parent / f"{closeout_file.stem}-delivery-bundle.zip"
    manifest_file = closeout_file.parent / f"{bundle_file.stem}-manifest.md"
    receipt_file = closeout_file.parent / f"{bundle_file.stem}-receipt.md"
    return {
        "bundle": bundle_file,
        "manifest": manifest_file,
        "receipt": receipt_file,
    }


def _collect_stale_artifacts(*, closeout_file: Path, checks: list[dict[str, str]]) -> list[str]:
    generated_names = {
        "share_note",
        "completion_report",
        "delivery_index",
        "bundle",
        "manifest",
        "receipt",
        "audit",
    }
    closeout_mtime = closeout_file.stat().st_mtime
    stale: list[str] = []
    for item in checks:
        name = item["name"]
        if name not in generated_names or item["status"] != "ok":
            continue
        path = Path(item["path"])
        if path.stat().st_mtime < closeout_mtime:
            stale.append(name)
    return stale


def _parse_receipt(receipt_file: Path) -> dict[str, str]:
    if not receipt_file.exists():
        return {}

    data: dict[str, str] = {}
    for raw_line in receipt_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- verification_status:"):
            parts = line.split("**")
            data["verification_status"] = parts[1] if len(parts) > 1 else "-"
        elif line.startswith("- bundle_sha256:"):
            data["bundle_sha256"] = line.split("`", 2)[1]
        elif line.startswith("- manifest_bundle_sha256:"):
            data["manifest_bundle_sha256"] = line.split("`", 2)[1]
        elif line.startswith("- entry_count:"):
            data["entry_count"] = line.split("`", 2)[1]
        elif line.startswith("- manifest_entry_count:"):
            data["manifest_entry_count"] = line.split("`", 2)[1]
    return data


def build_pilot_delivery_audit_payload(*, closeout_file: Path) -> dict[str, object]:
    bundle_payload = build_pilot_delivery_bundle_payload(closeout_file=closeout_file)
    artifacts = dict(bundle_payload.get("artifact_paths") or {})
    delivery_paths = _derive_delivery_paths(closeout_file)

    checks: list[dict[str, str]] = []
    all_ok = True

    for key, raw in artifacts.items():
        path = Path(str(raw))
        ok = path.exists()
        checks.append({"name": key, "path": str(path), "status": "ok" if ok else "missing"})
        all_ok = all_ok and ok

    for key, path in delivery_paths.items():
        ok = path.exists()
        checks.append({"name": key, "path": str(path), "status": "ok" if ok else "missing"})
        all_ok = all_ok and ok

    stale_artifacts = _collect_stale_artifacts(closeout_file=closeout_file, checks=checks)
    if stale_artifacts:
        all_ok = False

    verification = {"ok": False, "errors": ["bundle or manifest missing"], "bundle_sha256": "-", "entry_count": 0}
    manifest = {"bundle_sha256": "-", "entry_count": 0}
    if delivery_paths["bundle"].exists() and delivery_paths["manifest"].exists():
        verification = verify_pilot_delivery_bundle(
            bundle_file=delivery_paths["bundle"],
            manifest_file=delivery_paths["manifest"],
        )
        manifest = parse_pilot_delivery_manifest(manifest_file=delivery_paths["manifest"])
        all_ok = all_ok and bool(verification.get("ok"))
    else:
        all_ok = False

    receipt_data = _parse_receipt(delivery_paths["receipt"])
    receipt_matches = (
        receipt_data.get("verification_status") == ("PASS" if verification.get("ok") else "FAIL")
        and receipt_data.get("bundle_sha256") == str(verification.get("bundle_sha256", "-"))
        and receipt_data.get("manifest_bundle_sha256") == str(manifest.get("bundle_sha256", "-"))
        and receipt_data.get("entry_count") == str(verification.get("entry_count", 0))
        and receipt_data.get("manifest_entry_count") == str(manifest.get("entry_count", 0))
    )
    if not receipt_data:
        receipt_matches = False
    all_ok = all_ok and receipt_matches

    return {
        "closeout_file": str(closeout_file),
        "status": "PASS" if all_ok else "FAIL",
        "checks": checks,
        "bundle_sha256": verification.get("bundle_sha256", "-"),
        "entry_count": verification.get("entry_count", 0),
        "manifest_bundle_sha256": manifest.get("bundle_sha256", "-"),
        "manifest_entry_count": manifest.get("entry_count", 0),
        "verification_errors": verification.get("errors") or [],
        "receipt_matches": receipt_matches,
        "receipt_file": str(delivery_paths["receipt"]),
        "stale": bool(stale_artifacts),
        "stale_artifacts": stale_artifacts,
    }


def build_pilot_delivery_audit_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    check_lines = "\n".join(
        f"- {item['name']}: `{item['status']}` — `{item['path']}`" for item in payload.get("checks") or []
    )
    errors = payload.get("verification_errors") or []
    error_lines = "\n".join(f"- {item}" for item in errors) if errors else "- 없음"
    return f"""# Pilot Delivery Audit — {Path(str(payload.get('closeout_file', '-'))).name}

- generated_at: {generated_at.isoformat()}
- audit_status: **{payload.get('status', 'FAIL')}**
- closeout_file: `{payload.get('closeout_file', '-')}`

## Artifact Presence

{check_lines}

## Integrity Check

- bundle_sha256: `{payload.get('bundle_sha256', '-')}`
- manifest_bundle_sha256: `{payload.get('manifest_bundle_sha256', '-')}`
- entry_count: `{payload.get('entry_count', 0)}`
- manifest_entry_count: `{payload.get('manifest_entry_count', 0)}`

## Receipt Consistency

- receipt_file: `{payload.get('receipt_file', '-')}`
- receipt_matches_current_verification: `{str(payload.get('receipt_matches', False)).lower()}`
- stale: `{str(payload.get('stale', False)).lower()}`
- stale_artifacts: `{", ".join(payload.get('stale_artifacts') or []) or "-"}`

## Verification Errors

{error_lines}
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_delivery_audit(*, closeout_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    payload = build_pilot_delivery_audit_payload(closeout_file=closeout_file)
    output_path = output_dir / f"{closeout_file.stem}-delivery-audit.md"
    markdown = build_pilot_delivery_audit_markdown(payload=payload, generated_at=datetime.now(timezone.utc))
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the final pilot delivery chain from closeout to bundle, manifest, and receipt.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery audit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_delivery_audit(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot delivery audit: {output_path}", flush=True)
    print(f"Audit status: {payload.get('status', 'FAIL')}", flush=True)
    print(f"Receipt matches verification: {str(payload.get('receipt_matches', False)).lower()}", flush=True)
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
