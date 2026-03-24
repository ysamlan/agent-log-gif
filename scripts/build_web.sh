#!/bin/bash
# Build the web bundle: creates web/agent_log_gif.zip from Python source.
#
# Excludes CLI-only modules (session discovery, web API, video/audio backends,
# analysis) to minimize bundle size. The web pipeline.py stubs __init__.py
# at runtime via sys.modules.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - "$ROOT_DIR" << 'PYEOF'
import os
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
src_dir = root / "src"
web_dir = root / "web"
out_path = web_dir / "agent_log_gif.zip"

EXCLUDE_FILES = {
    "__init__.py",
    "session.py",
    "web.py",
    "analysis.py",
    "share.py",
}
EXCLUDE_BACKEND_FILES = {
    "video.py",
    "audio.py",
}

print("Building agent_log_gif.zip...")
out_path.unlink(missing_ok=True)

pkg_dir = src_dir / "agent_log_gif"
count = 0
with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(pkg_dir.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src_dir)
        name = path.name

        # Skip excluded top-level modules
        if path.parent == pkg_dir and name in EXCLUDE_FILES:
            continue
        # Skip excluded backend modules
        if path.parent == pkg_dir / "backends" and name in EXCLUDE_BACKEND_FILES:
            continue

        if path.is_file():
            zf.write(path, rel)
            count += 1

size = out_path.stat().st_size
print(f"Done: {size / 1024:.0f} KB ({count} files) → {out_path}")
PYEOF
