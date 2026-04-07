#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


TRACKED_FILE_CMD = ["git", "ls-files", "-z"]

ACCESS_KEY_ID_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
SECRET_ASSIGNMENT_RES = [
    re.compile(r"(?:export\s+)?[\"']?AWS_SECRET_ACCESS_KEY[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{40})\b"),
    re.compile(r"(?:export\s+)?[\"']?aws_secret_access_key[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{40})\b"),
    re.compile(r"aws\s+configure\s+set\s+aws_secret_access_key\s+[\"']?([A-Za-z0-9/+=]{40})\b"),
]
SESSION_TOKEN_ASSIGNMENT_RES = [
    re.compile(r"(?:export\s+)?[\"']?AWS_SESSION_TOKEN[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{16,})\b"),
    re.compile(r"(?:export\s+)?[\"']?aws_session_token[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{16,})\b"),
    re.compile(r"aws\s+configure\s+set\s+aws_session_token\s+[\"']?([A-Za-z0-9/+=]{16,})\b"),
]
ACCESS_KEY_ASSIGNMENT_RES = [
    re.compile(r"(?:export\s+)?[\"']?AWS_ACCESS_KEY_ID[\"']?\s*[:=]\s*[\"']?((?:AKIA|ASIA)[0-9A-Z]{16})\b"),
    re.compile(r"(?:export\s+)?[\"']?aws_access_key_id[\"']?\s*[:=]\s*[\"']?((?:AKIA|ASIA)[0-9A-Z]{16})\b"),
    re.compile(r"aws\s+configure\s+set\s+aws_access_key_id\s+[\"']?((?:AKIA|ASIA)[0-9A-Z]{16})\b"),
]


def tracked_files() -> list[Path]:
    result = subprocess.run(
        TRACKED_FILE_CMD,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def find_violations(path: Path, text: str) -> list[str]:
    violations: list[str] = []
    for match in ACCESS_KEY_ID_RE.finditer(text):
        violations.append(
            f"{path}:{text[: match.start()].count(chr(10)) + 1}: possible AWS access key id {match.group(0)}"
        )
    for pattern in ACCESS_KEY_ASSIGNMENT_RES + SECRET_ASSIGNMENT_RES + SESSION_TOKEN_ASSIGNMENT_RES:
        for match in pattern.finditer(text):
            violations.append(
                f"{path}:{text[: match.start()].count(chr(10)) + 1}: credential assignment pattern detected"
            )
    return violations


def main() -> int:
    violations: list[str] = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        violations.extend(find_violations(path, text))

    if violations:
        print("Secret hygiene check failed. Remove static AWS credentials from tracked files.", file=sys.stderr)
        for violation in violations:
            print(violation, file=sys.stderr)
        return 1

    print("Secret hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
