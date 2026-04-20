#!/usr/bin/env bash
# Prism capture hook for Claude Code
# Registered as PreToolUse hook in .claude/settings.local.json
#
# Receives JSON on stdin from Claude Code.
# Pipes directly to a single Python process (D-08, D-09).
# NEVER blocks Claude Code - exit 0 always.

set -euo pipefail

PRISM_HOME="${PRISM_HOME:-$HOME/.prism}"
PHASE="${1:-pre}"

# Guard: don't capture during extraction
[ -f "$PRISM_HOME/.extracting" ] && exit 0

# Pipe stdin directly to Python - single invocation, no shell variable interpolation
# If Python fails for any reason, exit 0 (never block Claude Code)
python3 "$PRISM_HOME/lib/capture.py" "$PHASE" 2>/dev/null || true

exit 0
