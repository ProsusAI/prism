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

# Pipe stdin directly to Python - single invocation, no shell variable interpolation
# (extraction lock only suppresses auto-extract spawn inside capture.py, not observation writes)
# Errors go to capture.log (never block Claude Code — exit 0 always)
python3 "$PRISM_HOME/lib/capture.py" "$PHASE" >>"$PRISM_HOME/capture.log" 2>&1 || true

exit 0
