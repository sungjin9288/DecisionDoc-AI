#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$ROOT_DIR/.githooks"

chmod +x "$HOOKS_DIR/pre-commit"
git config core.hooksPath "$HOOKS_DIR"

echo "Installed git hooks from $HOOKS_DIR"
echo "Current core.hooksPath: $(git config core.hooksPath)"
