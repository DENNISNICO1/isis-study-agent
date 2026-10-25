#!/bin/bash
# Installiert das Paket in Cloud-Sessions, damit `isis-agent` und pytest sofort verfügbar sind.
set -euo pipefail
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "$CLAUDE_PROJECT_DIR"
pip install -q -e '.[dev]' >/dev/null 2>&1 || pip install -q --break-system-packages -e '.[dev]'
