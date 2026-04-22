from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

from scripts.create_pilot_delivery_manifest import (
    build_pilot_delivery_manifest_payload,
    create_pilot_delivery_manifest,
)


def _make_bundle(bundle_file: Path) -> None:
    bundle_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("share-note.md", "share note\n")
        zf.writestr("completion-report.md", "completion report\n")


def test_build_pilot_delivery_manifest_payload_reads_zip_entries(tmp_path):
    bundle_file = tmp_path / "reports" / "pilot" / "sample-delivery-bundle.zip"
    _make_bundle(bundle_file)

    payload = build_pilot_delivery_manifest_payload(bundle_file=bundle_file)

    assert payload["bundle_name"] == bundle_file.name
    assert payload["entry_count"] == 2
    assert payload["entries"][0]["name"] == "completion-report.md"
    assert payload["entries"][1]["name"] == "share-note.md"
    assert payload["entries"][1]["sha256"] == hashlib.sha256(b"share note\n").hexdigest()


def test_create_pilot_delivery_manifest_writes_markdown(tmp_path):
    bundle_file = tmp_path / "reports" / "pilot" / "sample-delivery-bundle.zip"
    _make_bundle(bundle_file)

    payload, output_path = create_pilot_delivery_manifest(
        bundle_file=bundle_file,
        output_dir=bundle_file.parent,
    )

    assert payload["entry_count"] == 2
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "bundle_sha256" in content
    assert "share-note.md" in content
    assert "completion-report.md" in content
