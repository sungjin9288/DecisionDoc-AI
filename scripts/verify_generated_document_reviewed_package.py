#!/usr/bin/env python3
"""Verify a completed generated-document review ZIP without changing local state."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True

import argparse
import json
import os
import stat
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.storage.generated_document_review_models import (  # noqa: E402
    MAX_REVIEWED_PACKAGE_SIZE_BYTES,
    GeneratedDocumentReviewedPackageError,
    verify_generated_document_reviewed_package,
)


RESULT_SCHEMA_VERSION = (
    "decisiondoc.generated_document_reviewed_package.verification.v1"
)


def _open_readonly(path: str, flags: int) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise OSError("safe local file opening is unavailable")
    return os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the internal integrity of a completed DecisionDoc review ZIP. "
            "This does not authenticate its issuer or grant operational approval."
        )
    )
    parser.add_argument(
        "package", type=Path, help="path to a regular, non-symlink ZIP file"
    )
    args = parser.parse_args(argv)
    try:
        with open(args.package, "rb", opener=_open_readonly) as package_file:
            before = os.fstat(package_file.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or not 0 < before.st_size <= MAX_REVIEWED_PACKAGE_SIZE_BYTES
            ):
                raise GeneratedDocumentReviewedPackageError(
                    "package size or type is invalid"
                )
            content = package_file.read(MAX_REVIEWED_PACKAGE_SIZE_BYTES + 1)
            after = os.fstat(package_file.fileno())
            if len(content) != before.st_size or after.st_size != before.st_size:
                raise GeneratedDocumentReviewedPackageError(
                    "package size changed while reading"
                )
        evidence = verify_generated_document_reviewed_package(content)
    except (OSError, ValueError, EOFError, RecursionError, zlib.error):
        print("verification failed", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "schema_version": RESULT_SCHEMA_VERSION,
                "status": "verified",
                "packet_sha256": evidence["packet"]["packet_sha256"],
                "completion_receipt_sha256": evidence["completion_receipt_sha256"],
                "reviewed_package_sha256": evidence["reviewed_package_sha256"],
                "reviewed_package_size_bytes": evidence["reviewed_package_size_bytes"],
                "review_decision": evidence["receipt"]["review_decision"],
                "operational_approval": False,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
