#!/usr/bin/env python3
"""Sync color schemes from iTerm2-Color-Schemes into a bundled JSON file.

Reads VS Code JSON files from the iTerm2-Color-Schemes repo and writes a
compact lookup table to src/agent_log_gif/color_schemes.json.

Usage:
    just sync-schemes                              # via justfile (default path)
    uv run scripts/sync_color_schemes.py [DIR]     # custom path to vscode/ dir

The default source is ./tmp/iTerm2-Color-Schemes/vscode/.
Clone the repo first:
    git clone https://github.com/mbadolato/iTerm2-Color-Schemes tmp/iTerm2-Color-Schemes
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VSCODE_DIR = ROOT / "tmp" / "iTerm2-Color-Schemes" / "vscode"
OUTPUT = ROOT / "src" / "agent_log_gif" / "color_schemes.json"

# Map VS Code terminal color keys to our compact key names
KEY_MAP = {
    "terminal.foreground": "foreground",
    "terminal.background": "background",
    "terminal.selectionBackground": "selection",
    "terminalCursor.foreground": "cursor",
    "terminal.ansiBlack": "ansi_0",
    "terminal.ansiRed": "ansi_1",
    "terminal.ansiGreen": "ansi_2",
    "terminal.ansiYellow": "ansi_3",
    "terminal.ansiBlue": "ansi_4",
    "terminal.ansiMagenta": "ansi_5",
    "terminal.ansiCyan": "ansi_6",
    "terminal.ansiWhite": "ansi_7",
    "terminal.ansiBrightBlack": "ansi_8",
    "terminal.ansiBrightRed": "ansi_9",
    "terminal.ansiBrightGreen": "ansi_10",
    "terminal.ansiBrightYellow": "ansi_11",
    "terminal.ansiBrightBlue": "ansi_12",
    "terminal.ansiBrightMagenta": "ansi_13",
    "terminal.ansiBrightCyan": "ansi_14",
    "terminal.ansiBrightWhite": "ansi_15",
}


def parse_vscode_scheme(path: Path) -> dict[str, str] | None:
    """Parse a VS Code terminal color JSON file into our compact format."""
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    colors = raw.get("workbench.colorCustomizations", {})
    scheme = {}
    for vscode_key, our_key in KEY_MAP.items():
        if vscode_key in colors:
            scheme[our_key] = colors[vscode_key].lower()

    # Must have at least foreground and background
    if "foreground" not in scheme or "background" not in scheme:
        return None

    return scheme


def main():
    vscode_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VSCODE_DIR

    if not vscode_dir.is_dir():
        # Auto-clone the repo if using the default path
        repo_dir = vscode_dir.parent
        if vscode_dir == DEFAULT_VSCODE_DIR and not repo_dir.exists():
            print("Cloning iTerm2-Color-Schemes...")
            import subprocess

            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "https://github.com/mbadolato/iTerm2-Color-Schemes",
                    str(repo_dir),
                ],
                check=True,
            )
        if not vscode_dir.is_dir():
            print(f"Directory not found: {vscode_dir}", file=sys.stderr)
            sys.exit(1)

    schemes = {}
    skipped = 0
    for path in sorted(vscode_dir.glob("*.json")):
        name = path.stem  # filename without .json
        scheme = parse_vscode_scheme(path)
        if scheme:
            schemes[name] = scheme
        else:
            skipped += 1

    OUTPUT.write_text(json.dumps(schemes, separators=(",", ":"), sort_keys=True) + "\n")

    size_kb = OUTPUT.stat().st_size / 1024
    print(
        f"Wrote {len(schemes)} color schemes to {OUTPUT.relative_to(ROOT)} ({size_kb:.0f} KB)"
    )
    if skipped:
        print(f"Skipped {skipped} files (missing foreground/background)")


if __name__ == "__main__":
    main()
