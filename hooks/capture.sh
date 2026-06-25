#!/usr/bin/env bash
# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

# Prism capture hook for Claude Code
# Registered as PreToolUse hook in .claude/settings.local.json
#
# Receives JSON on stdin from Claude Code.
# Pipes directly to a single Python process (D-08, D-09).
# NEVER blocks Claude Code - exit 0 always.

set -euo pipefail

PRISM_HOME="${PRISM_HOME:-$HOME/.prism}"
PHASE="${1:-pre}"

# Ensure the dirs where `prism` and `claude` are installed are on PATH so the
# background `prism extract` this triggers (and its `claude` subprocess) resolve
# even if the hook is launched with a stripped PATH. Terminal-launched Claude Code
# usually already has these; the prepend is harmless (duplicate entries are fine).
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# Pipe stdin directly to Python - single invocation, no shell variable interpolation
# (extraction lock only suppresses auto-extract spawn inside capture.py, not observation writes)
# Errors go to capture.log (never block Claude Code — exit 0 always)
PRISM_SOURCE=claude_code python3 "$PRISM_HOME/lib/capture.py" "$PHASE" >>"$PRISM_HOME/capture.log" 2>&1 || true

exit 0
