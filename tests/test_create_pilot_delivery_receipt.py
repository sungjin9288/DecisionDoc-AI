from __future__ import annotations

from pathlib import Path
import zipfile

from scripts.create_pilot_delivery_manifest import create_pilot_delivery_manifest
from scripts.create_pilot_delivery_receipt import (
    build_pilot_delivery_receipt_payload,
    create_pilot_delivery_receipt,
)


def _make_bundle(bundle_file: Path, *, share_note: str = "share note\n") -> None:
    bundle_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("share-note.md", share_note)
        zf.writestr("completion-report.md", "completion report\n")


def test_build_pilot_delivery_receipt_payload_for_verified_bundle(tmp_path):
    bundle_file = tmp_path / "reports" / "pilot" / "sample-delivery-bundle.zip"
    _make_bundle(bundle_file)
    _, manifest_file = create_pilot_delivery_manifest(
        bundle_file=bundle_file,
        output_dir=bundle_file.parent,
    )

    payload = build_pilot_delivery_receipt_payload(
        bundle_file=bundle_file,
        manifest_file=manifest_file,
    )

    assert payload["verification_status"] == "PASS"
    assert payload["entry_count"] == 2
    assert payload["verification_errors"] == []


def test_create_pilot_delivery_receipt_writes_markdown(tmp_path):
    bundle_file = tmp_path / "reports" / "pilot" / "sample-delivery-bundle.zip"
    _make_bundle(bundle_file)
    _, manifest_file = create_pilot_delivery_manifest(
        bundle_file=bundle_file,
        output_dir=bundle_file.parent,
    )

    payload, output_path = create_pilot_delivery_receipt(
        bundle_file=bundle_file,
        manifest_file=manifest_file,
        output_dir=bundle_file.parent,
    )

    assert payload["verification_status"] == "PASS"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "verification_status" in content
    assert "bundle_sha256" in content
    assert "manifest_bundle_sha256" in content
