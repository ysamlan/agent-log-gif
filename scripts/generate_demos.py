#!/usr/bin/env python3
"""Generate demo GIFs for the README.

Usage:
    just demos          # via justfile
    uv run scripts/generate_demos.py   # directly

Outputs:
    demo.gif                    — Mac chrome, Claude Code session
    docs/demo-windows-codex.gif — Windows chrome, Codex session
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
DOCS = ROOT / "docs"


DEMOS = [
    {
        "description": "Main demo (mac chrome, Claude Code)",
        "output": ROOT / "demo.gif",
        "args": [
            str(TESTS / "sample_session.jsonl"),
            "--chrome",
            "mac",
            "--turns",
            "3",
        ],
    },
    {
        "description": "Windows chrome, Codex session",
        "output": DOCS / "demo-windows-codex.gif",
        "args": [
            str(TESTS / "sample_codex_session.jsonl"),
            "--chrome",
            "windows",
        ],
    },
]


def main():
    DOCS.mkdir(exist_ok=True)

    for demo in DEMOS:
        print(f"\n{'=' * 60}")
        print(f"  {demo['description']}")
        print(f"  → {demo['output'].relative_to(ROOT)}")
        print(f"{'=' * 60}\n")

        cmd = [
            "agent-log-gif",
            "json",
            *demo["args"],
            "-o",
            str(demo["output"]),
        ]
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            print(f"FAILED: {demo['description']}", file=sys.stderr)
            sys.exit(1)

    print("\nAll demos generated successfully.")
    for demo in DEMOS:
        path = demo["output"]
        size_kb = path.stat().st_size / 1024
        print(f"  {path.relative_to(ROOT)}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
