#!/usr/bin/env bash
# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

# Prism capture hook for Cursor
# Registered as preToolUse-only hook in .cursor/hooks.json (one obs per tool call)
#
# Receives JSON on stdin from Cursor Agent.
# Pipes directly to a single Python process.
# NEVER blocks Cursor - exit 0 always.

set -euo pipefail

PRISM_HOME="${PRISM_HOME:-$HOME/.prism}"
PHASE="${1:-pre}"

# Cursor launches this hook from the GUI app, whose PATH often omits ~/.local/bin
# (where `prism` and `agent` are installed). Without these dirs, the background
# `prism extract` this triggers cannot find the `agent` CLI it shells out to, so
# extraction silently produces zero engrams. Prepend the standard install dirs so
# the whole spawned chain (prism -> agent) resolves regardless of Cursor's PATH.
export PATH="$HOME/.local/bin:$HOME/.cursor/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

PRISM_SOURCE=cursor python3 "$PRISM_HOME/lib/capture.py" "$PHASE" >>"$PRISM_HOME/capture.log" 2>&1 || true

exit 0
