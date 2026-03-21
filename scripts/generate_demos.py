#!/usr/bin/env python3
"""Generate demo media for the README.

Usage:
    just demos          # via justfile
    uv run scripts/generate_demos.py   # directly

Outputs:
    demo.avif                   — Main above-the-fold demo (inbox zero scenario)
    docs/demo-windows-codex.avif — Windows chrome, Codex session
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
DOCS = ROOT / "docs"


DEMOS = [
    {
        "description": "Main demo — inbox zero scenario (mac chrome, --show tools)",
        "output": ROOT / "demo.avif",
        "args": [
            str(SCRIPTS / "demo_session.jsonl"),
            "--format",
            "avif",
            "--chrome",
            "mac",
            "--canvas-bg",
            "#FFFFFF",
            "--show",
            "tools",
            "--speed",
            "1.0",
            "--spinner-time",
            "1.0",
        ],
    },
    {
        "description": "Windows chrome, Codex session",
        "output": DOCS / "demo-windows-codex.avif",
        "args": [
            str(TESTS / "sample_codex_session.jsonl"),
            "--format",
            "avif",
            "--chrome",
            "windows",
        ],
    },
]


def main():
    DOCS.mkdir(exist_ok=True)

    for demo in DEMOS:
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {demo['description']}", flush=True)
        print(f"  → {demo['output'].relative_to(ROOT)}", flush=True)
        print(f"{'=' * 60}\n", flush=True)

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

    print("\nAll demos generated successfully.", flush=True)
    for demo in DEMOS:
        path = demo["output"]
        size_kb = path.stat().st_size / 1024
        print(f"  {path.relative_to(ROOT)}  ({size_kb:.0f} KB)", flush=True)


if __name__ == "__main__":
    main()
