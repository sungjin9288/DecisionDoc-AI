from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import local_write_once


def _temporary_files(path: Path) -> list[Path]:
    return list(path.parent.glob(f"{path.name}.tmp.*"))


def test_write_bytes_once_publishes_complete_content(tmp_path: Path) -> None:
    output_path = tmp_path / "handoff.zip"

    local_write_once.write_bytes_once(
        output_path,
        b"complete handoff",
        label="handoff package",
    )

    assert output_path.read_bytes() == b"complete handoff"
    assert _temporary_files(output_path) == []


def test_write_bytes_once_preserves_an_existing_file(tmp_path: Path) -> None:
    output_path = tmp_path / "handoff.zip"
    output_path.write_bytes(b"existing evidence")

    with pytest.raises(ValueError, match="refusing to overwrite existing handoff package"):
        local_write_once.write_bytes_once(
            output_path,
            b"replacement",
            label="handoff package",
        )

    assert output_path.read_bytes() == b"existing evidence"
    assert _temporary_files(output_path) == []


def test_write_bytes_once_preserves_a_competing_file(tmp_path: Path, monkeypatch) -> None:
    output_path = tmp_path / "handoff-summary.md"
    real_link = os.link

    def publish_competing_file(source: Path, target: Path) -> None:
        Path(target).write_bytes(b"competing evidence")
        real_link(source, target)

    monkeypatch.setattr(local_write_once.os, "link", publish_competing_file)

    with pytest.raises(ValueError, match="refusing to overwrite existing handoff summary"):
        local_write_once.write_bytes_once(
            output_path,
            b"new summary",
            label="handoff summary",
        )

    assert output_path.read_bytes() == b"competing evidence"
    assert _temporary_files(output_path) == []


def test_write_bytes_once_cleans_up_when_publication_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "handoff.zip"

    def reject_link(source: Path, target: Path) -> None:
        raise OSError("hard links unavailable")

    monkeypatch.setattr(local_write_once.os, "link", reject_link)

    with pytest.raises(OSError, match="hard links unavailable"):
        local_write_once.write_bytes_once(
            output_path,
            b"complete handoff",
            label="handoff package",
        )

    assert not output_path.exists()
    assert _temporary_files(output_path) == []
