from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import manage_portfolio_pack as manager


def _write_sources(root: Path) -> tuple[str, ...]:
    files = {
        "README.md": "# DecisionDoc AI\n",
        "docs/case-study.md": "# Case Study\n\nVerified local workflow.\n",
        "evidence/result.json": '{"ok": true}\n',
    }
    for relative_path, content in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tuple(sorted(files))


def test_portfolio_pack_sync_prunes_stale_files_and_checks_exact_content(tmp_path: Path) -> None:
    source_paths = _write_sources(tmp_path)
    pack_dir = tmp_path / "exports" / "decisiondoc_ai_portfolio_pack"
    stale_file = pack_dir / "stale.md"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale\n", encoding="utf-8")

    result = manager.sync_pack(
        root=tmp_path,
        pack_dir=pack_dir,
        source_paths=source_paths,
        prune=True,
    )

    manifest = json.loads((pack_dir / manager.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["source_file_count"] == 3
    assert not stale_file.exists()
    assert [item["path"] for item in manifest["files"]] == list(source_paths)
    assert manager.check_pack(root=tmp_path, pack_dir=pack_dir, source_paths=source_paths)["ok"] is True


def test_portfolio_pack_check_rejects_tampered_content(tmp_path: Path) -> None:
    source_paths = _write_sources(tmp_path)
    pack_dir = tmp_path / "decisiondoc_ai_portfolio_pack"
    manager.sync_pack(root=tmp_path, pack_dir=pack_dir, source_paths=source_paths, prune=True)
    (pack_dir / "docs/case-study.md").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="file drifted"):
        manager.check_pack(root=tmp_path, pack_dir=pack_dir, source_paths=source_paths)


def test_portfolio_zip_is_deterministic_and_rejects_tampering(tmp_path: Path) -> None:
    source_paths = _write_sources(tmp_path)
    pack_dir = tmp_path / "decisiondoc_ai_portfolio_pack"
    first_zip = tmp_path / "first.zip"
    second_zip = tmp_path / "second.zip"
    manager.sync_pack(root=tmp_path, pack_dir=pack_dir, source_paths=source_paths, prune=True)

    first = manager.package_zip(
        root=tmp_path,
        pack_dir=pack_dir,
        zip_path=first_zip,
        source_paths=source_paths,
    )
    second = manager.package_zip(
        root=tmp_path,
        pack_dir=pack_dir,
        zip_path=second_zip,
        source_paths=source_paths,
    )

    assert first["zip_sha256"] == second["zip_sha256"]
    assert first_zip.read_bytes() == second_zip.read_bytes()
    assert manager.verify_zip(pack_dir=pack_dir, zip_path=first_zip)["ok"] is True

    (pack_dir / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ZIP file drifted"):
        manager.verify_zip(pack_dir=pack_dir, zip_path=first_zip)


def test_portfolio_pack_rejects_unsafe_paths_and_directories(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must stay relative"):
        manager.build_manifest(tmp_path, ("../secret.txt",))

    with pytest.raises(ValueError, match="must be named"):
        manager.sync_pack(
            root=tmp_path,
            pack_dir=tmp_path / "wrong-name",
            source_paths=(),
            prune=True,
        )


def test_portfolio_pack_rejects_zip_output_inside_pack(tmp_path: Path) -> None:
    source_paths = _write_sources(tmp_path)
    pack_dir = tmp_path / "decisiondoc_ai_portfolio_pack"
    manager.sync_pack(root=tmp_path, pack_dir=pack_dir, source_paths=source_paths, prune=True)

    with pytest.raises(ValueError, match="outside the portfolio pack"):
        manager.package_zip(
            root=tmp_path,
            pack_dir=pack_dir,
            zip_path=pack_dir / "portfolio.zip",
            source_paths=source_paths,
        )


def test_tracked_portfolio_pack_matches_current_sources() -> None:
    source_paths = manager.collect_tracked_sources(manager.REPO_ROOT)

    result = manager.check_pack(
        root=manager.REPO_ROOT,
        pack_dir=manager.DEFAULT_PACK_DIR,
        source_paths=source_paths,
    )

    assert result["ok"] is True
    assert result["source_file_count"] == len(source_paths)
