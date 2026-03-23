#!/bin/bash
# Fetch pre-built gifsicle WASM artifacts from the gifsicle-bin GitHub release.
# Version is extracted from pyproject.toml's gifsicle-bin dependency.
#
# Usage:
#   bash scripts/fetch_gifsicle_wasm.sh           # use version from pyproject.toml
#   bash scripts/fetch_gifsicle_wasm.sh 1.96.2    # explicit version
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/web/lib/gifsicle"
GITHUB_REPO="ysamlan/gifsicle-bin"

# Determine version: argument > pyproject.toml
if [ $# -ge 1 ]; then
  VERSION="$1"
else
  VERSION=$(grep 'gifsicle-bin>=' "$REPO_ROOT/pyproject.toml" | sed 's/.*gifsicle-bin>=\([^"]*\).*/\1/')
  if [ -z "$VERSION" ]; then
    echo "ERROR: Could not extract gifsicle-bin version from pyproject.toml"
    exit 1
  fi
fi

echo "==> Fetching gifsicle WASM from gifsicle-bin release $VERSION..."

RELEASE_URL="https://github.com/$GITHUB_REPO/releases/download/$VERSION"

for file in gifsicle.js gifsicle.wasm; do
  echo "    Downloading $file..."
  curl -fsSL "$RELEASE_URL/$file" -o "$OUTPUT_DIR/$file"
done

echo "==> Done! Updated files:"
ls -la "$OUTPUT_DIR/gifsicle.js" "$OUTPUT_DIR/gifsicle.wasm"
