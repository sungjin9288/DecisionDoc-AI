from __future__ import annotations

from pathlib import Path
import zipfile

from scripts.create_pilot_delivery_manifest import create_pilot_delivery_manifest
from scripts.verify_pilot_delivery_bundle import (
    parse_pilot_delivery_manifest,
    verify_pilot_delivery_bundle,
)


def _make_bundle(bundle_file: Path, *, share_note: str = "share note\n") -> None:
    bundle_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("share-note.md", share_note)
        zf.writestr("completion-report.md", "completion report\n")


def test_parse_pilot_delivery_manifest_reads_expected_fields(tmp_path):
    bundle_file = tmp_path / "reports" / "pilot" / "sample-delivery-bundle.zip"
    _make_bundle(bundle_file)
    _, manifest_file = create_pilot_delivery_manifest(
        bundle_file=bundle_file,
        output_dir=bundle_file.parent,
    )

    parsed = parse_pilot_delivery_manifest(manifest_file=manifest_file)

    assert parsed["entry_count"] == 2
    assert parsed["bundle_sha256"]
    assert parsed["entries"][0]["name"] == "completion-report.md"
    assert parsed["entries"][1]["name"] == "share-note.md"


def test_verify_pilot_delivery_bundle_passes_for_matching_bundle(tmp_path):
    bundle_file = tmp_path / "reports" / "pilot" / "sample-delivery-bundle.zip"
    _make_bundle(bundle_file)
    _, manifest_file = create_pilot_delivery_manifest(
        bundle_file=bundle_file,
        output_dir=bundle_file.parent,
    )

    result = verify_pilot_delivery_bundle(
        bundle_file=bundle_file,
        manifest_file=manifest_file,
    )

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["entry_count"] == 2


def test_verify_pilot_delivery_bundle_fails_for_tampered_bundle(tmp_path):
    bundle_file = tmp_path / "reports" / "pilot" / "sample-delivery-bundle.zip"
    _make_bundle(bundle_file)
    _, manifest_file = create_pilot_delivery_manifest(
        bundle_file=bundle_file,
        output_dir=bundle_file.parent,
    )
    _make_bundle(bundle_file, share_note="tampered share note\n")

    result = verify_pilot_delivery_bundle(
        bundle_file=bundle_file,
        manifest_file=manifest_file,
    )

    assert result["ok"] is False
    assert any("bundle sha256 mismatch" in error for error in result["errors"])
