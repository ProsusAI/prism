#!/usr/bin/env bash
# Prism installer
# Usage: ./install.sh
#
# What it does:
#   1. Checks prerequisites (python3, git required; claude CLI recommended)
#   2. Creates ~/.prism/ directory tree
#   3. Copies hooks, agent prompts, lib, and templates
#   4. Creates a symlink so `prism` is on your PATH
#
# After install, run `prism init` in any project to set up hooks for that project.

set -euo pipefail

PRISM_REPO="$(cd "$(dirname "$0")" && pwd)"
PRISM_HOME="${PRISM_HOME:-$HOME/.prism}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

# --- Prerequisite checks ---

# python3 is required (hard fail)
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required but not found."; exit 1; }

# git is required (hard fail)
command -v git >/dev/null 2>&1 || { echo "ERROR: git is required but not found."; exit 1; }

# claude CLI is optional (soft warning)
command -v claude >/dev/null 2>&1 || echo "WARNING: claude CLI not found. Needed for extraction (prism extract) but not for observation capture."

# Python version warning
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo '0.0')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    echo "WARNING: Python 3.12+ recommended (found $PY_VERSION). Prism should work but is untested on older versions."
fi

echo "Installing Prism..."
echo "  Source:  $PRISM_REPO"
echo "  Home:    $PRISM_HOME"
echo "  Binary:  $BIN_DIR/prism"
echo ""

# 1. Create directory structure (SETUP-01)
mkdir -p "$PRISM_HOME"/{global/engrams,archive,hooks,agents,lib,skills,projects,cache}
mkdir -p "$BIN_DIR"

# 2. Copy hooks (overwrite on upgrade)
cp "$PRISM_REPO/hooks/capture.sh" "$PRISM_HOME/hooks/capture.sh"
cp "$PRISM_REPO/hooks/capture_cursor.sh" "$PRISM_HOME/hooks/capture_cursor.sh"
chmod +x "$PRISM_HOME/hooks/capture.sh"
chmod +x "$PRISM_HOME/hooks/capture_cursor.sh"

# 3. Copy agent prompts (overwrite on upgrade)
cp "$PRISM_REPO/agents/"*.md "$PRISM_HOME/agents/"

# 4. Copy lib (overwrite on upgrade)
for pyfile in "$PRISM_REPO"/lib/*.py; do
    [ -f "$pyfile" ] || continue
    case "$(basename "$pyfile")" in
        test_*) continue ;;  # Exclude test files from install
    esac
    cp "$pyfile" "$PRISM_HOME/lib/"
done

# 4b. Copy slash command skills (overwrite on upgrade)
if [ -d "$PRISM_REPO/skills" ]; then
    for skill_dir in "$PRISM_REPO/skills"/*/; do
        [ -d "$skill_dir" ] || continue
        skill_name=$(basename "$skill_dir")
        mkdir -p "$PRISM_HOME/skills/$skill_name"
        cp "$skill_dir"* "$PRISM_HOME/skills/$skill_name/" 2>/dev/null || true
    done
fi

# 4c. Copy registry template (overwrite on upgrade)
if [ -d "$PRISM_REPO/templates/registry" ]; then
    mkdir -p "$PRISM_HOME/templates/registry"
    cp -r "$PRISM_REPO/templates/registry/." "$PRISM_HOME/templates/registry/"
    echo "  Copied registry template"
fi

# 4d. Copy schemas (overwrite on upgrade)
if [ -d "$PRISM_REPO/schemas" ]; then
    mkdir -p "$PRISM_HOME/schemas"
    cp "$PRISM_REPO/schemas/"*.json "$PRISM_HOME/schemas/" 2>/dev/null || true
fi

# 5. Copy CLI wrapper (overwrite on upgrade)
cp "$PRISM_REPO/prism" "$PRISM_HOME/prism"
chmod +x "$PRISM_HOME/prism"

# 6. Copy constitution template only if not exists (SETUP-04)
if [ ! -f "$PRISM_HOME/constitution.md" ]; then
    cp "$PRISM_REPO/templates/constitution.md" "$PRISM_HOME/constitution.md"
fi

# 7. Write default config.json if missing (SETUP-03)
if [ ! -f "$PRISM_HOME/config.json" ]; then
    cat > "$PRISM_HOME/config.json" << 'EOF'
{
  "extract_threshold": 15,
  "review_interval": 5,
  "review_timeout": 60,
  "decay_rate_per_week": 0.02,
  "archive_threshold": 0.2,
  "publish_min_confidence": 0.7,
  "publish_min_evidence": 3,
  "max_context_lines": 100,
  "registry_url": ""
}
EOF
fi

# 8. Write empty index.json if missing (SETUP-03)
if [ ! -f "$PRISM_HOME/index.json" ]; then
    echo '{"engrams": []}' > "$PRISM_HOME/index.json"
fi

# 9. Create symlink (SETUP-02)
# Symlinks to the installed copy so updates via install.sh are picked up
ln -sf "$PRISM_HOME/prism" "$BIN_DIR/prism"

# 10. Check PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qxF "$BIN_DIR"; then
    echo "NOTE: $BIN_DIR is not in your PATH."
    echo "Add this to your shell profile (~/.zshrc or ~/.bashrc):"
    echo ""
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    echo ""
fi

echo "Done!"
echo ""
echo "Next: cd into a project and run:"
echo ""
echo "  prism init    # hooks into Claude Code for this project"

# Note on dual-path install (SETUP-07):
# When run from a git clone, PRISM_REPO is the repo root and all source
# files are available. For a curl|bash distribution model, files would
# need to be bundled/extracted first. The primary install path is
# git clone for now (repo is private).
