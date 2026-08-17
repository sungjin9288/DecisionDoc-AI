#!/usr/bin/env python3
"""Read-only verifier for a generated-document export review packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.generation_export_packet import (  # noqa: E402
    GenerationExportPacketError,
    MAX_PACKET_SIZE_BYTES,
    verify_generation_export_packet,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a DecisionDoc generated-document export packet without writing files."
    )
    parser.add_argument("packet", type=Path, help="path to the ZIP packet")
    args = parser.parse_args(argv)
    try:
        size_bytes = args.packet.stat().st_size
        if not 0 < size_bytes <= MAX_PACKET_SIZE_BYTES:
            raise GenerationExportPacketError("packet size is invalid")
        with args.packet.open("rb") as packet_file:
            content = packet_file.read(MAX_PACKET_SIZE_BYTES + 1)
        if len(content) != size_bytes or len(content) > MAX_PACKET_SIZE_BYTES:
            raise GenerationExportPacketError("packet size changed while reading")
        evidence = verify_generation_export_packet(content)
    except (OSError, GenerationExportPacketError):
        print("verification failed", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "artifact_count": evidence["artifact_count"],
                "manifest_sha256": evidence["manifest_sha256"],
                "packet_sha256": evidence["packet_sha256"],
                "status": "verified",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
