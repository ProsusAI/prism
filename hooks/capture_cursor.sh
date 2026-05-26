#!/usr/bin/env bash
# Prism capture hook for Cursor
# Registered as preToolUse-only hook in .cursor/settings.json (one obs per tool call)
#
# Receives JSON on stdin from Cursor Agent.
# Pipes directly to a single Python process.
# NEVER blocks Cursor - exit 0 always.

set -euo pipefail

PRISM_HOME="${PRISM_HOME:-$HOME/.prism}"
PHASE="${1:-pre}"

PRISM_SOURCE=cursor python3 "$PRISM_HOME/lib/capture.py" "$PHASE" >>"$PRISM_HOME/capture.log" 2>&1 || true

exit 0
