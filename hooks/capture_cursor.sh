#!/usr/bin/env bash
# Prism capture hook for Cursor
# Registered as preToolUse hook in .cursor/settings.json
#
# Receives JSON on stdin from Cursor Agent.
# Pipes directly to a single Python process.
# NEVER blocks Cursor - exit 0 always.

set -euo pipefail

PRISM_HOME="${PRISM_HOME:-$HOME/.prism}"
PHASE="${1:-pre}"

# Guard: don't capture during extraction
[ -f "$PRISM_HOME/.extracting" ] && exit 0

PRISM_SOURCE=cursor python3 "$PRISM_HOME/lib/capture.py" "$PHASE" 2>/dev/null || true

exit 0
