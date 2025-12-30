#!/usr/bin/env bash
#
# Install this skill/package as a command-line tool
#
# Usage:
#   ./scripts/install.sh            # Install
#   ./scripts/install.sh --force    # Reinstall/upgrade
#   ./scripts/install.sh --dry-run  # Show what would be done
#

set -e

# Get the directory where this script lives, then go up one level to skill root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Extract package name from pyproject.toml or SKILL.md
if [[ -f "$SKILL_DIR/pyproject.toml" ]]; then
    PACKAGE_NAME=$(grep -m1 '^name' "$SKILL_DIR/pyproject.toml" | sed -E 's/.*"([^"]+)".*/\1/')
elif [[ -f "$SKILL_DIR/SKILL.md" ]]; then
    PACKAGE_NAME=$(grep -m1 '^name:' "$SKILL_DIR/SKILL.md" | sed -E 's/name:\s*//')
else
    PACKAGE_NAME=$(basename "$SKILL_DIR")
fi

# Parse arguments
FORCE=""
DRY_RUN=""
for arg in "$@"; do
    case $arg in
        --force|-f)
            FORCE="--force"
            ;;
        --dry-run|-n)
            DRY_RUN=1
            ;;
    esac
done

run_cmd() {
    if [[ -n "$DRY_RUN" ]]; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

echo "Installing $PACKAGE_NAME from: $SKILL_DIR"
[[ -n "$DRY_RUN" ]] && echo "(dry-run mode - no changes will be made)"

# Try uv first (preferred)
if command -v uv &> /dev/null; then
    echo "Using uv tool install..."
    run_cmd uv tool install $FORCE "$SKILL_DIR"
    echo ""
    echo "Success! Run '$PACKAGE_NAME --help' to get started."
    exit 0
fi

# Fall back to pip
if command -v pip &> /dev/null; then
    echo "Warning: uv not found, falling back to pip"
    echo "For better experience, install uv: https://docs.astral.sh/uv/"
    echo ""
    echo "Using pip install..."
    run_cmd pip install $( [[ -n "$FORCE" ]] && echo "--force-reinstall" ) "$SKILL_DIR"
    echo ""
    echo "Success! Run '$PACKAGE_NAME --help' to get started."
    exit 0
fi

# Neither found
echo "Error: Neither uv nor pip found."
echo ""
echo "Please install one of:"
echo "  uv (recommended): https://docs.astral.sh/uv/"
echo "  pip: https://pip.pypa.io/en/stable/installation/"
exit 1
